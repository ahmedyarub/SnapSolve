import logging
import threading
import time

from core.llm.base import CANCELLED, LLMEngine
from core.llm.errors import LLMError
from core.sinks.base import Sink
from core.sources.base import Source
from core.sources.ocr.exceptions import OCRCancelledError

logger = logging.getLogger(__name__)

PIPELINE_CANCELLED_MSG = "Pipeline cancelled."


class LinkedCancel(threading.Event):
    """A cancel event that is also set while its parent is.

    The fallback model gets one: it stops when the user cancels the request,
    and also when the main model has answered and its result is no longer needed.
    """

    def __init__(self, parent: threading.Event | None):
        super().__init__()
        self._parent = parent

    def is_set(self) -> bool:
        return super().is_set() or bool(self._parent and self._parent.is_set())

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            super().wait(0.1 if remaining is None else min(0.1, remaining))
        return True


def _call_llm_with_retry(
    llm: LLMEngine,
    prompt: str,
    image_path: str | None,
    is_image: bool,
    status_callback,
    enable_chat_sessions: bool,
    sink: Sink,
    is_main: bool,
    cancel_event: threading.Event | None = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    """Call the LLM, retrying transient failures with exponential backoff.

    Waits *base_delay* × 2^attempt between tries (5 s → 10 s → 20 s by
    default) and checks *cancel_event* so the user can still abort. Raises
    :class:`LLMError` when the call fails for good.
    """
    for attempt in range(max_retries + 1):
        if cancel_event and cancel_event.is_set():
            return CANCELLED
        try:
            return llm.generate(
                prompt,
                image_path if is_image else None,
                status_callback,
                enable_chat_sessions,
                sink,
                is_main=is_main,
                cancel_event=cancel_event,
            )
        except LLMError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            delay = base_delay * (2**attempt)
            role = "main" if is_main else "fallback"
            logger.warning(
                "[Pipeline] Retryable error on %s model (attempt %d/%d): %s — retrying in %.0fs",
                role,
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            if status_callback:
                status_callback(f"Retrying ({attempt + 1}/{max_retries})...")
            if sink:
                sink.process_chunk("", is_main=is_main, replace=True)
            # Sleep in small increments so we can bail on cancellation.
            deadline = time.time() + delay
            while time.time() < deadline:
                if cancel_event and cancel_event.is_set():
                    return CANCELLED
                time.sleep(0.25)
    raise LLMError("retries exhausted", retryable=False)  # not reached


class ConcurrentSinkWrapper(Sink):
    def __init__(
        self,
        target_sink: Sink,
        main_finished_event: threading.Event,
        main_started: list,
        fallback_started: list,
        main_success: list,
        cancel_event: threading.Event | None = None,
    ):
        super().__init__(cancel_event)
        self.target_sink = target_sink
        self.main_finished_event = main_finished_event
        self.main_started = main_started
        self.fallback_started = fallback_started
        self.main_success = main_success
        self.lock = threading.Lock()

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        if not self.target_sink or self.cancel_event.is_set():
            return

        with self.lock:
            if is_main:
                if replace and chunk == "":
                    self.main_started[0] = False
                    self.target_sink.process_chunk("", is_main=True, replace=True)
                    if self.fallback_started[0]:
                        self.target_sink.process_chunk("", is_main=False, replace=False)
                    return
                else:
                    self.main_started[0] = True
                self.target_sink.process_chunk(chunk, is_main=True, replace=replace)
            else:
                if not self.main_started[0] and not self.main_success[0]:
                    self.fallback_started[0] = True
                    self.target_sink.process_chunk(
                        chunk, is_main=False, replace=replace
                    )

    def force_replace(self):
        if self.target_sink and self.fallback_started[0]:
            self.target_sink.process_chunk("", is_main=True, replace=True)


def _retrieve_data_from_source(
    source: Source,
    coords=None,
    text=None,
    status_callback=None,
    cancel_event: threading.Event | None = None,
) -> tuple[str | None, str | None, bool]:
    """Retrieve text or image from source."""
    image_path = None
    is_image = False

    try:
        extracted_text = _get_text_from_source(
            source, coords, text, status_callback, cancel_event
        )
        logger.info(
            "Retrieved %d characters from the source", len(extracted_text or "")
        )

        if hasattr(source, "temp_files") and source.temp_files:
            image_path = source.temp_files[-1]

        return extracted_text, image_path, is_image
    except (ValueError, OCRCancelledError) as e:
        return _handle_text_retrieval_error(source, coords, text, cancel_event, str(e))
    except Exception as e:
        raise RuntimeError(f"Error retrieving data from source: {e!s}") from e


def _get_text_from_source(
    source: Source,
    coords=None,
    text=None,
    status_callback=None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Get text from source."""
    return source.get_text(
        coords=coords,
        text=text,
        status_callback=status_callback,
        cancel_event=cancel_event,
    )


def _handle_text_retrieval_error(
    source: Source,
    coords=None,
    text=None,
    cancel_event: threading.Event | None = None,
    error_message: str = "",
) -> tuple[str | None, str | None, bool]:
    """Handle text retrieval error by attempting image retrieval."""
    if not (hasattr(source, "supports_images") and source.supports_images):
        raise ValueError(
            f"Pipeline failed: Source could not provide text ({error_message}), and LLM does not support images."
        )

    is_image = True
    image_path = _get_image_from_source(source, coords, text, cancel_event)
    logger.info("Retrieved an image from the source")
    return None, image_path, is_image


def _get_image_from_source(
    source: Source,
    coords=None,
    text=None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Get image from source."""
    return source.get_image(coords=coords, text=text, cancel_event=cancel_event)


def _build_prompt(prompt_text: str, extracted_text: str | None) -> str:
    """Build the final prompt from prompt text and extracted text."""
    if not prompt_text:
        return extracted_text
    return f"{prompt_text}: {extracted_text}" if extracted_text else prompt_text


def _execute_llm_without_fallback(
    llm: LLMEngine,
    prompt: str,
    image_path: str | None,
    is_image: bool,
    status_callback=None,
    enable_chat_sessions: bool = True,
    sink: Sink = None,
    cancel_event: threading.Event | None = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    """Execute LLM processing without fallback, with automatic retry."""
    return _call_llm_with_retry(
        llm,
        prompt,
        image_path,
        is_image,
        status_callback,
        enable_chat_sessions,
        sink,
        is_main=True,
        cancel_event=cancel_event,
        max_retries=max_retries,
        base_delay=base_delay,
    )


def _store_llm_result(
    results: dict,
    lock: threading.Lock,
    ans: str,
    is_main: bool,
    main_success: list,
):
    """Store a successful answer."""
    with lock:
        if is_main:
            results["main"] = ans
            main_success[0] = True
        else:
            results["fallback"] = ans


def _store_llm_error(
    results: dict,
    lock: threading.Lock,
    error: Exception,
    is_main: bool,
):
    """Store LLM error in results dict."""
    with lock:
        if is_main:
            results["main_error"] = str(error)
        else:
            results["fallback_error"] = str(error)


def _run_llm_thread(
    llm: LLMEngine,
    prompt: str,
    image_path: str | None,
    is_image: bool,
    status_callback,
    enable_chat_sessions: bool,
    sink: Sink,
    is_main: bool,
    results: dict,
    lock: threading.Lock,
    main_success: list,
    main_finished: threading.Event,
    cancel_event: threading.Event | None = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
):
    """Run LLM processing in a thread with automatic retry."""
    try:
        ans = _call_llm_with_retry(
            llm,
            prompt,
            image_path,
            is_image,
            status_callback,
            enable_chat_sessions,
            sink,
            is_main,
            cancel_event,
            max_retries=max_retries,
            base_delay=base_delay,
        )
        _store_llm_result(results, lock, ans, is_main, main_success)
    except Exception as error:
        _store_llm_error(results, lock, error, is_main)
        if is_main and sink:
            try:
                sink.process_chunk("", is_main=True, replace=True)
            except Exception as e:
                logger.error(f"Error clearing sink on main model failure: {e}")
    finally:
        if is_main:
            main_finished.set()


def _determine_final_result(
    results: dict, main_success: list, fallback_thread: threading.Thread
) -> str:
    """The main answer, else the fallback's; raises LLMError if both failed."""
    if main_success[0] and "main" in results:
        return results["main"]
    fallback_thread.join()
    if "fallback" in results:
        return results["fallback"]
    raise LLMError(
        f"Main model: {results.get('main_error', 'no answer')}; "
        f"fallback model: {results.get('fallback_error', 'no answer')}",
        retryable=False,
    )


def _save_to_session(
    session_manager,
    prompt: str,
    image_path: str | list[str] | None,
    final_result: str,
    extracted_text: str | None,
    source_name: str,
):
    """Save the interaction to session manager (only real answers reach here)."""
    if session_manager and final_result and final_result != CANCELLED:
        try:
            session_manager.append_interaction(
                prompt,
                image_path,
                final_result,
                extracted_text,
                source_name=source_name,
            )
        except Exception:
            logger.exception("Failed to save the interaction to the session")


def process_pipeline(
    source: Source,
    llm: LLMEngine,
    prompt_text: str,
    status_callback=None,
    session_manager=None,
    enable_chat_sessions: bool = True,
    sink: Sink = None,
    fallback_llm: LLMEngine = None,
    coords=None,
    text=None,
    image_paths=None,
    cancel_event: threading.Event | None = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    """Process a source through the LLM pipeline and return the result.

    This is the legacy entry-point.  Internally it builds and runs a
    composable :class:`Pipeline` of processors.
    """
    if cancel_event is None:
        cancel_event = threading.Event()

    pipeline_start_time = time.time()
    logger.info("Using source: %s", source.__class__.__name__)

    from .frames import CancelledFrame, ErrorFrame, Frame, LLMResponseFrame
    from .runner import build_pipeline

    pipeline = build_pipeline(
        source=source,
        llm=llm,
        prompt_text=prompt_text,
        status_callback=status_callback,
        session_manager=session_manager,
        enable_chat_sessions=enable_chat_sessions,
        sink=sink,
        fallback_llm=fallback_llm,
        coords=coords,
        text=text,
        image_paths=image_paths,
        max_retries=max_retries,
        base_delay=base_delay,
    )

    initial_frame = Frame(cancel_event=cancel_event, metadata={})
    result_frame = pipeline.run(initial_frame)

    elapsed_ms = (time.time() - pipeline_start_time) * 1000
    logger.info("[Pipeline] Finished processing in %.0f ms", elapsed_ms)

    if isinstance(result_frame, CancelledFrame):
        return PIPELINE_CANCELLED_MSG
    if isinstance(result_frame, ErrorFrame):
        return result_frame.error
    if isinstance(result_frame, LLMResponseFrame):
        return result_frame.result

    return "Error: unexpected pipeline result."
