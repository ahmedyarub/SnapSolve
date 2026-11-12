"""Source cycling and coordinate reselection handlers."""

import logging
import threading

from app.context import AppContext
from app.feedback import run_request, show_status
from config.settings import update_config_file
from core.output import set_active_source_ui
from core.sources import (
    ScreenshotSource,
    SoundSource,
    TextSource,
    get_active_source_instance,
    set_active_source_instance,
)
from core.ui.selector import get_coordinates

logger = logging.getLogger(__name__)


def handle_cycle_source(ctx: AppContext):
    """Cycle through available input sources: Text → Image → Audio → Text."""
    active_source = get_active_source_instance()
    if isinstance(active_source, TextSource):
        new_source = ScreenshotSource()
        new_source.ocr_engine = ctx.ocr_engine

        if ctx.ocr_engine is None and ctx.profile.get("ocr_engine") == "paddleocr":
            # Loading PaddleOCR takes seconds; never on the hotkey/GUI thread.
            from app.handlers.capture import ensure_ocr_engine

            def load_ocr() -> None:
                new_source.ocr_engine = ensure_ocr_engine(ctx)

            threading.Thread(target=load_ocr, daemon=True, name="load-ocr").start()
    elif isinstance(active_source, ScreenshotSource):
        new_source = SoundSource(ctx.config, session_manager=ctx.session_manager)
    else:
        new_source = TextSource()

    set_active_source_instance(new_source)
    set_active_source_ui(new_source.name, opacity=ctx.config.get("opacity", 0.8))
    logger.info("Source cycled to: %s", new_source.name)
    show_status(
        ctx.config,
        f"Source changed to: {new_source.name.capitalize()}",
        auto_close=2000,
    )


def handle_reselect(ctx: AppContext):
    """Reselect the screen region used for image capture."""
    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        logger.info("Reselect is disabled for the %s source.", active_source.name)
        return

    def work() -> None:
        coords = get_coordinates()
        if coords:
            ctx.config["coordinates"] = coords
            update_config_file({"coordinates": coords})
            logger.info("New coordinates saved: %s", coords)
        else:
            logger.info("Reselection cancelled.")

    run_request(ctx, work, "reselect")
