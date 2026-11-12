"""Orderly shutdown."""

import logging
import os
import threading
from collections.abc import Callable

from app.context import AppContext

logger = logging.getLogger(__name__)

SHUTDOWN_TIMEOUT_S = 8


def _shutdown_steps(ctx: AppContext) -> list[tuple[str, Callable[[], object]]]:
    from core.api_server import stop_api_server
    from core.sources.whisperlive_manager import stop_all_services

    steps: list[tuple[str, Callable[[], object]]] = [
        ("cancel the running request", ctx.cancel_event.set),
        ("stop the API server", stop_api_server),
    ]
    if ctx.periodic_screenshot_service:
        steps.append(
            ("stop periodic screenshots", ctx.periodic_screenshot_service.stop)
        )
    if ctx.correction_engine:
        steps.append(("stop the correction engine", ctx.correction_engine.stop))
    if ctx.session_manager:
        steps.append(("index the session", ctx.session_manager.cleanup))
    steps.append(("stop WhisperLive", stop_all_services))
    return steps


def exit_app(ctx: AppContext) -> None:
    """Stop the services this app started, then end the process.

    Shutdown runs on a worker thread with a deadline: exit_app is also called
    from the keyboard-hook thread (quit hotkey), where keyboard.unhook_all()
    deadlocks and QApplication.quit() can block, so the process ends with
    os._exit once the steps are done or the deadline passes.
    """
    ctx.is_running = False
    logger.info("Exiting...")

    def shutdown() -> None:
        for label, step in _shutdown_steps(ctx):
            try:
                step()
            except Exception:
                logger.exception("Shutdown: could not %s", label)

    worker = threading.Thread(target=shutdown, daemon=True, name="shutdown")
    worker.start()
    worker.join(timeout=SHUTDOWN_TIMEOUT_S)
    if worker.is_alive():
        logger.warning(
            "Shutdown did not finish in %ss; exiting anyway", SHUTDOWN_TIMEOUT_S
        )
    # noinspection PyProtectedMember
    os._exit(0)
