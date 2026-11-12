"""Capture pipeline handlers — screen capture, OCR, sink setup, and result processing.

Also contains ``_handle_audio_source_capture`` (kept here rather than in
``audio.py`` to avoid a circular import: capture → audio → text → capture).
"""

import logging

from app.context import AppContext
from app.feedback import run_request, show_status, status_callback
from core.output import output_result, share_response_screenshot
from core.pipeline import process_pipeline
from core.remote_control_server import is_android_connected
from core.sinks import CompositeSink, PopupSink
from core.sources import get_active_source_instance

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audio source capture (lives here to break a circular import)
# ---------------------------------------------------------------------------
def _handle_audio_source_capture():
    """Handle audio source capture."""
    from core.output import ui_manager

    if ui_manager and ui_manager.panel:
        record_btn = ui_manager.panel.btn_record
        if record_btn.is_recording:
            record_btn.stop_record_action()
        else:
            record_btn.start_record_action()


# ---------------------------------------------------------------------------
# OCR engine lazy init
# ---------------------------------------------------------------------------
def ensure_ocr_engine(ctx: AppContext, status_update=None):
    """Load the local PaddleOCR engine on first use if the profile wants it."""
    with ctx.engines_lock:
        if ctx.ocr_engine is None and ctx.profile.get("ocr_engine") == "paddleocr":
            (status_update or logger.info)("Loading PaddleOCR engine...")
            from core.sources.ocr import LocalPaddleOCREngine

            ctx.ocr_engine = LocalPaddleOCREngine(warmup=False)
        return ctx.ocr_engine


# ---------------------------------------------------------------------------
# Sink setup & result processing (shared with text.py)
# ---------------------------------------------------------------------------
def setup_capture_sinks(ctx: AppContext):
    """The popup + TTS sinks for one request; headers when two models answer."""
    main_model, fallback_model = ctx.main_model, ctx.fallback_model
    show_headers = bool(fallback_model) and ctx.profile.get("prompt_id") != "quick"
    popup_sink = PopupSink(
        ctx.config,
        show_headers,
        main_model,
        fallback_model or "None",
        ctx.cancel_event,
    )
    assert ctx.audio_sink is not None
    sink = CompositeSink([popup_sink, ctx.audio_sink], ctx.cancel_event)
    return sink, popup_sink, show_headers


def process_capture_result(ctx: AppContext, result, show_headers, popup_sink) -> None:
    """Show the final answer (with a model header when two models answered)."""
    config = ctx.config
    final_result = result
    if show_headers:
        if popup_sink.accumulated_fallback and len(popup_sink.accumulated_result) == 1:
            final_result = f"## Fallback Model ({ctx.fallback_model})\n\n{result}"
        else:
            final_result = f"## Main Model ({ctx.main_model})\n\n{result}"

    output_result(
        final_result,
        config.get("output_mode"),
        auto_close=config.get("auto_close_results", False),
        opacity=config.get("opacity", 0.8),
    )

    if config.get("share_response_with_android", False) and is_android_connected():
        logger.info("Sharing response screenshot with Android app...")
        share_response_screenshot()


def llm_unavailable(ctx: AppContext) -> bool:
    """Show a popup and return True if the main LLM cannot be reached."""
    if ctx.llm_engine:
        available, err_msg = ctx.llm_engine.is_available()
        if not available:
            show_status(ctx.config, f"⚠️ LLM Unavailable: {err_msg}", auto_close=5000)
            return True
    return False


# ---------------------------------------------------------------------------
# Capture pipeline execution
# ---------------------------------------------------------------------------
def _execute_capture_pipeline(ctx: AppContext, status_update) -> None:
    active_src = get_active_source_instance()
    if llm_unavailable(ctx):
        return

    ensure_ocr_engine(ctx)
    with ctx.engines_lock:  # a profile switch waits until this request is set up
        if hasattr(active_src, "ocr_engine"):
            active_src.ocr_engine = ctx.ocr_engine
        llm, fallback_llm = ctx.llm_engine, ctx.fallback_llm_engine
        prompt_text = ctx.prompt_text
        chat_sessions = ctx.profile.get("enable_chat_sessions", True)
        sink, popup_sink, show_headers = setup_capture_sinks(ctx)

    assert active_src is not None
    assert llm is not None

    result = process_pipeline(
        source=active_src,
        llm=llm,
        prompt_text=prompt_text,
        status_callback=status_update,
        session_manager=ctx.session_manager,
        enable_chat_sessions=chat_sessions,
        sink=sink,
        fallback_llm=fallback_llm,
        coords=ctx.config.get("coordinates"),
        cancel_event=ctx.cancel_event,
        max_retries=ctx.config.get("llm_max_retries", 3),
        base_delay=ctx.config.get("llm_retry_base_delay", 5),
    )

    if hasattr(sink, "finish"):
        sink.finish()
    if hasattr(active_src, "cleanup_all"):
        active_src.cleanup_all()

    if ctx.cancel_event.is_set():
        logger.info("Capture processing was cancelled.")
        return

    process_capture_result(ctx, result, show_headers, popup_sink)


# ---------------------------------------------------------------------------
# OCR-to-text-box (Autosubmit OFF)
# ---------------------------------------------------------------------------
def _execute_ocr_to_textbox(ctx: AppContext) -> None:
    """Perform OCR and send the extracted text to the text input widget."""
    from core.output import send_ocr_text_to_input
    from core.sources import ScreenshotSource

    status_update = status_callback(ctx.config)
    status_update("Capturing screen...")

    temp_source = ScreenshotSource()
    temp_source.ocr_engine = ensure_ocr_engine(ctx, status_update)
    try:
        extracted_text = temp_source.get_text(
            coords=ctx.config.get("coordinates"),
            status_callback=status_update,
            cancel_event=ctx.cancel_event,
        )
    except Exception as e:
        show_status(ctx.config, f"OCR error: {e}", auto_close=5000)
        return
    finally:
        temp_source.cleanup_all()

    if ctx.cancel_event.is_set():
        logger.info("OCR-to-textbox was cancelled.")
        return

    if extracted_text:
        send_ocr_text_to_input(extracted_text)
    else:
        show_status(ctx.config, "OCR found no text.", auto_close=3000)


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------
def handle_capture(ctx: AppContext):
    """Handle a screen capture request."""
    active_source = get_active_source_instance()
    if active_source and active_source.name == "audio":
        _handle_audio_source_capture()
        return

    if active_source and active_source.name != "image":
        logger.info("Capture is disabled for the %s source.", active_source.name)
        return

    from core.output import is_autosubmit_enabled

    if not is_autosubmit_enabled():
        run_request(ctx, lambda: _execute_ocr_to_textbox(ctx), "OCR to text box")
        return

    status_update = status_callback(ctx.config)
    run_request(ctx, lambda: _execute_capture_pipeline(ctx, status_update), "capture")
