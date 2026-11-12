"""Chat session handlers — new session and toggle."""

from app.context import AppContext
from app.feedback import show_status
from config.settings import load_profiles, save_profiles
from core.output import close_popup, set_chat_sessions_btn_state


def handle_new_chat_session(ctx: AppContext):
    """Start a new chat session and show a confirmation popup."""
    if not ctx.session_manager:
        return
    session_id = ctx.session_manager.start_new_session()
    if "popup" in ctx.config.get("output_mode", ["popup"]):
        close_popup()
    show_status(
        ctx.config, f"New Chat Session Started\nID: {session_id}", auto_close=3000
    )


def handle_toggle_chat_sessions(ctx: AppContext):
    """Toggle chat sessions on/off for the active profile and persist it."""
    enabled = not ctx.profile.get("enable_chat_sessions", True)
    ctx.profile["enable_chat_sessions"] = enabled

    profiles = load_profiles()
    for p in profiles:
        if p.get("id") == ctx.profile.get("id"):
            p["enable_chat_sessions"] = enabled
            break
    save_profiles(profiles)

    show_status(
        ctx.config,
        f"Chat Sessions {'Enabled' if enabled else 'Disabled'}",
        auto_close=3000,
    )
    set_chat_sessions_btn_state(enabled)
