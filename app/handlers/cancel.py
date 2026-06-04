"""Cancel handler."""
import app.state as state
from core.output import show_popup, update_multi_state


def handle_cancel():
    """Cancel any in-progress operation and reset multi-capture state."""
    print("Cancel requested.")
    state.cancel_event.set()

    # Reset multi-capture state if it was active
    if state.is_multi_capturing:
        state.is_multi_capturing = False
        state.multi_capture_texts = []
        update_multi_state(False)

    # Close any open popups and show a "Canceled" message
    from core.output import ui_signals

    ui_signals.close_popup.emit()
    show_popup("Cancelled", auto_close=2000, is_result=False)
