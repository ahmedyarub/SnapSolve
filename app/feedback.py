"""Status popups and the standard way to run a request in the background."""

import logging
import threading
from collections.abc import Callable

from app.context import AppContext
from core.output import show_popup

logger = logging.getLogger(__name__)


def show_status(config: dict, message: str, auto_close: int | None = None) -> None:
    """Show a non-result popup if popup output mode is enabled."""
    if "popup" in config.get("output_mode", ["popup"]):
        show_popup(
            message,
            auto_close=auto_close,
            opacity=config.get("opacity", 0.8),
            is_result=False,
        )


def status_callback(config: dict) -> Callable[[str], None]:
    """A callback that shows each status message as a popup."""

    def status_update(msg: str) -> None:
        show_status(config, msg)

    return status_update


def run_request(
    ctx: AppContext, work_fn: Callable[[], object], label: str = "processing"
) -> bool:
    """Run ``work_fn`` on a worker thread as *the* current request.

    Returns False (and does nothing) if another request is already running.
    The request ends, and the UI leaves its busy state, when ``work_fn`` returns
    or raises.
    """
    if not ctx.ready.is_set():
        show_status(ctx.config, "Still starting up, one moment...", auto_close=2500)
        return False
    if not ctx.try_start_processing():
        logger.info("Ignoring %s: another request is running", label)
        return False

    def worker() -> None:
        try:
            work_fn()
        except Exception as err:
            logger.exception("Error during %s", label)
            show_status(ctx.config, f"Error: {err}", auto_close=5000)
        finally:
            ctx.finish_processing()

    threading.Thread(target=worker, daemon=True, name=label).start()
    return True
