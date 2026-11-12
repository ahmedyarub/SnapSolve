"""Navigation-related handlers — panel, widget, URL, and dialog toggles."""

from core.output import toggle_all_widgets, toggle_control_panel, ui_signals


def handle_toggle_panel():
    """Toggle control panel state internally."""
    toggle_control_panel()


def handle_toggle_all_widgets():
    """Hide or unhide all overlay widgets at once."""
    toggle_all_widgets()


def handle_open_url():
    """Open the URL input popup."""
    ui_signals.show_url_input.emit()


def handle_open_session_browser():
    """Open the session browser dialog."""
    ui_signals.open_session_browser.emit()


def handle_open_context_manager(session_manager):
    """Open the context manager dialog (Qt main thread)."""
    from ui.context_manager_ui import ContextManagerDialog

    dialog = ContextManagerDialog(session_manager)
    dialog.exec()
