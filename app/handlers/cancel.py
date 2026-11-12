"""Cancel handler."""

import logging

from app.context import AppContext
from core.output import show_popup, ui_signals, update_multi_state

logger = logging.getLogger(__name__)


def handle_cancel(ctx: AppContext):
    """Cancel any in-progress operation and reset multi-capture state."""
    logger.info("Cancel requested.")
    ctx.cancel_event.set()

    if ctx.is_multi_capturing:
        ctx.reset_multi_capture()
        update_multi_state(False)

    # Close any open popups and show a "Cancelled" message
    ui_signals.close_popup.emit()
    show_popup("Cancelled", auto_close=2000, is_result=False)
