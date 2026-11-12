"""Periodic screenshot handlers — toggle and configuration updates."""

import logging

from app.context import AppContext
from app.feedback import show_status
from config.settings import update_config_file
from core.output import set_periodic_screenshots_btn_state

logger = logging.getLogger(__name__)


def handle_toggle_periodic_screenshots(ctx: AppContext):
    """Toggle periodic screenshots on/off and persist the setting."""
    service = ctx.periodic_screenshot_service
    if service is None:
        logger.warning("Periodic screenshot service not initialized")
        return

    enabled = not service.is_running
    ctx.config["periodic_screenshots_enabled"] = enabled
    update_config_file({"periodic_screenshots_enabled": enabled})
    service.set_enabled(enabled)

    show_status(
        ctx.config,
        f"Periodic Screenshots {'ON' if enabled else 'OFF'}",
        auto_close=3000,
    )
    set_periodic_screenshots_btn_state(enabled)


def handle_set_periodic_screenshots_config(ctx: AppContext, **kwargs):
    """Update periodic screenshot settings.

    Accepted keyword arguments: ``interval`` (seconds between captures),
    ``on_activity`` (capture on keyboard/mouse activity) and
    ``activity_min_delay`` (minimum seconds between activity captures).
    """
    changes = {}
    if "interval" in kwargs:
        changes["periodic_screenshots_interval"] = int(kwargs["interval"])
    if "on_activity" in kwargs:
        changes["periodic_screenshots_on_activity"] = bool(kwargs["on_activity"])
    if "activity_min_delay" in kwargs:
        changes["periodic_screenshots_activity_min_delay"] = int(
            kwargs["activity_min_delay"]
        )
    ctx.config.update(changes)
    update_config_file(changes)

    # Restart service if running to pick up new settings
    service = ctx.periodic_screenshot_service
    if service and service.is_running:
        service.stop()
        service.start()

    show_status(ctx.config, "Screenshot settings updated", auto_close=2000)
