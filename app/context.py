"""What the running app shares, passed to every handler instead of module globals.

Handlers read ``ctx.profile`` and ``ctx.prompt_text`` when they run, not when
they were registered, so switching the profile at runtime takes effect at once.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "claude-opus-5-5"
DEFAULT_PROMPT_TEXT = "answer the following question quickly and briefly"


@dataclass
class AppContext:
    config: dict
    profile: dict = field(default_factory=dict)
    prompt_text: str = DEFAULT_PROMPT_TEXT

    session_manager: Any = None  # SessionManager
    llm_engine: Any = None  # LLMEngine
    fallback_llm_engine: Any = None  # LLMEngine | None
    ocr_engine: Any = None  # OCREngine | None
    correction_engine: Any = None  # CorrectionEngine | None
    audio_sink: Any = None  # AudioSink
    periodic_screenshot_service: Any = None  # PeriodicScreenshotService

    cancel_event: threading.Event = field(default_factory=threading.Event)
    is_running: bool = True
    # Set once the profile's engines are built (they load in the background).
    ready: threading.Event = field(default_factory=threading.Event)

    # Multi-capture
    is_multi_capturing: bool = False
    multi_capture_texts: list[str] = field(default_factory=list)
    multi_capture_images: list[str] = field(default_factory=list)

    _processing: bool = False
    _processing_lock: threading.Lock = field(default_factory=threading.Lock)
    # Held while the profile's engines are rebuilt; requests wait for it.
    engines_lock: threading.RLock = field(default_factory=threading.RLock)

    # ------------------------------------------------------------------ #
    #  One request at a time
    # ------------------------------------------------------------------ #

    @property
    def is_processing(self) -> bool:
        return self._processing

    def try_start_processing(self) -> bool:
        """Claim the app for one request; False if another one is running.

        Hotkeys, the panel and the remote API can fire at the same moment; the
        lock makes exactly one of them win.
        """
        with self._processing_lock:
            if self._processing:
                return False
            self._processing = True
        _notify_processing(True)
        return True

    def finish_processing(self) -> None:
        with self._processing_lock:
            self._processing = False
            self.cancel_event.clear()
        _notify_processing(False)

    def reset_multi_capture(self) -> None:
        self.is_multi_capturing = False
        self.multi_capture_texts = []
        self.multi_capture_images = []

    # ------------------------------------------------------------------ #
    #  Profile helpers
    # ------------------------------------------------------------------ #

    @property
    def main_model(self) -> str:
        return self.profile.get("model", DEFAULT_MODEL_NAME)

    @property
    def fallback_model(self) -> str | None:
        return model_or_none(self.profile.get("fallback_model"))


def model_or_none(value: Any) -> str | None:
    """Profiles mark "no model" as None, "" or the string "None"."""
    if not value or str(value).strip().lower() == "none":
        return None
    return str(value)


def _notify_processing(processing: bool) -> None:
    from core.output import set_app_processing_state

    set_app_processing_state(processing)
