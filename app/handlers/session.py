"""Chat session handlers — new session and toggle."""
import app.state as state
from app.state import _show_status_popup
from config.settings import load_profiles
from core.output import close_popup, set_chat_sessions_btn_state


def handle_new_chat_session(config):
    """Start a new chat session and show a confirmation popup."""
    if state.session_manager:
        session_id = state.session_manager.start_new_session()
        # Visual reset and popup
        if "popup" in config.get("output_mode", ["popup"]):
            close_popup()
        _show_status_popup(
            config, f"New Chat Session Started\nID: {session_id}", auto_close=3000
        )


def handle_toggle_chat_sessions(config, active_profile):
    """Toggle chat sessions on/off for the active profile and persist."""
    current = active_profile.get("enable_chat_sessions", True)
    active_profile["enable_chat_sessions"] = not current

    # Save the profiles
    profiles = load_profiles()
    for p in profiles:
        if p["id"] == active_profile["id"]:
            p["enable_chat_sessions"] = not current
            break

    from config.settings import save_profiles

    save_profiles(profiles)

    state_str = "Enabled" if not current else "Disabled"
    _show_status_popup(config, f"Chat Sessions {state_str}", auto_close=3000)
    set_chat_sessions_btn_state(not current)
