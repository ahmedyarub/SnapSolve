"""Keyboard shortcut registration.

Every hotkey calls its handler with the AppContext, so it always acts on the
current profile (including after a runtime profile switch).
"""

import logging

import keyboard

from app.context import AppContext
from app.handlers.cancel import handle_cancel
from app.handlers.capture import handle_capture
from app.handlers.multi_capture import handle_end_multi_capture, handle_multi_capture
from app.handlers.navigation import (
    handle_open_session_browser,
    handle_open_url,
    handle_toggle_all_widgets,
    handle_toggle_panel,
)
from app.handlers.session import handle_new_chat_session, handle_toggle_chat_sessions
from app.handlers.source import handle_cycle_source, handle_reselect
from app.handlers.text import handle_text_submit
from app.lifecycle import exit_app
from core.output import get_subtitle_text

logger = logging.getLogger(__name__)


def _actions(ctx: AppContext) -> dict:
    """Hotkey action name -> zero-argument callable."""
    return {
        "capture": lambda: handle_capture(ctx),
        "reselect": lambda: handle_reselect(ctx),
        "multi_capture": lambda: handle_multi_capture(ctx),
        "end_multi_capture": lambda: handle_end_multi_capture(ctx),
        "cancel": lambda: handle_cancel(ctx),
        "cancel_multi_capture": lambda: handle_cancel(ctx),
        "toggle_panel": handle_toggle_panel,
        "new_chat_session": lambda: handle_new_chat_session(ctx),
        "toggle_chat_sessions": lambda: handle_toggle_chat_sessions(ctx),
        "cycle_source": lambda: handle_cycle_source(ctx),
        "toggle_all_widgets": handle_toggle_all_widgets,
        "open_url": handle_open_url,
        "open_session_browser": handle_open_session_browser,
        "quit_app": lambda: exit_app(ctx),
    }


def _register_debug_hotkeys(ctx: AppContext) -> None:
    """Hotkeys for testing transcription (only with debug_hotkeys: true)."""

    def show_test_subtitle():
        import secrets

        from core.output import show_subtitle

        show_subtitle(
            f"Transcription test with random number: {secrets.randbelow(1000) + 1}"
        )

    def submit_subtitle(index):
        text = get_subtitle_text(index)
        if text:
            handle_text_submit(ctx, text)
        else:
            logger.info("No subtitle at index %s", index)

    keyboard.add_hotkey("ctrl+alt+shift+t", show_test_subtitle)
    for i in range(1, 6):
        keyboard.add_hotkey(f"ctrl+alt+shift+{i}", submit_subtitle, args=(i,))


def register_keyboard_shortcuts(ctx: AppContext) -> None:
    """Register the configured hotkeys (and the debug ones if enabled)."""
    if ctx.config.get("debug_hotkeys", False):
        _register_debug_hotkeys(ctx)

    actions = _actions(ctx)
    for hk in ctx.config.get("hotkeys", []):
        action, key = hk.get("action"), hk.get("key")
        if not action or not key:
            continue
        handler = actions.get(action)
        if handler is None:
            logger.warning("Unknown hotkey action %r (%s)", action, key)
            continue
        logger.info("Listening for '%s' hotkey: %s", action, key)
        keyboard.add_hotkey(key, handler)
