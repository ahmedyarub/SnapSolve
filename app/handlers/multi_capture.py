"""Multi-capture handlers — accumulate multiple screen captures before sending to LLM."""
import threading

import app.state as state
from app.state import (
    _show_status_popup,
    _make_status_callback,
    _run_in_processing_thread,
    set_processing,
)
from app.handlers.capture import _ensure_ocr_engine
from core.output import update_multi_state
from core.sources import ScreenshotSource, get_active_source_instance
from ui.selector import get_coordinates


def _check_multi_capture_requirements(config, active_profile):
    """Check multi-capture requirements."""
    ocr_type = active_profile.get("ocr_engine", "none")
    if ocr_type == "none":
        _show_status_popup(
            config,
            "Error: Multi-capture requires an OCR engine to be defined in the active profile.",
            auto_close=5000,
        )
        return False
    return True


def _initialize_multi_capture():
    """Initialize multi-capture mode."""
    if not state.is_multi_capturing:
        state.is_multi_capturing = True
        state.multi_capture_texts = []
        state.multi_capture_images = []
        update_multi_state(True)


def _perform_multi_capture_ocr(active_profile, coords, status_update):
    """Perform multi-capture OCR."""
    _ensure_ocr_engine(active_profile, status_callback=status_update)

    temp_source = ScreenshotSource()
    temp_source.ocr_engine = state.ocr_engine_instance
    extracted_text = None
    image_path = None
    try:
        extracted_text = temp_source.get_text(
            coords=coords,
            status_callback=status_update,
            cancel_event=state.cancel_event,
        )
        if hasattr(temp_source, "_temp_files") and temp_source._temp_files:
            image_path = temp_source._temp_files[-1]
    except Exception as ocr_error:
        status_update(f"Error during OCR: {str(ocr_error)}")
    finally:
        temp_source.cleanup_all()

    return extracted_text, image_path


def _handle_multi_capture_ocr(active_profile, coords, config):
    """Handle OCR during multi-capture."""

    def status_update(msg):
        _show_status_popup(config, msg)

    status_update("Capturing screen...")

    extracted_text, image_path = _perform_multi_capture_ocr(active_profile, coords, status_update)

    if state.cancel_event.is_set():
        print("Multi-capture OCR was cancelled.")
        return None

    if extracted_text or image_path:
        if extracted_text:
            state.multi_capture_texts.append(extracted_text)
        if image_path:
            state.multi_capture_images.append(image_path)
        status_update(
            f"Captured {len(state.multi_capture_texts)} text blocks, "
            f"{len(state.multi_capture_images)} images... Multiple capture mode"
        )
    else:
        status_update(
            f"No text found. Captured {len(state.multi_capture_images)} images... Multiple capture mode"
        )

    return extracted_text


def _multi_capture_loop(config, active_profile):
    """Main loop for multi-capture process."""
    coords = get_coordinates()
    if not coords or state.cancel_event.is_set():
        print("Multi-capture: Selection cancelled.")
        if state.is_multi_capturing:
            from app.handlers.cancel import handle_cancel

            handle_cancel()
        return

    _handle_multi_capture_ocr(active_profile, coords, config)


def handle_multi_capture(config, active_profile):
    """Start or continue a multi-capture session."""
    if state.is_processing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        print(f"Multi-capture is disabled for {active_source.name} source.")
        return

    set_processing(True)

    def _multi_capture():
        if not _check_multi_capture_requirements(config, active_profile):
            return

        _initialize_multi_capture()
        _show_status_popup(config, "Multiple capture mode")
        _multi_capture_loop(config, active_profile)

    _run_in_processing_thread(config, _multi_capture, error_label="multi-capture")


def _check_multi_capture_texts(config, capture_texts):
    """Check if there are multi-capture texts."""
    if not capture_texts:
        _show_status_popup(
            config, "No text captured in multi-capture mode.", auto_close=3000
        )
        return False
    return True


def handle_end_multi_capture(config, active_profile, active_prompt_text):
    """End multi-capture mode and send combined text to LLM."""
    if state.is_processing:
        return

    if not state.is_multi_capturing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        return

    set_processing(True)

    update_multi_state(False)

    def _end_multi_capture():
        try:
            if not _check_multi_capture_texts(config, state.multi_capture_texts):
                state.is_multi_capturing = False
                update_multi_state(False)
                return

            combined_text = "\n\n".join(state.multi_capture_texts)
            print(f"Combined Text:\n{combined_text}")

            status_update = _make_status_callback(config)

            from app.handlers.text import _execute_text_pipeline

            _execute_text_pipeline(
                config,
                active_profile,
                active_prompt_text,
                status_update,
                text=combined_text,
                image_paths=state.multi_capture_images if state.multi_capture_images else None,
            )

        except Exception as multi_error:
            print(f"Error during processing multi-capture: {multi_error}")
            _show_status_popup(config, f"Error: {multi_error}", auto_close=5000)
        finally:
            set_processing(False)
            state.is_multi_capturing = False
            state.multi_capture_texts = []
            state.multi_capture_images = []

    threading.Thread(target=_end_multi_capture, daemon=True).start()
