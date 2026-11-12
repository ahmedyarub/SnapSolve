"""Signal brokers, module-level globals, and tiny helpers shared across UI widgets."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


# --- Signal Broker ---
class UISignals(QObject):
    toggle_panel = pyqtSignal(object)
    set_multi_state = pyqtSignal(bool)
    set_source = pyqtSignal(str, float)
    set_processing_state = pyqtSignal(bool)
    show_popup = pyqtSignal(dict)
    close_popup = pyqtSignal()
    capture_popup_screenshot = pyqtSignal()
    request_active_source = pyqtSignal(object)
    show_subtitle = pyqtSignal(str)
    update_subtitle = pyqtSignal(str, bool)
    clear_subtitles = pyqtSignal()
    toggle_all_visibility = pyqtSignal()
    show_url_input = pyqtSignal()
    open_url = pyqtSignal(str)
    open_session_browser = pyqtSignal()
    open_context_manager = pyqtSignal()
    show_pairing = pyqtSignal()
    open_settings = pyqtSignal()
    # [(profile_id, name), ...], active profile id
    set_profiles = pyqtSignal(list, str)
    set_transcription_language = pyqtSignal(str)
    update_chat_sessions_btn = pyqtSignal(bool)
    update_periodic_screenshots_btn = pyqtSignal(bool)
    ocr_text_to_input = pyqtSignal(str)
    update_volume = pyqtSignal(int)
    # Real-time correction signals
    show_correction = pyqtSignal(dict)
    clear_corrections = pyqtSignal()
    toggle_correction_panel = pyqtSignal()


class SelectorSignals(QObject):
    request_coords = pyqtSignal(object)
    coords_ready = pyqtSignal(object)


ui_signals = UISignals()
selector_signals = SelectorSignals()
# Action name -> callable, registered by the app (see app.startup).
app_callbacks: dict[str, Callable[..., Any]] = {}
_last_user_prompt: str | None = None


def set_last_user_prompt(prompt: str | None) -> None:
    """Store the latest user prompt so it can be injected into IDE-opened files."""
    global _last_user_prompt
    _last_user_prompt = prompt


def call_action(action, *args):
    if action in app_callbacks:
        try:
            # Run callback in background thread so it doesn't block UI
            threading.Thread(
                target=app_callbacks[action], args=args, daemon=True
            ).start()
        except Exception as e:
            logger.error("Error calling %s: %s", action, e)
