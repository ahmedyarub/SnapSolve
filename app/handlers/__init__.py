"""Handler re-exports — single import point for all ``handle_*`` functions."""
from app.handlers.cancel import handle_cancel
from app.handlers.capture import handle_capture
from app.handlers.audio import handle_start_record, handle_stop_record
from app.handlers.multi_capture import handle_multi_capture, handle_end_multi_capture
from app.handlers.navigation import (
    handle_toggle_panel,
    handle_toggle_all_widgets,
    handle_open_url,
    handle_open_session_browser,
    handle_open_context_manager,
)
from app.handlers.periodic_screenshots import (
    handle_toggle_periodic_screenshots,
    handle_set_periodic_screenshots_config,
)
from app.handlers.session import handle_new_chat_session, handle_toggle_chat_sessions
from app.handlers.source import handle_cycle_source, handle_reselect
from app.handlers.text import handle_text_submit

__all__ = [
    "handle_cancel",
    "handle_capture",
    "handle_cycle_source",
    "handle_end_multi_capture",
    "handle_multi_capture",
    "handle_new_chat_session",
    "handle_open_context_manager",
    "handle_open_session_browser",
    "handle_open_url",
    "handle_reselect",
    "handle_set_periodic_screenshots_config",
    "handle_start_record",
    "handle_stop_record",
    "handle_text_submit",
    "handle_toggle_all_widgets",
    "handle_toggle_chat_sessions",
    "handle_toggle_panel",
    "handle_toggle_periodic_screenshots",
]
