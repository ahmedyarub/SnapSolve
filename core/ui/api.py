"""Public API — thread-safe functions called from background threads to interact with the UI."""
import logging
import queue
import threading

from PyQt6.QtWidgets import QApplication

from core.ui.signals import ui_signals, _app_callbacks


def set_app_callbacks(callbacks):
    # Mutate in-place so every module that imported a reference to the
    # original dict object sees the updated callbacks.
    from core.ui.signals import _app_callbacks
    _app_callbacks.clear()
    _app_callbacks.update(callbacks)


def set_hide_from_capture(hide: bool):
    """Enable or disable capture-hiding globally for all overlay widgets."""
    from core.ui.manager import ui_manager
    if ui_manager is not None:
        ui_manager.set_hide_from_capture(hide)


# --- Public API called from background threads ---
def toggle_control_panel(show=None):
    ui_signals.toggle_panel.emit(show)


def toggle_all_widgets():
    """Hide or unhide all overlay widgets."""
    ui_signals.toggle_all_visibility.emit()


def update_multi_state(in_progress):
    ui_signals.set_multi_state.emit(in_progress)


def set_active_source_ui(source_name, opacity=0.8):
    ui_signals.set_source.emit(source_name, opacity)


def set_app_processing_state(is_processing):
    ui_signals.set_processing_state.emit(is_processing)


def show_popup(text, auto_close=5000, opacity=0.8, is_result=False):
    ui_signals.show_popup.emit(
        {
            "text": text,
            "auto_close": auto_close,
            "opacity": opacity,
            "is_result": is_result,
        }
    )


def close_popup():
    ui_signals.close_popup.emit()


def share_response_screenshot():
    ui_signals.capture_popup_screenshot.emit()

def set_chat_sessions_btn_state(enabled: bool):
    ui_signals.update_chat_sessions_btn.emit(enabled)


def send_ocr_text_to_input(text: str):
    """Send OCR'd text to the text input widget (thread-safe)."""
    ui_signals.ocr_text_to_input.emit(text)


def is_autosubmit_enabled() -> bool:
    """Check if the Autosubmit checkbox is checked on the control panel.

    Safe to call from any thread — reads the widget state directly.
    Returns True (default) when the panel is not available.
    """
    from core.ui.manager import ui_manager
    if ui_manager is not None and ui_manager.panel is not None:
        return ui_manager.panel.chk_autosubmit.isChecked()
    return True


def show_subtitle(text: str):
    """Show a subtitle line with real-time transcription."""
    logger = logging.getLogger(__name__)
    logger.info(f"show_subtitle called with text: {text}")
    ui_signals.show_subtitle.emit(text)
    logger.info("show_subtitle signal emitted")


def update_subtitle(text: str, append: bool = False):
    """Update the most recent subtitle line instead of creating a new one."""
    logger = logging.getLogger(__name__)
    logger.info(f"update_subtitle called with text: {text}, append: {append}")
    ui_signals.update_subtitle.emit(text, append)
    logger.info("update_subtitle signal emitted")


def clear_subtitles():
    """Clear all subtitle lines."""
    ui_signals.clear_subtitles.emit()


def get_subtitle_text(index: int) -> str:
    """Get the text of a subtitle by index (1 is newest)."""
    from core.ui.manager import ui_manager
    if ui_manager is not None:
        return ui_manager.get_subtitle_text(index)
    return ""


def output_result(text, output_modes, auto_close=False, opacity=0.8):
    if not output_modes:
        output_modes = ["popup"]

    # Audio is now handled by the AudioSink in the pipeline

    if "popup" in output_modes:
        show_popup(
            text,
            auto_close=5000 if auto_close else None,
            opacity=opacity,
            is_result=True,
        )


def get_active_source():
    from core.sources import get_active_source_instance

    app = QApplication.instance()
    if app and app.thread() == threading.current_thread():
        return get_active_source_instance()

    q = queue.Queue()
    ui_signals.request_active_source.emit(q)
    return q.get()
