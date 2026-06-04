from typing import Optional
import logging
import re
import threading
import time
from core.sources.base import Source
from core.sources.ocr.exceptions import OCRCancelledError
from core.llm.base import LLMEngine
from core.sinks.base import Sink

logger = logging.getLogger(__name__)

PIPELINE_CANCELLED_MSG = "Pipeline cancelled."

# Patterns that indicate a transient/retryable LLM error (matched case-insensitively).
_RETRYABLE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"503",
        r"429",
        r"UNAVAILABLE",
        r"overloaded",
        r"rate.?limit",
        r"quota",
        r"capacity",
        r"too many requests",
        r"ResourceExhausted",
        r"ServerError",
        r"deadline.?exceeded",
        r"connection",
    )
]


def _is_retryable_error(error_text: str) -> bool:
    """Return True if *error_text* matches any known transient error pattern."""
    return any(pat.search(error_text) for pat in _RETRYABLE_PATTERNS)


def _call_llm_with_retry(
    llm: LLMEngine,
    prompt: str,
    image_path: Optional[str],
    is_image: bool,
    status_callback,
    enable_chat_sessions: bool,
    sink: Sink,
    is_main: bool,
    cancel_event: threading.Event = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    """Call the LLM with automatic retry on transient errors.

    Uses exponential backoff: *base_delay* × 2^attempt (5 s → 10 s → 20 s by
    default).  Checks *cancel_event* between retries so the user can still
    abort.
    """
    last_error = ""
    for attempt in range(max_retries + 1):
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        try:
            result = _call_llm_with_cancel_check(
                llm, prompt, image_path, is_image,
                status_callback, enable_chat_sessions, sink, is_main, cancel_event,
            )

            # Some engines return error strings instead of raising.
            if isinstance(result, str) and result.startswith("Error") and _is_retryable_error(result):
                raise RuntimeError(result)

            return result

        except Exception as exc:
            last_error = str(exc)
            if not _is_retryable_error(last_error) or attempt >= max_retries:
                raise

            delay = base_delay * (2 ** attempt)
            role = "main" if is_main else "fallback"
            logger.warning(
                "[Pipeline] Retryable error on %s model (attempt %d/%d): %s — retrying in %.0fs",
                role, attempt + 1, max_retries, last_error, delay,
            )
            if status_callback:
                status_callback(f"Retrying ({attempt + 1}/{max_retries})...")

            # Sleep in small increments so we can bail on cancellation.
            deadline = time.time() + delay
            while time.time() < deadline:
                if cancel_event and cancel_event.is_set():
                    return "Cancelled"
                time.sleep(0.25)

    # Should not be reached, but just in case:
    return f"Error: retries exhausted — {last_error}"



class ConcurrentSinkWrapper(Sink):
    def __init__(
        self,
        target_sink: Sink,
        main_finished_event: threading.Event,
        main_started: list,
        fallback_started: list,
        main_success: list,
        cancel_event: threading.Event = None,
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
                self.main_started[0] = True
                self.target_sink.process_chunk(chunk, is_main=True, replace=False)
            else:
                if (
                    not self.main_started[0]
                    and not self.main_success[0]
                    and not self.main_finished_event.is_set()
                ):
                    self.fallback_started[0] = True
                    self.target_sink.process_chunk(chunk, is_main=False, replace=False)

    def force_replace(self):
        if self.target_sink and self.fallback_started[0]:
            self.target_sink.process_chunk("", is_main=True, replace=True)


def _retrieve_data_from_source(
    source: Source,
    coords=None,
    text=None,
    status_callback=None,
    cancel_event: threading.Event = None,
) -> tuple[Optional[str], Optional[str], bool]:
    """Retrieve text or image from source."""
    image_path = None
    is_image = False

    try:
        extracted_text = _get_text_from_source(
            source, coords, text, status_callback, cancel_event
        )
        print(f"Retrieved text from source: {extracted_text}")

        if hasattr(source, "_temp_files") and source._temp_files:
            image_path = source._temp_files[-1]

        return extracted_text, image_path, is_image
    except (ValueError, OCRCancelledError) as e:
        return _handle_text_retrieval_error(source, coords, text, cancel_event, str(e))
    except Exception as e:
        raise RuntimeError(f"Error retrieving data from source: {str(e)}")


def _get_text_from_source(
    source: Source,
    coords=None,
    text=None,
    status_callback=None,
    cancel_event: threading.Event = None,
) -> str:
    """Get text from source with optional cancel event support."""
    if (
        hasattr(source, "get_text")
        and "cancel_event" in source.get_text.__code__.co_varnames
    ):
        return source.get_text(
            coords=coords,
            text=text,
            status_callback=status_callback,
            cancel_event=cancel_event,
        )
    else:
        return source.get_text(
            coords=coords, text=text, status_callback=status_callback
        )


def _handle_text_retrieval_error(
    source: Source,
    coords=None,
    text=None,
    cancel_event: threading.Event = None,
    error_message: str = "",
) -> tuple[Optional[str], Optional[str], bool]:
    """Handle text retrieval error by attempting image retrieval."""
    if not (hasattr(source, "supports_images") and source.supports_images):
        raise ValueError(
            f"Pipeline failed: Source could not provide text ({error_message}), and LLM does not support images."
        )

    is_image = True
    image_path = _get_image_from_source(source, coords, text, cancel_event)
    print(f"Retrieved image from source: {image_path}")
    return None, image_path, is_image


def _get_image_from_source(
    source: Source,
    coords=None,
    text=None,
    cancel_event: threading.Event = None,
) -> str:
    """Get image from source with optional cancel event support."""
    if (
        hasattr(source, "get_image")
        and "cancel_event" in source.get_image.__code__.co_varnames
    ):
        return source.get_image(coords=coords, text=text, cancel_event=cancel_event)
    else:
        return source.get_image(coords=coords, text=text)


def _build_prompt(prompt_text: str, extracted_text: Optional[str]) -> str:
    """Build the final prompt from prompt text and extracted text."""
    if not prompt_text:
        return extracted_text
    return f"{prompt_text}: {extracted_text}" if extracted_text else prompt_text


def _execute_llm_without_fallback(
    llm: LLMEngine,
    prompt: str,
    image_path: Optional[str],
    is_image: bool,
    status_callback=None,
    enable_chat_sessions: bool = True,
    sink: Sink = None,
    cancel_event: threading.Event = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    """Execute LLM processing without fallback, with automatic retry."""
    return _call_llm_with_retry(
        llm, prompt, image_path, is_image,
        status_callback, enable_chat_sessions, sink, is_main=True,
        cancel_event=cancel_event, max_retries=max_retries, base_delay=base_delay,
    )


def _call_llm_with_cancel_check(
    llm: LLMEngine,
    prompt: str,
    image_path: Optional[str],
    is_image: bool,
    status_callback,
    enable_chat_sessions: bool,
    sink: Sink,
    is_main: bool,
    cancel_event: threading.Event = None,
) -> str:
    """Call LLM with cancel event support check."""
    if is_image:
        if "cancel_event" in llm.process_image.__code__.co_varnames:
            return llm.process_image(
                prompt,
                image_path,
                status_callback,
                enable_chat_sessions,
                sink,
                is_main=is_main,
                cancel_event=cancel_event,
            )
        return llm.process_image(
            prompt,
            image_path,
            status_callback,
            enable_chat_sessions,
            sink,
            is_main=is_main,
        )
    else:
        if "cancel_event" in llm.process_text.__code__.co_varnames:
            return llm.process_text(
                prompt,
                status_callback,
                enable_chat_sessions,
                sink,
                is_main=is_main,
                cancel_event=cancel_event,
            )
        return llm.process_text(
            prompt, status_callback, enable_chat_sessions, sink, is_main=is_main
        )


def _store_llm_result(
    results: dict,
    lock: threading.Lock,
    ans: str,
    is_main: bool,
    main_success: list,
):
    """Store LLM result in results dict."""
    with lock:
        if isinstance(ans, str) and ans.startswith("Error"):
            if is_main:
                results["main_error"] = ans
            else:
                results["fallback_error"] = ans
        else:
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
    image_path: Optional[str],
    is_image: bool,
    status_callback,
    enable_chat_sessions: bool,
    sink: Sink,
    is_main: bool,
    results: dict,
    lock: threading.Lock,
    main_success: list,
    main_finished: threading.Event,
    cancel_event: threading.Event = None,
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
    finally:
        if is_main:
            main_finished.set()


def _determine_final_result(
    results: dict, main_success: list, fallback_thread: threading.Thread
) -> str:
    """Determine the final result from main and fallback results."""
    if main_success[0] and "main" in results:
        return results["main"]
    else:
        fallback_thread.join()
        if "fallback" in results:
            return results["fallback"]
        elif "main_error" in results:
            return f"Error processing main: {results['main_error']}, Fallback error: {results.get('fallback_error', 'unknown')}"
        else:
            return "Error processing with both models."


def _save_to_session(
    session_manager,
    prompt: str,
    image_path: Optional[str | list[str]],
    final_result: str,
    extracted_text: Optional[str],
    source_name: str,
):
    """Save the interaction to session manager."""
    if session_manager and final_result and not final_result.startswith("Error"):
        try:
            session_manager.append_interaction(
                prompt,
                image_path,
                final_result,
                extracted_text,
                source_name=source_name,
            )
        except Exception as e:
            print(f"Failed to append to session manager: {e}")


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
    cancel_event: threading.Event = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> str:
    if cancel_event is None:
        cancel_event = threading.Event()

    pipeline_start_time = time.time()
    source_name = getattr(source, "name", "unknown")

    print(f"Using source: {source.__class__.__name__}")

    # 1. Text/Image Retrieval
    try:
        extracted_text, source_image_path, is_image = _retrieve_data_from_source(
            source, coords, text, status_callback, cancel_event
        )
    except Exception as e:
        return str(e)

    if cancel_event.is_set():
        return PIPELINE_CANCELLED_MSG

    combined_image_paths = []
    if image_paths:
        combined_image_paths.extend(image_paths)
    if source_image_path:
        combined_image_paths.append(source_image_path)
    if not combined_image_paths:
        combined_image_paths = None
    elif len(combined_image_paths) == 1:
        combined_image_paths = combined_image_paths[0]

    # 2. Prompt Augmentation
    include_transcribed = True
    if session_manager:
        ctx = session_manager.get_context_config()
        include_transcribed = ctx.get("include_transcribed_text", True)
        
    prompt_extracted = extracted_text if include_transcribed else None
    prompt = _build_prompt(prompt_text, prompt_extracted)
    print(f"Submitted prompt: {prompt}")

    # Store prompt for IDE context injection (Open in IDE prepends it as a comment)
    from core.output import set_last_user_prompt
    set_last_user_prompt(prompt)

    if cancel_event.is_set():
        return PIPELINE_CANCELLED_MSG

    # 3. LLM Execution (with Fallback Concurrency)
    if not fallback_llm:
        final_result = _execute_llm_without_fallback(
            llm,
            prompt,
            combined_image_paths if isinstance(combined_image_paths, str) else None,
            is_image,
            status_callback,
            enable_chat_sessions,
            sink,
            cancel_event,
            max_retries=max_retries,
            base_delay=base_delay,
        )
        _save_to_session(
            session_manager, prompt, combined_image_paths, final_result, extracted_text, source_name
        )
        return final_result

    results = {}
    lock = threading.Lock()

    main_started = [False]
    fallback_started = [False]
    main_success = [False]
    main_finished = threading.Event()

    concurrent_sink = (
        ConcurrentSinkWrapper(
            sink,
            main_finished,
            main_started,
            fallback_started,
            main_success,
            cancel_event,
        )
        if sink
        else None
    )

    main_thread = threading.Thread(
        target=_run_llm_thread,
        args=(
            llm,
            prompt,
            combined_image_paths if isinstance(combined_image_paths, str) else None,
            is_image,
            status_callback,
            enable_chat_sessions,
            concurrent_sink,
            True,
            results,
            lock,
            main_success,
            main_finished,
            cancel_event,
            max_retries,
            base_delay,
        ),
        daemon=True,
    )

    fallback_thread = threading.Thread(
        target=_run_llm_thread,
        args=(
            fallback_llm,
            prompt,
            combined_image_paths if isinstance(combined_image_paths, str) else None,
            is_image,
            None,
            enable_chat_sessions,
            concurrent_sink,
            False,
            results,
            lock,
            main_success,
            main_finished,
            cancel_event,
            max_retries,
            base_delay,
        ),
        daemon=True,
    )

    main_thread.start()
    fallback_thread.start()

    main_thread.join()

    if cancel_event.is_set():
        return PIPELINE_CANCELLED_MSG

    elapsed_ms = (time.time() - pipeline_start_time) * 1000
    print(f"[Pipeline] Main thread finished processing in {elapsed_ms:.2f} ms")

    final_result = _determine_final_result(results, main_success, fallback_thread)

    _save_to_session(
        session_manager, prompt, combined_image_paths, final_result, extracted_text, source_name
    )

    return final_result
