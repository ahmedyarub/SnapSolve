"""Application startup — Qt initialization, config loading, and orchestration.

This module also performs early platform-specific setup (DPI awareness,
console control handler) at import time so it runs before any Qt or
library code.
"""

import logging
import os
import platform
import sys

# ---------------------------------------------------------------------------
# CRITICAL: Initialize Qt flags BEFORE any other imports!
# PyTorch DataLoader may spawn child processes on Windows which import this module.
# If external libraries (like matplotlib) instantiate QApplication before this flag
# is set, QtWebEngineWidgets will cause a fatal crash.
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    if not QApplication.instance():
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except Exception:
    pass

import threading

from app.config_validation import profile_problems
from app.context import AppContext
from app.engine_init import build_audio_sink, warm_up_llms
from app.feedback import show_status
from app.handlers.audio import handle_start_record, handle_stop_record
from app.handlers.cancel import handle_cancel
from app.handlers.capture import handle_capture
from app.handlers.multi_capture import handle_end_multi_capture, handle_multi_capture
from app.handlers.navigation import handle_open_context_manager, handle_toggle_panel
from app.handlers.periodic_screenshots import handle_toggle_periodic_screenshots
from app.handlers.session import handle_new_chat_session, handle_toggle_chat_sessions
from app.handlers.source import handle_cycle_source, handle_reselect
from app.handlers.text import handle_text_submit
from app.hotkeys import register_keyboard_shortcuts
from app.lifecycle import exit_app
from app.profiles import (
    apply_profile_engines,
    find_profile,
    prompt_text_for,
    publish_profiles,
    switch_profile,
)
from app.tray import setup_tray_or_console_mode
from config.settings import (
    CONFIG_FILE,
    PROFILES_FILE,
    PROMPTS_FILE,
    get_config,
    load_config,
    load_profiles,
    load_prompts,
    update_config_file,
)
from core.api_server import start_api_server
from core.output import (
    set_active_source_ui,
    set_app_callbacks,
    set_chat_sessions_btn_state,
    set_hide_from_capture,
    set_periodic_screenshots_btn_state,
    toggle_control_panel,
)
from core.remote_auth import generate_api_key
from core.session_manager import SessionManager
from core.sources import (
    ScreenshotSource,
    SoundSource,
    TextSource,
    get_active_source_instance,
    set_active_source_instance,
)
from core.ui.selector import get_coordinates

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Early platform setup (runs at import time)
# ---------------------------------------------------------------------------
if platform.system() == "Windows":
    import ctypes

    try:
        SetProcessDpiAwareness = ctypes.windll.shcore.SetProcessDpiAwareness
        SetProcessDpiAwareness(2)
    except Exception as dpi_error:
        logger.warning("Failed to set DPI awareness: %s", dpi_error)

    # Register a console control handler BEFORE any library (keyboard, Qt,
    # pystray) has a chance to install its own.  This ensures PyCharm's Stop
    # button (which sends CTRL_C_EVENT or CTRL_BREAK_EVENT) terminates the
    # process immediately via os._exit().
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def _console_ctrl_handler(_ctrl_type):
        # CTRL_C_EVENT=0, CTRL_BREAK_EVENT=1, CTRL_CLOSE_EVENT=2,
        # CTRL_LOGOFF_EVENT=5, CTRL_SHUTDOWN_EVENT=6
        # noinspection PyProtectedMember
        os._exit(0)

    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, True)


# ---------------------------------------------------------------------------
# Initialization helpers
# ---------------------------------------------------------------------------
def _initialize_qt_app():
    """Initialize PyQt application."""
    import PyQt6.QtWebEngineWidgets  # noqa: F401  Force early import to prevent crash

    app = QApplication.instance()
    if not app:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    return app


def _create_context() -> AppContext:
    """Config plus the active profile and its prompt (engines come later)."""
    config = get_config()
    profile = find_profile(load_profiles(), config.get("active_profile_id", "claude"))
    if "enable_chat_sessions" in config:
        profile["enable_chat_sessions"] = config["enable_chat_sessions"]
    return AppContext(
        config=config,
        profile=profile,
        prompt_text=prompt_text_for(profile, load_prompts()),
    )


def _exit_if_profile_invalid(ctx: AppContext) -> None:
    problems = profile_problems(ctx.profile)
    if not problems:
        return
    from PyQt6.QtWidgets import QMessageBox

    name = ctx.profile.get("name", ctx.profile.get("id"))
    message = (
        f"The active profile '{name}' cannot be used:\n\n- "
        + "\n- ".join(problems)
        + "\n\nFix it in config/profiles.json or in the settings (ui/config_ui.py)."
    )
    logger.error(message)
    QMessageBox.critical(None, "SnapSolve", message)
    sys.exit(1)


def _setup_active_source(ctx: AppContext):
    """Set up the active source based on configuration."""
    default_source = ctx.config.get("default_source", "text")
    if default_source == "image":
        set_active_source_instance(ScreenshotSource())
    elif default_source == "audio":
        set_active_source_instance(
            SoundSource(ctx.config, session_manager=ctx.session_manager)
        )
    else:
        set_active_source_instance(TextSource())
    return get_active_source_instance()


def _open_session_browser():
    from ui.session_browser import open_session_browser

    open_session_browser()


def _open_settings(ctx: AppContext) -> None:
    """The settings dialog (Qt thread); after a save, reload config and profile."""
    from ui.config_ui import ConfigUI

    models_path = os.path.join(os.path.dirname(CONFIG_FILE), "llm_models.json")
    dialog = ConfigUI(CONFIG_FILE, models_path, PROFILES_FILE, PROMPTS_FILE)
    if not dialog.exec():
        return

    ctx.config.update(load_config())
    # Command-line flags still win for this run.
    ctx.config.update(getattr(ctx.config, "cli_overrides", {}))
    reload_active_profile(ctx)


def reload_active_profile(ctx: AppContext) -> None:
    """Rebuild the active profile's engines from the saved profiles (background)."""

    def work():
        profile_id = ctx.config.get("active_profile_id", ctx.profile.get("id"))
        profile = find_profile(load_profiles(), profile_id)
        problems = profile_problems(profile)
        if problems:
            show_status(
                ctx.config, "Profile not reloaded:\n" + "\n".join(problems), 8000
            )
            return
        try:
            apply_profile_engines(ctx, profile, load_prompts())
        except Exception as e:
            logger.exception("Reloading the profile failed")
            show_status(ctx.config, f"Could not reload the profile: {e}", 8000)
            return
        publish_profiles(ctx)
        set_chat_sessions_btn_state(ctx.profile.get("enable_chat_sessions", True))
        show_status(ctx.config, "Settings applied", auto_close=2500)

    threading.Thread(target=work, daemon=True, name="reload-profile").start()


def _setup_ui_callbacks(ctx: AppContext):
    """Callbacks the UI and the remote API invoke by name."""
    return {
        "capture": lambda: handle_capture(ctx),
        "reselect": lambda: handle_reselect(ctx),
        "multi_capture": lambda: handle_multi_capture(ctx),
        "end_multi_capture": lambda: handle_end_multi_capture(ctx),
        "cancel": lambda: handle_cancel(ctx),
        "toggle_chat_sessions": lambda: handle_toggle_chat_sessions(ctx),
        "new_chat_session": lambda: handle_new_chat_session(ctx),
        "toggle_panel": handle_toggle_panel,
        "cycle_source": lambda: handle_cycle_source(ctx),
        "text_submit": lambda text: handle_text_submit(ctx, text),
        "start_record": lambda enable_transcription: handle_start_record(
            ctx, enable_transcription
        ),
        "stop_record": lambda is_long_press: handle_stop_record(ctx, is_long_press),
        "open_context_manager": lambda: handle_open_context_manager(
            ctx.session_manager
        ),
        "toggle_periodic_screenshots": lambda: handle_toggle_periodic_screenshots(ctx),
        "switch_profile": lambda profile_id: switch_profile(ctx, profile_id),
        # These two run on the Qt thread (the UI manager calls them from slots).
        "open_session_browser": _open_session_browser,
        "open_settings": lambda: _open_settings(ctx),
    }


def _initialize_ui(ctx: AppContext, active_source) -> None:
    """Initialize UI manager and set callbacks."""
    from core.output import init_ui_manager

    init_ui_manager()
    set_hide_from_capture(ctx.config.get("hide_from_capture", False))
    set_app_callbacks(_setup_ui_callbacks(ctx))

    set_active_source_ui(
        active_source.name if active_source else "text",
        opacity=ctx.config.get("opacity", 0.8),
    )
    if ctx.config.get("show_control_panel", False):
        toggle_control_panel(True)


def _handle_coordinates_setup(ctx: AppContext, active_source) -> None:
    """Ask for the capture region on first use of the image source."""
    if (
        active_source
        and active_source.name == "image"
        and not ctx.config.get("coordinates")
    ):
        logger.info("No capture region configured; launching the selector...")
        coords = get_coordinates()
        if not coords:
            logger.error("No coordinates selected. Exiting.")
            sys.exit(1)
        ctx.config["coordinates"] = coords
        update_config_file({"coordinates": coords})


def _start_api_server(ctx: AppContext) -> None:
    config = ctx.config
    if not config.get("enable_api_server", False):
        return
    if not config.get("api_server_key"):
        # The API controls the mouse and keyboard; it never runs without a key.
        config["api_server_key"] = generate_api_key()
        update_config_file({"api_server_key": config["api_server_key"]})
        logger.info("Generated a remote-control API key. Pair a phone from the panel.")

    def status():
        return {"ocr": type(ctx.ocr_engine).__name__ if ctx.ocr_engine else "None"}

    try:
        start_api_server(
            config.get("api_server_host", "127.0.0.1"),
            config.get("api_server_port", 3031),
            config,
            status_provider=status,
        )
    except Exception:
        logger.exception("Failed to start the API server")


def _load_engines_in_background(ctx: AppContext) -> None:
    """Build the profile's engines (OCR load, LLM warmup) without blocking the UI.

    Requests made before this finishes are refused with "Still starting up".
    """

    def work() -> None:
        try:
            apply_profile_engines(ctx, ctx.profile, load_prompts())
        except Exception as e:
            logger.exception("Engine initialization failed")
            show_status(ctx.config, f"Startup failed: {e}", auto_close=10000)
            return
        ctx.ready.set()
        warm_up_llms(ctx.config, ctx.llm_engine, ctx.fallback_llm_engine)
        logger.info("Ready.")
        show_status(
            ctx.config, f"Ready ({ctx.profile.get('name', '')})", auto_close=2500
        )

    threading.Thread(target=work, daemon=True, name="engine-init").start()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main():
    """Application entry point — initialize everything and start the Qt event loop."""
    # Minimal early logging (before config is loaded)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Initializing SnapSolve...")

    app = _initialize_qt_app()
    ctx = _create_context()

    # Replace early logging with full loguru setup now that config is available
    from core.logging_config import setup_logging

    setup_logging(ctx.config)
    _exit_if_profile_invalid(ctx)

    ctx.session_manager = SessionManager(ctx.config)
    active_source = _setup_active_source(ctx)
    _initialize_ui(ctx, active_source)
    _handle_coordinates_setup(ctx, active_source)

    ctx.audio_sink = build_audio_sink(ctx.config, ctx.session_manager, ctx.cancel_event)
    set_chat_sessions_btn_state(ctx.profile.get("enable_chat_sessions", True))
    publish_profiles(ctx)

    from core.periodic_screenshots import PeriodicScreenshotService

    ctx.periodic_screenshot_service = PeriodicScreenshotService(
        ctx.config, ctx.session_manager
    )
    if ctx.config.get("periodic_screenshots_enabled", False):
        ctx.periodic_screenshot_service.start()
    set_periodic_screenshots_btn_state(
        ctx.config.get("periodic_screenshots_enabled", False)
    )

    _start_api_server(ctx)
    register_keyboard_shortcuts(ctx)
    setup_tray_or_console_mode(ctx)
    _load_engines_in_background(ctx)

    logger.info("UI up; loading engines in the background.")
    code = app.exec()
    exit_app(ctx)
    sys.exit(code)
