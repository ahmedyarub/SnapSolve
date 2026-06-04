"""Keyboard shortcut registration."""
import keyboard

from app.handlers.capture import handle_capture
from app.handlers.cancel import handle_cancel
from app.handlers.multi_capture import handle_multi_capture, handle_end_multi_capture
from app.handlers.navigation import (
    handle_toggle_panel,
    handle_toggle_all_widgets,
    handle_open_url,
    handle_open_session_browser,
)
from app.handlers.session import handle_new_chat_session, handle_toggle_chat_sessions
from app.handlers.source import handle_cycle_source, handle_reselect
from app.handlers.text import handle_text_submit
from app.state import exit_app
from core.output import get_subtitle_text


def _register_test_hotkeys(config, active_profile):
    """Register test hotkeys for transcription testing."""

    def handle_test_transcription():
        import secrets
        from core.output import show_subtitle

        test_text = (
            f"Transcription test with random number: {secrets.randbelow(1000) + 1}"
        )
        print(f"Testing transcription display: {test_text}")
        show_subtitle(test_text)

    def handle_select_subtitle(index):
        text = get_subtitle_text(index)
        if text:
            print(f"Selected subtitle {index}: {text}")
            handle_text_submit(config, active_profile, text)
        else:
            print(f"No subtitle found at index {index}")

    keyboard.add_hotkey("ctrl+alt+shift+t", handle_test_transcription)

    for i in range(1, 6):
        keyboard.add_hotkey(f"ctrl+alt+shift+{i}", handle_select_subtitle, args=(i,))


def _register_config_hotkeys(config, active_profile, active_prompt_text):
    """Register hotkeys from configuration."""
    hotkeys = config.get("hotkeys", [])

    for hk in hotkeys:
        action = hk.get("action")
        key = hk.get("key")
        if not action or not key:
            continue

        print(f"Listening for '{action}' hotkey: {key}")

        if action == "capture":
            keyboard.add_hotkey(
                key, handle_capture, args=(config, active_profile, active_prompt_text)
            )
        elif action == "reselect":
            keyboard.add_hotkey(key, handle_reselect, args=(config,))
        elif action == "multi_capture":
            keyboard.add_hotkey(
                key,
                handle_multi_capture,
                args=(config, active_profile, active_prompt_text),
            )
        elif action == "end_multi_capture":
            keyboard.add_hotkey(
                key,
                handle_end_multi_capture,
                args=(config, active_profile, active_prompt_text),
            )
        elif action == "cancel":
            keyboard.add_hotkey(key, handle_cancel)
        elif action == "toggle_panel":
            keyboard.add_hotkey(key, handle_toggle_panel, args=(config,))
        elif action == "new_chat_session":
            keyboard.add_hotkey(key, handle_new_chat_session, args=(config,))
        elif action == "toggle_chat_sessions":
            keyboard.add_hotkey(
                key, handle_toggle_chat_sessions, args=(config, active_profile)
            )
        elif action == "cycle_source":
            keyboard.add_hotkey(key, handle_cycle_source, args=(config, active_profile))
        elif action == "toggle_all_widgets":
            keyboard.add_hotkey(key, handle_toggle_all_widgets)
        elif action == "open_url":
            keyboard.add_hotkey(key, handle_open_url)
        elif action == "open_session_browser":
            keyboard.add_hotkey(key, handle_open_session_browser)
        elif action == "quit_app":
            keyboard.add_hotkey(key, exit_app)


def _register_keyboard_shortcuts(config, active_profile, active_prompt_text):
    """Register keyboard shortcuts."""
    _register_test_hotkeys(config, active_profile)
    _register_config_hotkeys(config, active_profile, active_prompt_text)
