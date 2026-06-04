"""Source cycling and coordinate reselection handlers."""
import threading

import app.state as state
from app.state import set_processing, _show_status_popup
from app.handlers.capture import _ensure_ocr_engine
from config.settings import save_config
from core.output import set_active_source_ui
from core.sources import (
    ScreenshotSource,
    TextSource,
    SoundSource,
    get_active_source_instance,
    set_active_source_instance,
)
from ui.selector import get_coordinates


def handle_cycle_source(config, active_profile):
    """Cycle through available input sources: Text → Image → Audio → Text."""
    active_source = get_active_source_instance()
    if isinstance(active_source, TextSource):
        new_source = ScreenshotSource()
        _ensure_ocr_engine(active_profile)
        new_source.ocr_engine = state.ocr_engine_instance
    elif isinstance(active_source, ScreenshotSource):
        new_source = SoundSource(config, session_manager=state.session_manager)
    else:
        new_source = TextSource()

    set_active_source_instance(new_source)
    set_active_source_ui(new_source.name, opacity=config.get("opacity", 0.8))
    print(f"Source cycled to: {new_source.name}")
    _show_status_popup(
        config, f"Source changed to: {new_source.name.capitalize()}", auto_close=2000
    )


def handle_reselect(config):
    """Reselect screen coordinates for image capture."""
    if state.is_processing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        print(f"Reselect is disabled for {active_source.name} source.")
        return

    set_processing(True)
    print("Reselecting coordinates...")

    try:
        # Run in a separate thread so we don't block keyboard hooks
        def _reselect():
            coords = get_coordinates()
            if coords:
                config["coordinates"] = coords
                save_config(config)
                print(f"New coordinates saved: {coords}")
            else:
                print("Reselection cancelled.")

            set_processing(False)

        threading.Thread(target=_reselect, daemon=True).start()
        return
    except Exception as reselect_error:
        print(f"Error during reselection: {reselect_error}")
        set_processing(False)
