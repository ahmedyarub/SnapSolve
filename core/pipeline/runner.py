"""Pipeline runner and factory for building standard processor chains.

The :class:`Pipeline` class runs a list of :class:`Processor` objects
sequentially, passing frames through until a terminal frame is reached.

:func:`build_pipeline` constructs the standard ``Source → Prompt → LLM → Sink
→ SessionSave`` chain from the same arguments accepted by the legacy
``process_pipeline()`` function.
"""
import logging
import threading
import time
from typing import Optional

from core.llm.base import LLMEngine
from core.sinks.base import Sink
from core.sources.base import Source
from .frames import CancelledFrame, ErrorFrame, Frame
from .processors import (
    ConcurrentLLMProcessor,
    LLMProcessor,
    Processor,
    PromptBuilderProcessor,
    SessionSaveProcessor,
    SinkProcessor,
    SourceProcessor,
)

logger = logging.getLogger(__name__)


class Pipeline:
    """Runs a chain of :class:`Processor` objects sequentially.

    Stops early if any processor returns an ``ErrorFrame`` or
    ``CancelledFrame``.
    """

    def __init__(self, processors: list[Processor]):
        self.processors = list(processors)

    def run(self, frame: Frame) -> Frame:
        """Execute the pipeline, passing *frame* through each processor."""
        for proc in self.processors:
            frame = proc.process(frame)
            if isinstance(frame, (ErrorFrame, CancelledFrame)):
                break
        return frame


def build_pipeline(
    source: Source,
    llm: LLMEngine,
    prompt_text: str,
    status_callback=None,
    session_manager=None,
    enable_chat_sessions: bool = True,
    sink: Optional[Sink] = None,
    fallback_llm: Optional[LLMEngine] = None,
    coords=None,
    text: Optional[str] = None,
    image_paths: Optional[list[str]] = None,
    cancel_event: Optional[threading.Event] = None,
    max_retries: int = 3,
    base_delay: float = 5.0,
) -> Pipeline:
    """Build the standard composable pipeline from legacy arguments.

    Returns a :class:`Pipeline` ready to be executed via ``pipeline.run(frame)``.
    """
    processors: list[Processor] = []

    # 1. Source extraction
    processors.append(
        SourceProcessor(
            source=source,
            coords=coords,
            text=text,
            status_callback=status_callback,
            image_paths=image_paths,
        )
    )

    # 2. Prompt building
    processors.append(PromptBuilderProcessor(prompt_text=prompt_text))

    # 3. LLM execution (with or without fallback)
    if fallback_llm:
        processors.append(
            ConcurrentLLMProcessor(
                llm=llm,
                fallback_llm=fallback_llm,
                status_callback=status_callback,
                enable_chat_sessions=enable_chat_sessions,
                sink=sink,
                max_retries=max_retries,
                base_delay=base_delay,
            )
        )
    else:
        processors.append(
            LLMProcessor(
                llm=llm,
                status_callback=status_callback,
                enable_chat_sessions=enable_chat_sessions,
                sink=sink,
                max_retries=max_retries,
                base_delay=base_delay,
            )
        )

    # 4. Session save
    processors.append(SessionSaveProcessor(session_manager=session_manager))

    return Pipeline(processors)
