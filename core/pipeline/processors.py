"""Processor base class and concrete processor implementations.

Each processor receives a :class:`Frame`, performs a single stage of work,
and returns a new frame.  ``ErrorFrame`` and ``CancelledFrame`` are passed
through unchanged to short-circuit the pipeline.
"""
import abc
import logging
import threading
import time
from typing import Optional

from core.llm.base import LLMEngine
from core.sinks.base import Sink
from core.sources.base import Source
from .frames import (
    CancelledFrame,
    ErrorFrame,
    Frame,
    LLMResponseFrame,
    PromptFrame,
    SourceFrame,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
class Processor(abc.ABC):
    """A single stage in the composable pipeline."""

    @abc.abstractmethod
    def process(self, frame: Frame) -> Frame:
        """Transform *frame* into the next frame in the pipeline.

        Implementations **must** check for ``ErrorFrame`` / ``CancelledFrame``
        and return them unchanged.
        """


# ---------------------------------------------------------------------------
# Helpers shared by processors (thin wrappers around pipeline.py internals)
# ---------------------------------------------------------------------------
def _check_cancelled(frame: Frame) -> Optional[CancelledFrame]:
    """Return a ``CancelledFrame`` if the cancel event is set, else ``None``."""
    if frame.cancel_event and frame.cancel_event.is_set():
        return CancelledFrame(cancel_event=frame.cancel_event, metadata=frame.metadata)
    return None


def _is_terminal(frame: Frame) -> bool:
    """Return ``True`` if *frame* is a terminal (error / cancelled) frame."""
    return isinstance(frame, (ErrorFrame, CancelledFrame))


# ---------------------------------------------------------------------------
# SourceProcessor
# ---------------------------------------------------------------------------
class SourceProcessor(Processor):
    """Extracts text or image data from a :class:`Source`.

    Wraps the existing ``_retrieve_data_from_source`` logic.
    """

    def __init__(
        self,
        source: Source,
        coords=None,
        text: Optional[str] = None,
        status_callback=None,
        image_paths: Optional[list[str]] = None,
    ):
        self.source = source
        self.coords = coords
        self.text = text
        self.status_callback = status_callback
        self.image_paths = image_paths

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        from .pipeline import _retrieve_data_from_source

        try:
            extracted_text, source_image_path, is_image = _retrieve_data_from_source(
                self.source,
                self.coords,
                self.text,
                self.status_callback,
                frame.cancel_event,
            )
        except Exception as exc:
            return ErrorFrame(
                cancel_event=frame.cancel_event,
                metadata=frame.metadata,
                error=str(exc),
            )

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        # Merge image paths from source and externally-provided paths
        combined_image_paths: Optional[str | list[str]] = None
        paths: list[str] = []
        if self.image_paths:
            paths.extend(self.image_paths)
        if source_image_path:
            paths.append(source_image_path)
        if paths:
            combined_image_paths = paths[0] if len(paths) == 1 else paths

        # For backward compat — only pass a single string to downstream
        image_path_str: Optional[str] = None
        if isinstance(combined_image_paths, str):
            image_path_str = combined_image_paths

        source_name = getattr(self.source, "name", "unknown")
        return SourceFrame(
            cancel_event=frame.cancel_event,
            metadata={**frame.metadata, "combined_image_paths": combined_image_paths},
            extracted_text=extracted_text,
            image_path=image_path_str,
            is_image=is_image,
            source_name=source_name,
        )


# ---------------------------------------------------------------------------
# PromptBuilderProcessor
# ---------------------------------------------------------------------------
class PromptBuilderProcessor(Processor):
    """Builds the final LLM prompt from the prompt text and extracted text.

    Also stores the prompt for IDE context injection.
    """

    def __init__(self, prompt_text: str):
        self.prompt_text = prompt_text

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        if not isinstance(frame, SourceFrame):
            return ErrorFrame(
                cancel_event=frame.cancel_event,
                metadata=frame.metadata,
                error="PromptBuilderProcessor expected a SourceFrame.",
            )

        from .pipeline import _build_prompt

        prompt = _build_prompt(self.prompt_text, frame.extracted_text)
        print(f"Submitted prompt: {prompt}")

        # Store prompt for IDE context injection
        from core.output import set_last_user_prompt
        set_last_user_prompt(prompt)

        return PromptFrame(
            cancel_event=frame.cancel_event,
            metadata=frame.metadata,
            prompt=prompt,
            image_path=frame.image_path,
            is_image=frame.is_image,
            source_name=frame.source_name,
            extracted_text=frame.extracted_text,
        )


# ---------------------------------------------------------------------------
# LLMProcessor (single engine, no fallback)
# ---------------------------------------------------------------------------
class LLMProcessor(Processor):
    """Calls a single LLM engine with retry logic.

    Wraps ``_execute_llm_without_fallback``.
    """

    def __init__(
        self,
        llm: LLMEngine,
        status_callback=None,
        enable_chat_sessions: bool = True,
        sink: Optional[Sink] = None,
        max_retries: int = 3,
        base_delay: float = 5.0,
    ):
        self.llm = llm
        self.status_callback = status_callback
        self.enable_chat_sessions = enable_chat_sessions
        self.sink = sink
        self.max_retries = max_retries
        self.base_delay = base_delay

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        if not isinstance(frame, PromptFrame):
            return ErrorFrame(
                cancel_event=frame.cancel_event,
                metadata=frame.metadata,
                error="LLMProcessor expected a PromptFrame.",
            )

        from .pipeline import _execute_llm_without_fallback

        try:
            result = _execute_llm_without_fallback(
                self.llm,
                frame.prompt,
                frame.image_path,
                frame.is_image,
                self.status_callback,
                self.enable_chat_sessions,
                self.sink,
                frame.cancel_event,
                max_retries=self.max_retries,
                base_delay=self.base_delay,
            )
        except Exception as exc:
            return ErrorFrame(
                cancel_event=frame.cancel_event,
                metadata=frame.metadata,
                error=str(exc),
            )

        return LLMResponseFrame(
            cancel_event=frame.cancel_event,
            metadata=frame.metadata,
            result=result,
            prompt=frame.prompt,
            image_path=frame.image_path,
            extracted_text=frame.extracted_text,
            source_name=frame.source_name,
        )


# ---------------------------------------------------------------------------
# ConcurrentLLMProcessor (main + fallback)
# ---------------------------------------------------------------------------
class ConcurrentLLMProcessor(Processor):
    """Runs main and fallback LLM engines concurrently.

    Wraps the threaded execution logic and ``ConcurrentSinkWrapper``.
    """

    def __init__(
        self,
        llm: LLMEngine,
        fallback_llm: LLMEngine,
        status_callback=None,
        enable_chat_sessions: bool = True,
        sink: Optional[Sink] = None,
        max_retries: int = 3,
        base_delay: float = 5.0,
    ):
        self.llm = llm
        self.fallback_llm = fallback_llm
        self.status_callback = status_callback
        self.enable_chat_sessions = enable_chat_sessions
        self.sink = sink
        self.max_retries = max_retries
        self.base_delay = base_delay

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        if not isinstance(frame, PromptFrame):
            return ErrorFrame(
                cancel_event=frame.cancel_event,
                metadata=frame.metadata,
                error="ConcurrentLLMProcessor expected a PromptFrame.",
            )

        from .pipeline import (
            ConcurrentSinkWrapper,
            _run_llm_thread,
            _determine_final_result,
        )

        results: dict = {}
        lock = threading.Lock()
        main_started = [False]
        fallback_started = [False]
        main_success = [False]
        main_finished = threading.Event()

        concurrent_sink = (
            ConcurrentSinkWrapper(
                self.sink,
                main_finished,
                main_started,
                fallback_started,
                main_success,
                frame.cancel_event,
            )
            if self.sink
            else None
        )

        main_thread = threading.Thread(
            target=_run_llm_thread,
            args=(
                self.llm,
                frame.prompt,
                frame.image_path,
                frame.is_image,
                self.status_callback,
                self.enable_chat_sessions,
                concurrent_sink,
                True,
                results,
                lock,
                main_success,
                main_finished,
                frame.cancel_event,
                self.max_retries,
                self.base_delay,
            ),
            daemon=True,
        )

        fallback_thread = threading.Thread(
            target=_run_llm_thread,
            args=(
                self.fallback_llm,
                frame.prompt,
                frame.image_path,
                frame.is_image,
                None,
                self.enable_chat_sessions,
                concurrent_sink,
                False,
                results,
                lock,
                main_success,
                main_finished,
                frame.cancel_event,
                self.max_retries,
                self.base_delay,
            ),
            daemon=True,
        )

        main_thread.start()
        fallback_thread.start()
        main_thread.join()

        cancelled = _check_cancelled(frame)
        if cancelled:
            return cancelled

        final_result = _determine_final_result(results, main_success, fallback_thread)

        return LLMResponseFrame(
            cancel_event=frame.cancel_event,
            metadata=frame.metadata,
            result=final_result,
            prompt=frame.prompt,
            image_path=frame.image_path,
            extracted_text=frame.extracted_text,
            source_name=frame.source_name,
        )


# ---------------------------------------------------------------------------
# SinkProcessor
# ---------------------------------------------------------------------------
class SinkProcessor(Processor):
    """Calls ``sink.finish()`` after LLM execution completes."""

    def __init__(self, sink: Optional[Sink] = None):
        self.sink = sink

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        if self.sink and hasattr(self.sink, "finish"):
            self.sink.finish()

        return frame


# ---------------------------------------------------------------------------
# SessionSaveProcessor
# ---------------------------------------------------------------------------
class SessionSaveProcessor(Processor):
    """Persists the interaction to the session manager."""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def process(self, frame: Frame) -> Frame:
        if _is_terminal(frame):
            return frame

        if not isinstance(frame, LLMResponseFrame):
            return frame

        from .pipeline import _save_to_session

        image_path = frame.metadata.get("combined_image_paths", frame.image_path)
        _save_to_session(
            self.session_manager,
            frame.prompt,
            image_path,
            frame.result,
            frame.extracted_text,
            frame.source_name,
        )

        return frame
