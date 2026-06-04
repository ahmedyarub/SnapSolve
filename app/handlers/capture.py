"""Capture pipeline handlers — screen capture, OCR, sink setup, and result processing.

Also contains ``_handle_audio_source_capture`` (kept here rather than in
``audio.py`` to avoid a circular import: capture → audio → text → capture).
"""
import app.state as state
from app.state import (
    _show_status_popup,
    _make_status_callback,
    _run_in_processing_thread,
    set_processing,
)
from core.output import output_result, share_response_screenshot
from core.pipeline import process_pipeline
from core.remote_control_server import is_android_connected
from core.sinks import PopupSink, CompositeSink
from core.sources import get_active_source_instance


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
def _ensure_ocr_engine(active_profile, status_callback=None):
    """Lazily initialize PaddleOCR engine if needed."""
    if (
        state.ocr_engine_instance is None
        and active_profile.get("ocr_engine", "none") == "paddleocr"
    ):
        if status_callback:
            status_callback("Loading PaddleOCR engine...")
        else:
            print("Loading PaddleOCR engine on demand...")
        from core.sources.ocr import LocalPaddleOCREngine

        state.ocr_engine_instance = LocalPaddleOCREngine(warmup=False)
    return state.ocr_engine_instance


# ---------------------------------------------------------------------------
# Sink setup & result processing (shared with text.py)
# ---------------------------------------------------------------------------
def _setup_capture_sinks(config, active_profile, main_model, fallback_model):
    """Setup capture sinks."""
    show_headers = False
    prompt_id = active_profile.get("prompt_id", "default")

    if fallback_model and fallback_model != "None" and prompt_id != "quick":
        show_headers = True

    popup_sink = PopupSink(
        config, show_headers, main_model, fallback_model, state.cancel_event
    )

    assert state.audio_sink_instance is not None
    sink = CompositeSink([popup_sink, state.audio_sink_instance], state.cancel_event)

    return sink, popup_sink, show_headers


def _process_capture_result(
    result, show_headers, popup_sink, fallback_model, main_model, config
):
    """Process capture result."""
    final_result = result
    if show_headers:
        if popup_sink.accumulated_fallback and len(popup_sink.accumulated_result) == 1:
            final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
        else:
            final_result = f"## Main Model ({main_model})\n\n{result}"

    output_result(
        final_result,
        config.get("output_mode"),
        auto_close=config.get("auto_close_results", False),
        opacity=config.get("opacity", 0.8),
    )

    if config.get("share_response_with_android", False) and is_android_connected():
        print("Sharing response screenshot with Android app...")
        share_response_screenshot()


# ---------------------------------------------------------------------------
# Capture pipeline execution
# ---------------------------------------------------------------------------
def _execute_capture_pipeline(
    config, active_profile, active_prompt_text, status_update
):
    """Execute capture pipeline."""
    active_src = get_active_source_instance()

    _ensure_ocr_engine(active_profile)
    if hasattr(active_src, "ocr_engine"):
        active_src.ocr_engine = state.ocr_engine_instance

    main_model = active_profile.get("model", state.DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    sink, popup_sink, show_headers = _setup_capture_sinks(
        config, active_profile, main_model, fallback_model
    )

    assert active_src is not None
    assert state.llm_engine_instance is not None

    result = process_pipeline(
        source=active_src,
        llm=state.llm_engine_instance,
        prompt_text=active_prompt_text,
        status_callback=status_update,
        session_manager=state.session_manager,
        enable_chat_sessions=active_profile.get("enable_chat_sessions", True),
        sink=sink,
        fallback_llm=state.fallback_llm_engine_instance,
        coords=config.get("coordinates"),
        cancel_event=state.cancel_event,
        max_retries=config.get("llm_max_retries", 3),
        base_delay=config.get("llm_retry_base_delay", 5),
    )

    if hasattr(sink, "finish"):
        sink.finish()

    if hasattr(active_src, "cleanup_all"):
        active_src.cleanup_all()

    if state.cancel_event.is_set():
        print("Capture processing was cancelled.")
        return

    print(f"Result: {result}")

    _process_capture_result(
        result, show_headers, popup_sink, fallback_model, main_model, config
    )


# ---------------------------------------------------------------------------
# Public handler
# ---------------------------------------------------------------------------
def handle_capture(config, active_profile, active_prompt_text):
    """Handle a screen capture request."""
    if state.is_processing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name == "audio":
        _handle_audio_source_capture()
        return

    if active_source and active_source.name != "image":
        print(f"Capture is disabled for {active_source.name} source.")
        return

    set_processing(True)
    print("Capturing and processing...")

    status_update = _make_status_callback(config)

    _run_in_processing_thread(
        config,
        lambda: _execute_capture_pipeline(
            config, active_profile, active_prompt_text, status_update
        ),
        error_label="processing",
    )
