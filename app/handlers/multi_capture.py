"""Multi-capture handlers — accumulate multiple screen captures before sending to LLM."""

import logging

from app.context import AppContext
from app.feedback import run_request, show_status, status_callback
from app.handlers.capture import ensure_ocr_engine
from core.output import update_multi_state
from core.sources import ScreenshotSource, get_active_source_instance
from core.ui.selector import get_coordinates

logger = logging.getLogger(__name__)


def _image_source_active() -> bool:
    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        logger.info("Multi-capture is disabled for the %s source.", active_source.name)
        return False
    return True


def _capture_one_region(ctx: AppContext) -> None:
    """Let the user pick a region, OCR it, and add it to the multi-capture."""
    status_update = status_callback(ctx.config)
    coords = get_coordinates()
    if not coords or ctx.cancel_event.is_set():
        logger.info("Multi-capture: selection cancelled.")
        if ctx.is_multi_capturing:
            from app.handlers.cancel import handle_cancel

            handle_cancel(ctx)
        return

    status_update("Capturing screen...")
    temp_source = ScreenshotSource()
    temp_source.ocr_engine = ensure_ocr_engine(ctx, status_update)
    extracted_text = None
    image_path = None
    try:
        extracted_text = temp_source.get_text(
            coords=coords, status_callback=status_update, cancel_event=ctx.cancel_event
        )
        if getattr(temp_source, "temp_files", None):
            image_path = temp_source.temp_files[-1]
    except Exception as ocr_error:
        status_update(f"Error during OCR: {ocr_error!s}")
    finally:
        temp_source.cleanup_all()

    if ctx.cancel_event.is_set():
        logger.info("Multi-capture OCR was cancelled.")
        return

    if extracted_text:
        ctx.multi_capture_texts.append(extracted_text)
        # When Autosubmit is OFF, incrementally send OCR text to the text box
        from core.output import is_autosubmit_enabled, send_ocr_text_to_input

        if not is_autosubmit_enabled():
            send_ocr_text_to_input(extracted_text)
    if image_path:
        ctx.multi_capture_images.append(image_path)

    if extracted_text or image_path:
        status_update(
            f"Captured {len(ctx.multi_capture_texts)} text blocks, "
            f"{len(ctx.multi_capture_images)} images... Multiple capture mode"
        )
    else:
        status_update(
            f"No text found. Captured {len(ctx.multi_capture_images)} images... "
            "Multiple capture mode"
        )


def handle_multi_capture(ctx: AppContext):
    """Start or continue a multi-capture session."""
    if not _image_source_active():
        return
    if ctx.profile.get("ocr_engine", "none") == "none":
        show_status(
            ctx.config,
            "Error: Multi-capture requires an OCR engine in the active profile.",
            auto_close=5000,
        )
        return

    def work() -> None:
        if not ctx.is_multi_capturing:
            ctx.reset_multi_capture()
            ctx.is_multi_capturing = True
            update_multi_state(True)
        show_status(ctx.config, "Multiple capture mode")
        _capture_one_region(ctx)

    run_request(ctx, work, "multi-capture")


def handle_end_multi_capture(ctx: AppContext):
    """End multi-capture mode and send the combined text to the LLM."""
    if not ctx.is_multi_capturing or not _image_source_active():
        return

    def work() -> None:
        try:
            update_multi_state(False)
            if not ctx.multi_capture_texts:
                show_status(
                    ctx.config,
                    "No text captured in multi-capture mode.",
                    auto_close=3000,
                )
                return

            from core.output import is_autosubmit_enabled

            if not is_autosubmit_enabled():
                # Autosubmit OFF — the text is already in the text box from the
                # incremental sends; let the user review and submit it.
                logger.info(
                    "Multi-capture ended (Autosubmit OFF); text left in text box."
                )
                return

            from app.handlers.text import execute_text_pipeline

            execute_text_pipeline(
                ctx,
                ctx.prompt_text,
                status_callback(ctx.config),
                text="\n\n".join(ctx.multi_capture_texts),
                image_paths=list(ctx.multi_capture_images) or None,
                source_name="image",
            )
        finally:
            ctx.reset_multi_capture()

    run_request(ctx, work, "end multi-capture")
