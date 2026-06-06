"""core.ui — overlay widget package.

Re-exports every public name so that ``from core.ui import <name>`` works
identically to the old ``from core.output import <name>``.
"""

# --- Signals & globals ---
from core.ui.signals import (  # noqa: F401
    UISignals,
    SelectorSignals,
    ui_signals,
    selector_signals,
    set_last_user_prompt,
    call_action,
)

# --- IDE integration (also used by session_browser) ---
from core.ui.ide_integration import _PopupWebPage  # noqa: F401

# --- Widget classes ---
from core.ui.popup_widget import PopupWidget  # noqa: F401
from core.ui.record_button import RecordButton  # noqa: F401
from core.ui.subtitle_widget import SubtitleLabel, SubtitleWidget  # noqa: F401
from core.ui.panel_widget import PanelWidget  # noqa: F401
from core.ui.text_input_widget import TextInputWidget  # noqa: F401
from core.ui.url_input_widget import UrlInputWidget  # noqa: F401

# --- Manager ---
from core.ui.manager import UIManager, ui_manager, init_ui_manager  # noqa: F401

# --- Public API (thread-safe helpers) ---
from core.ui.api import (  # noqa: F401
    set_app_callbacks,
    set_hide_from_capture,
    toggle_control_panel,
    toggle_all_widgets,
    update_multi_state,
    set_active_source_ui,
    set_app_processing_state,
    show_popup,
    close_popup,
    share_response_screenshot,
    set_chat_sessions_btn_state,
    set_periodic_screenshots_btn_state,
    send_ocr_text_to_input,
    is_autosubmit_enabled,
    show_subtitle,
    update_subtitle,
    clear_subtitles,
    get_subtitle_text,
    output_result,
    get_active_source,
)
