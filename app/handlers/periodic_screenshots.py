"""Periodic screenshot handlers — toggle and configuration updates."""
import app.state as state
from app.state import _show_status_popup
from config.settings import save_config
from core.output import set_periodic_screenshots_btn_state


def handle_toggle_periodic_screenshots(config):
    """Toggle periodic screenshots on/off and persist the setting."""
    service = state.periodic_screenshot_service
    if service is None:
        print("[PeriodicScreenshots] Service not initialized")
        return

    new_enabled = not service.is_running
    config["periodic_screenshots_enabled"] = new_enabled
    save_config(config)

    service.set_enabled(new_enabled)

    state_str = "ON" if new_enabled else "OFF"
    _show_status_popup(config, f"Periodic Screenshots {state_str}", auto_close=3000)
    set_periodic_screenshots_btn_state(new_enabled)


def handle_set_periodic_screenshots_config(config, **kwargs):
    """Update periodic screenshot settings (interval, on_activity, activity_min_delay).

    Accepted keyword arguments:

    * ``interval`` — seconds between periodic captures
    * ``on_activity`` — whether to capture on keyboard/mouse activity
    * ``activity_min_delay`` — minimum seconds between activity captures
    """
    service = state.periodic_screenshot_service

    if "interval" in kwargs:
        config["periodic_screenshots_interval"] = int(kwargs["interval"])
    if "on_activity" in kwargs:
        config["periodic_screenshots_on_activity"] = bool(kwargs["on_activity"])
    if "activity_min_delay" in kwargs:
        config["periodic_screenshots_activity_min_delay"] = int(kwargs["activity_min_delay"])

    save_config(config)

    # Restart service if running to pick up new settings
    if service and service.is_running:
        service.stop()
        service.start()

    _show_status_popup(config, "Screenshot settings updated", auto_close=2000)
