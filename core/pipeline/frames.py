"""Typed data containers (frames) that flow through the composable pipeline.

Each frame represents the output of a pipeline stage.  Processors receive a
frame, transform it, and return a new frame for the next processor in the
chain.  ``ErrorFrame`` and ``CancelledFrame`` short-circuit the pipeline —
subsequent processors pass them through unchanged.
"""
from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass
class Frame:
    """Base frame — the seed passed into the first processor."""
    cancel_event: threading.Event
    metadata: dict = field(default_factory=dict)


@dataclass
class SourceFrame(Frame):
    """Output of :class:`SourceProcessor` — raw data from a ``Source``."""
    extracted_text: Optional[str] = None
    image_path: Optional[str] = None
    is_image: bool = False
    source_name: str = "unknown"


@dataclass
class PromptFrame(Frame):
    """Output of :class:`PromptBuilderProcessor` — augmented LLM prompt."""
    prompt: str = ""
    image_path: Optional[str] = None
    is_image: bool = False
    source_name: str = "unknown"
    extracted_text: Optional[str] = None


@dataclass
class LLMResponseFrame(Frame):
    """Output of :class:`LLMProcessor` / :class:`ConcurrentLLMProcessor`."""
    result: str = ""
    prompt: str = ""
    image_path: Optional[str] = None
    extracted_text: Optional[str] = None
    source_name: str = "unknown"


@dataclass
class ErrorFrame(Frame):
    """Signals a pipeline error — short-circuits remaining processors."""
    error: str = ""


@dataclass
class CancelledFrame(Frame):
    """Signals pipeline cancellation."""
    message: str = "Pipeline cancelled."
