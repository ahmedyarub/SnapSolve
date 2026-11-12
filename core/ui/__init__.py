"""core.ui — overlay widget package.

Re-exports every public name so that ``from core.ui import <name>`` works
identically to the old ``from core.output import <name>``.
"""

# --- Signals & globals ---
# --- Public API (thread-safe helpers) ---
from core.ui.api import (  # noqa: F401
    clear_subtitles,
    close_popup,
    get_active_source,
    get_subtitle_text,
    is_autosubmit_enabled,
    output_result,
    send_ocr_text_to_input,
    set_active_source_ui,
    set_app_callbacks,
    set_app_processing_state,
    set_chat_sessions_btn_state,
    set_hide_from_capture,
    set_periodic_screenshots_btn_state,
    share_response_screenshot,
    show_popup,
    show_subtitle,
    toggle_all_widgets,
    toggle_control_panel,
    update_multi_state,
    update_subtitle,
)

# --- IDE integration (also used by session_browser) ---
from core.ui.ide_integration import _PopupWebPage  # noqa: F401

# --- Manager ---
from core.ui.manager import UIManager, init_ui_manager, ui_manager  # noqa: F401
from core.ui.panel_widget import PanelWidget  # noqa: F401

# --- Widget classes ---
from core.ui.popup_widget import PopupWidget  # noqa: F401
from core.ui.record_button import RecordButton  # noqa: F401
from core.ui.signals import (  # noqa: F401
    SelectorSignals,
    UISignals,
    call_action,
    selector_signals,
    set_last_user_prompt,
    ui_signals,
)
from core.ui.subtitle_widget import SubtitleLabel, SubtitleWidget  # noqa: F401
from core.ui.text_input_widget import TextInputWidget  # noqa: F401
from core.ui.url_input_widget import UrlInputWidget  # noqa: F401
