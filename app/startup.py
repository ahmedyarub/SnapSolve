"""Application startup — Qt initialization, config loading, and orchestration.

This module also performs early platform-specific setup (DPI awareness,
console control handler) at import time so it runs before any Qt or
library code.
"""
import logging
import os
import platform
import sys
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from app import state
from app.config_validation import validate_config
from app.engine_init import (
    _initialize_ocr_engine,
    _initialize_llm_engines,
    _perform_llm_warmup,
    _initialize_audio_components,
)
from app.handlers.audio import handle_start_record, handle_stop_record
from app.handlers.cancel import handle_cancel
from app.handlers.capture import handle_capture
from app.handlers.multi_capture import handle_multi_capture, handle_end_multi_capture
from app.handlers.navigation import handle_open_context_manager
from app.handlers.periodic_screenshots import handle_toggle_periodic_screenshots
from app.handlers.session import handle_toggle_chat_sessions
from app.handlers.source import handle_cycle_source, handle_reselect
from app.handlers.text import handle_text_submit
from app.hotkeys import _register_keyboard_shortcuts
from app.state import exit_app
from app.tray import _setup_tray_or_console_mode
from config.settings import get_config, save_config, load_profiles, load_prompts
from core.output import (
    set_hide_from_capture,
    set_active_source_ui,
    set_app_callbacks,
    toggle_control_panel,
    set_chat_sessions_btn_state,
    set_periodic_screenshots_btn_state,
)
from core.remote_control_server import start_remote_control_server
from core.session_manager import SessionManager
from core.sources import (
    ScreenshotSource,
    TextSource,
    SoundSource,
    get_active_source_instance,
    set_active_source_instance,
)
from ui.selector import get_coordinates

# ---------------------------------------------------------------------------
# Early platform setup (runs at import time)
# ---------------------------------------------------------------------------
if platform.system() == "Windows":
    import ctypes

    try:
        SetProcessDpiAwareness = getattr(ctypes.windll.shcore, "SetProcessDpiAwareness")
        SetProcessDpiAwareness(2)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")

    # Register a console control handler BEFORE any library (keyboard, Qt,
    # pystray) has a chance to install its own.  This ensures PyCharm's Stop
    # button (which sends CTRL_C_EVENT or CTRL_BREAK_EVENT) terminates the
    # process immediately via os._exit().
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def _console_ctrl_handler(ctrl_type):
        # CTRL_C_EVENT=0, CTRL_BREAK_EVENT=1, CTRL_CLOSE_EVENT=2,
        # CTRL_LOGOFF_EVENT=5, CTRL_SHUTDOWN_EVENT=6
        os._exit(0)
        return True  # pragma: no cover

    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, True)


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------
def _initialize_qt_app():
    """Initialize PyQt application."""
    app = QApplication.instance()
    if not app:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    return app


def _load_config_and_profiles():
    """Load configuration and profiles."""
    config = get_config()
    profiles = load_profiles()
    prompts = load_prompts()

    active_profile_id = config.get("active_profile_id", "prof1")
    active_profile = next(
        (p for p in profiles if p.get("id") == active_profile_id),
        profiles[0] if profiles else {},
    )

    prompt_id = active_profile.get("prompt_id", "default")
    active_prompt = next(
        (p for p in prompts if p.get("id") == prompt_id), prompts[0] if prompts else {}
    )
    active_prompt_text = active_prompt.get(
        "text", "answer the following question quickly and briefly"
    )

    return config, active_profile, active_prompt_text


def _initialize_session_manager(config):
    """Initialize session manager."""
    manager = SessionManager(config)
    return manager


def _setup_active_source(config, manager):
    """Set up the active source based on configuration."""
    default_source = config.get("default_source", "text")
    if default_source == "image":
        set_active_source_instance(ScreenshotSource())
    elif default_source == "audio":
        set_active_source_instance(SoundSource(config, session_manager=manager))
    else:
        set_active_source_instance(TextSource())
    return get_active_source_instance()


def _setup_ui_callbacks(config, active_profile, active_prompt_text, session_manager):
    """Set up UI callbacks."""
    callbacks = {
        "capture": lambda: handle_capture(config, active_profile, active_prompt_text),
        "reselect": lambda: handle_reselect(config),
        "multi_capture": lambda: handle_multi_capture(config, active_profile),
        "end_multi_capture": lambda: handle_end_multi_capture(
            config, active_profile, active_prompt_text
        ),
        "cancel": handle_cancel,
        "toggle_chat_sessions": lambda: handle_toggle_chat_sessions(config, active_profile),
        "cycle_source": lambda: handle_cycle_source(config, active_profile),
        "text_submit": lambda text: handle_text_submit(config, active_profile, text),
        "start_record": lambda enable_transcription: handle_start_record(
            config, enable_transcription
        ),
        "stop_record": lambda is_long_press: handle_stop_record(
            config, active_profile, active_prompt_text, is_long_press
        ),
        "open_context_manager": lambda: handle_open_context_manager(session_manager),
        "toggle_periodic_screenshots": lambda: handle_toggle_periodic_screenshots(config),
    }
    return callbacks


def _initialize_ui(config, active_source, callbacks):
    """Initialize UI manager and set callbacks."""
    from core.output import init_ui_manager

    init_ui_manager()
    set_hide_from_capture(config.get("hide_from_capture", False))
    set_app_callbacks(callbacks)

    set_active_source_ui(
        active_source.name if active_source else "text",
        opacity=config.get("opacity", 0.8),
    )

    if config.get("show_control_panel", False):
        toggle_control_panel(True)


def _handle_coordinates_setup(config, active_source):
    """Handle coordinates setup if needed."""
    if (
        active_source
        and active_source.name == "image"
        and not config.get("coordinates")
    ):
        print("Coordinates not found in config. Launching coordinate selector...")
        coords = get_coordinates()
        if coords:
            config["coordinates"] = coords
            save_config(config)
            print(f"Coordinates saved: {coords}")
        else:
            print("No coordinates selected. Exiting.")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Application entry point — initialize everything and start the Qt event loop."""
    # Configure logging early
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Initializing Screen Capture & Gemini QA App...")

    app = _initialize_qt_app()

    config, active_profile, active_prompt_text = _load_config_and_profiles()

    validate_config(active_profile)

    state.session_manager = _initialize_session_manager(config)

    active_source = _setup_active_source(config, state.session_manager)

    callbacks = _setup_ui_callbacks(config, active_profile, active_prompt_text, state.session_manager)

    _initialize_ui(config, active_source, callbacks)

    _handle_coordinates_setup(config, active_source)

    print("Checking engine pre-initialization...")

    state.ocr_engine_instance = _initialize_ocr_engine(active_profile, config)

    if isinstance(active_source, ScreenshotSource):
        active_source.ocr_engine = state.ocr_engine_instance
        set_active_source_instance(active_source)

    state.llm_engine_instance, state.fallback_llm_engine_instance = _initialize_llm_engines(
        active_profile, config, state.session_manager
    )

    _perform_llm_warmup(config, state.llm_engine_instance, state.fallback_llm_engine_instance)

    state.audio_sink_instance = _initialize_audio_components(
        config, state.session_manager, state.cancel_event
    )

    if "enable_chat_sessions" in config:
        active_profile["enable_chat_sessions"] = config["enable_chat_sessions"]

    set_chat_sessions_btn_state(active_profile.get("enable_chat_sessions", True))

    # Initialize periodic screenshot service
    from core.periodic_screenshots import PeriodicScreenshotService  # noqa: PLC0415

    state.periodic_screenshot_service = PeriodicScreenshotService(config, state.session_manager)
    if config.get("periodic_screenshots_enabled", False):
        state.periodic_screenshot_service.start()
    set_periodic_screenshots_btn_state(config.get("periodic_screenshots_enabled", False))

    # Start remote control server if enabled
    if config.get("enable_remote_control", False):
        remote_host = config.get("remote_control_host", "0.0.0.0")
        remote_port = config.get("remote_control_port", 8080)
        try:
            start_remote_control_server(remote_host, remote_port, config)
        except Exception as remote_error:
            print(f"Failed to start remote control server: {remote_error}")

    _register_keyboard_shortcuts(config, active_profile, active_prompt_text)

    _setup_tray_or_console_mode(config, exit_app)

    print("Initialization done.")
    sys.exit(app.exec())
