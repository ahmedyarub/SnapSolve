"""Text input pipeline handler."""
import app.state as state
from app.state import _make_status_callback, _run_in_processing_thread, set_processing
from app.handlers.capture import _setup_capture_sinks, _process_capture_result
from core.pipeline import process_pipeline
from core.sources import TextSource


def _execute_text_pipeline(
    config, active_profile, prompt_text, status_update, text=None, image_paths=None
):
    """Execute text pipeline."""
    if text is None:
        text = prompt_text

    main_model = active_profile.get("model", state.DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    sink, popup_sink, show_headers = _setup_capture_sinks(
        config, active_profile, main_model, fallback_model
    )

    temp_source = TextSource()

    assert state.llm_engine_instance is not None

    result = process_pipeline(
        source=temp_source,
        llm=state.llm_engine_instance,
        prompt_text=prompt_text,
        status_callback=status_update,
        session_manager=state.session_manager,
        enable_chat_sessions=active_profile.get("enable_chat_sessions", True),
        sink=sink,
        fallback_llm=state.fallback_llm_engine_instance,
        text=text,
        image_paths=image_paths,
        cancel_event=state.cancel_event,
        max_retries=config.get("llm_max_retries", 3),
        base_delay=config.get("llm_retry_base_delay", 5),
    )

    if hasattr(sink, "finish"):
        sink.finish()

    if state.cancel_event.is_set():
        print("Text processing was cancelled.")
        return None

    print(f"Result: {result}")

    _process_capture_result(
        result, show_headers, popup_sink, fallback_model, main_model, config
    )

    return result


def handle_text_submit(config, active_profile, text):
    """Handle text input submission."""
    if state.is_processing:
        return

    set_processing(True)
    print(f"Processing text input: {text}")

    status_update = _make_status_callback(config)

    _run_in_processing_thread(
        config,
        lambda: _execute_text_pipeline(config, active_profile, text, status_update),
        error_label="processing text input",
    )
