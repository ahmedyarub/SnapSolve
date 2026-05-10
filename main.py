GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
import json
import logging
import os
import platform
import sys
import threading

import keyboard
import pystray
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from config.settings import get_config, save_config, load_profiles, load_prompts
from core.llm import OllamaEngine, GeminiCLIEngine, GoogleGenAIEngine, LLMEngine
from core.output import (
    output_result,
    show_popup,
    close_popup,
    toggle_control_panel,
    set_app_callbacks,
    update_multi_state,
    set_active_source_ui,
    set_app_processing_state,
    get_subtitle_text,
)
from core.pipeline import process_pipeline
from core.session_manager import SessionManager
from core.sinks import PopupSink, AudioSink, CompositeSink
from core.sources import (
    ScreenshotSource,
    TextSource,
    SoundSource,
    get_active_source_instance,
    set_active_source_instance,
)
from core.sources.ocr import LocalPaddleOCREngine, NoOCREngine, RemotePaddleOCREngine
from ui.selector import get_coordinates

# Global state
is_running = True
is_processing = False
ocr_engine_instance = None
cancel_event = threading.Event()

llm_engine_instance: LLMEngine | None = None
fallback_llm_engine_instance: LLMEngine | None = None
session_manager: SessionManager | None = None
audio_sink_instance: AudioSink | None = None  # Global AudioSink instance

# Multi-capture state
is_multi_capturing = False
multi_capture_texts = []

# Enable Windows DPI awareness to fix coordinate scaling issues
if platform.system() == "Windows":
    import ctypes

    try:
        SetProcessDpiAwareness = getattr(ctypes.windll.shcore, "SetProcessDpiAwareness")
        SetProcessDpiAwareness(2)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")


def create_tray_icon(on_exit):
    # Create a simple tray icon
    img = Image.new("RGB", (64, 64), color=(73, 109, 137))

    def quit_action(_icon):
        _icon.stop()
        on_exit()

    def toggle_panel_action():
        toggle_control_panel()

    menu = pystray.Menu(
        pystray.MenuItem("Toggle Panel", toggle_panel_action),
        pystray.MenuItem("Exit", quit_action),
    )
    icon = pystray.Icon("ScreenQA", img, "Screen Capture QA", menu)
    return icon


def set_processing(state):
    global is_processing
    is_processing = state
    set_app_processing_state(state)
    if not state:
        cancel_event.clear()  # Reset cancel event when not processing


def _process_text_input(config, active_profile, text, status_update):
    try:
        global llm_engine_instance, fallback_llm_engine_instance
        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        from core.sources import TextSource
        temp_source = TextSource()

        assert llm_engine_instance is not None

        result = process_pipeline(
            source=temp_source, llm=llm_engine_instance, prompt_text=text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink, fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            text=text, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if cancel_event.is_set():
            print("Text processing was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as text_error:
        print(f"Error during processing text input: {text_error}")
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {text_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event):
    from core.sinks import PopupSink, CompositeSink
    fallback_model = active_profile.get("fallback_model", "None")
    main_model = active_profile.get("model", GEMINI_2_5_FLASH_LITE)
    popup_sink = PopupSink(config, show_headers, main_model, fallback_model, cancel_event)
    global audio_sink_instance
    assert audio_sink_instance is not None
    sink = CompositeSink([popup_sink, audio_sink_instance], cancel_event)
    return sink, popup_sink

def _output_pipeline_result(config, active_profile, result, show_headers, popup_sink):
    from core.output import output_result
    final_result = result
    if show_headers:
        fallback_model = active_profile.get("fallback_model", "None")
        main_model = active_profile.get("model", GEMINI_2_5_FLASH_LITE)
        if popup_sink.accumulated_fallback and len(popup_sink.accumulated_result) == 1:
            final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
        else:
            final_result = f"## Main Model ({main_model})\n\n{result}"
    output_result(
        final_result, config.get("output_mode"), None,
        auto_close=config.get("auto_close_results", False),
        opacity=config.get("popup_opacity", 0.8)
    )

def _create_status_update(config):
    from core.output import show_popup
    def status_update(msg):
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(msg, auto_close=None, opacity=config.get("popup_opacity", 0.8), is_result=False)
    return status_update

def _prepare_ocr_engine(config, active_profile, status_update):
    global ocr_engine_instance
    if ocr_engine_instance is None and active_profile.get("ocr_engine", "none") == "paddleocr":
        print("Loading PaddleOCR engine on demand...")
        from core.sources.ocr import LocalPaddleOCREngine
        ocr_engine_instance = LocalPaddleOCREngine(warmup=False)
    return ocr_engine_instance

def _process_text_input(config, active_profile, text, status_update):
    try:
        from core.pipeline import process_pipeline
        global llm_engine_instance, fallback_llm_engine_instance, session_manager, cancel_event
        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        from core.sources import TextSource
        temp_source = TextSource()

        assert llm_engine_instance is not None

        result = process_pipeline(
            source=temp_source, llm=llm_engine_instance, prompt_text=text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink,
            fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            text=text, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if cancel_event.is_set():
            print("Text processing was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as text_error:
        print(f"Error during processing text input: {text_error}")
        from core.output import show_popup
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {text_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def handle_text_submit(config, active_profile, text):
    global is_processing
    if is_processing:
        return
    set_processing(True)
    print(f"Processing text input: {text}")
    status_update = _create_status_update(config)
    threading.Thread(target=_process_text_input, args=(config, active_profile, text, status_update), daemon=True).start()


def _execute_capture(config, active_profile, active_prompt_text, coords, status_update, active_source_name, active_source):
    try:
        global llm_engine_instance, fallback_llm_engine_instance
        if active_source_name == "image":
            active_source.ocr_engine = _prepare_ocr_engine(config, status_update)
        else:
            if isinstance(active_source, SoundSource) and active_source.realtime_transcription:
                status_update("Listening (Streaming)...")
            else:
                status_update(f"Recording from {active_source_name} source...")

        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        assert llm_engine_instance is not None
        result = process_pipeline(
            source=active_source, llm=llm_engine_instance, prompt_text=active_prompt_text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink, fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            coords=coords, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if hasattr(active_source, "cleanup_all"): active_source.cleanup_all()
        if cancel_event.is_set():
            print("Capture was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as capture_error:
        print(f"Error during capture: {capture_error}")
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {capture_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def _execute_capture(config, active_profile, active_prompt_text, coords, status_update, active_source_name, active_source):
    try:
        from core.pipeline import process_pipeline
        global llm_engine_instance, fallback_llm_engine_instance, session_manager, cancel_event

        ocr_engine = _prepare_ocr_engine(config, active_profile, status_update)
        if hasattr(active_source, "ocr_engine") and ocr_engine:
            active_source.ocr_engine = ocr_engine

        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        assert active_source is not None
        assert llm_engine_instance is not None

        result = process_pipeline(
            source=active_source, llm=llm_engine_instance, prompt_text=active_prompt_text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink, fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            coords=coords, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if hasattr(active_source, "cleanup_all"): active_source.cleanup_all()
        if cancel_event.is_set():
            print("Capture processing was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as processing_error:
        print(f"Error during processing: {processing_error}")
        from core.output import show_popup
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {processing_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def handle_capture(config, active_profile, active_prompt_text):
    global is_processing
    if is_processing:
        return

    from core.output import get_active_source_instance
    active_source = get_active_source_instance()
    if active_source and active_source.name == "audio":
        from core.output import ui_manager
        if ui_manager and ui_manager.panel:
            record_btn = ui_manager.panel.btn_record
            if record_btn.is_recording: record_btn.stop_record_action()
            else: record_btn.start_record_action()
        return

    if active_source and active_source.name != "image":
        print(f"Capture is disabled for {active_source.name} source.")
        return

    set_processing(True)
    print("Capturing and processing...")
    status_update = _create_status_update(config)
    threading.Thread(target=_execute_capture, args=(config, active_profile, active_prompt_text, config.get("coordinates"), status_update, active_source.name if active_source else "text", active_source), daemon=True).start()


def _execute_multi_capture(config, coords, status_update):
    global is_multi_capturing, multi_capture_texts, ocr_engine_instance
    try:
        temp_source = ScreenshotSource()
        temp_source.ocr_engine = _prepare_ocr_engine(config, status_update)
        extracted_text = None
        try:
            extracted_text = temp_source.get_text(coords=coords, status_callback=status_update, cancel_event=cancel_event)
        except Exception as ocr_error:
            status_update(f"Error during OCR: {str(ocr_error)}")
        finally:
            temp_source.cleanup_all()

        if cancel_event.is_set():
            print("Multi-capture OCR was cancelled.")
            return

        if extracted_text:
            multi_capture_texts.append(extracted_text)
            status_update(f"Captured {len(multi_capture_texts)} images... Multiple capture mode")
        else:
            status_update(f"No text found. Captured {len(multi_capture_texts)} images... Multiple capture mode")
    except Exception as multi_capture_error:
        print(f"Error during multi-capture: {multi_capture_error}")
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {multi_capture_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def _execute_multi_capture(config, coords, status_update):
    global is_multi_capturing, multi_capture_texts, ocr_engine_instance, cancel_event
    try:
        from core.sources import ScreenshotSource
        from core.sources.ocr import LocalPaddleOCREngine
        if config.get("ocr_engine", "none") == "paddleocr" and not isinstance(ocr_engine_instance, LocalPaddleOCREngine):
            status_update("Loading PaddleOCR engine...")
            ocr_engine_instance = LocalPaddleOCREngine(warmup=False)

        temp_source = ScreenshotSource()
        temp_source.ocr_engine = ocr_engine_instance
        extracted_text = None
        try:
            extracted_text = temp_source.get_text(coords=coords, status_callback=status_update, cancel_event=cancel_event)
        except Exception as ocr_error:
            status_update(f"Error during OCR: {str(ocr_error)}")
        finally:
            temp_source.cleanup_all()

        if cancel_event.is_set():
            print("Multi-capture OCR was cancelled.")
            return

        if extracted_text:
            multi_capture_texts.append(extracted_text)
            status_update(f"Captured {len(multi_capture_texts)} images... Multiple capture mode")
        else:
            status_update(f"No text found. Captured {len(multi_capture_texts)} images... Multiple capture mode")
    except Exception as multi_capture_error:
        print(f"Error during multi-capture: {multi_capture_error}")
        from core.output import show_popup
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {multi_capture_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)

def handle_multi_capture(config, active_profile):
    global is_processing, is_multi_capturing, multi_capture_texts, cancel_event
    if is_processing: return

    from core.output import update_multi_state, get_coordinates, show_popup
    if not is_multi_capturing:
        is_multi_capturing = True
        multi_capture_texts = []
        update_multi_state(True)

    if "popup" in config.get("output_mode", ["popup"]):
        show_popup("Multiple capture mode", auto_close=None, opacity=config.get("popup_opacity", 0.8), is_result=False)

    coords = get_coordinates()
    if not coords or cancel_event.is_set():
        print("Multi-capture: Selection cancelled.")
        is_multi_capturing = False
        update_multi_state(False)
        return

    set_processing(True)
    status_update = _create_status_update(config)
    threading.Thread(target=_execute_multi_capture, args=(config, coords, status_update), daemon=True).start()


def _execute_end_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts, llm_engine_instance, fallback_llm_engine_instance
    try:
        if not multi_capture_texts:
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup("No text captured in multi-capture mode.", auto_close=3000, opacity=config.get("popup_opacity", 0.8), is_result=False)
            is_multi_capturing = False
            update_multi_state(False)
            return

        combined_text = "\n\n".join(multi_capture_texts)
        print(f"Combined Text:\n{combined_text}")
        status_update = _create_status_update(config)

        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        from core.sources import TextSource
        temp_source = TextSource()

        assert llm_engine_instance is not None
        result = process_pipeline(
            source=temp_source, llm=llm_engine_instance, prompt_text=active_prompt_text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink, fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            text=combined_text, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if cancel_event.is_set():
            print("Multi-capture processing was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as multi_error:
        print(f"Error during processing multi-capture: {multi_error}")
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {multi_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)
        is_multi_capturing = False
        multi_capture_texts = []

def _execute_end_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts, llm_engine_instance, fallback_llm_engine_instance, cancel_event, session_manager
    try:
        from core.output import show_popup, update_multi_state
        if not multi_capture_texts:
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup("No text captured in multi-capture mode.", auto_close=3000, opacity=config.get("popup_opacity", 0.8), is_result=False)
            is_multi_capturing = False
            update_multi_state(False)
            return

        combined_text = "\n\n".join(multi_capture_texts)
        print(f"Combined Text:\n{combined_text}")
        status_update = _create_status_update(config)

        fallback_model = active_profile.get("fallback_model", "None")
        prompt_id = active_profile.get("prompt_id", "default")
        show_headers = fallback_model and fallback_model != "None" and prompt_id != "quick"

        sink, popup_sink = _setup_pipeline_sinks(config, active_profile, show_headers, cancel_event)

        from core.sources import TextSource
        from core.pipeline import process_pipeline
        temp_source = TextSource()

        assert llm_engine_instance is not None
        result = process_pipeline(
            source=temp_source, llm=llm_engine_instance, prompt_text=active_prompt_text,
            status_callback=status_update, session_manager=session_manager,
            enable_stitching=active_profile.get("enable_stitching", True),
            sink=sink, fallback_llm=fallback_llm_engine_instance if "fallback_llm_engine_instance" in globals() else None,
            text=combined_text, cancel_event=cancel_event
        )
        if hasattr(sink, "finish"): sink.finish()
        if cancel_event.is_set():
            print("Multi-capture processing was cancelled.")
            return

        print(f"Result: {result}")
        _output_pipeline_result(config, active_profile, result, show_headers, popup_sink)
    except Exception as multi_error:
        print(f"Error during processing multi-capture: {multi_error}")
        from core.output import show_popup
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(f"Error: {multi_error}", auto_close=5000, opacity=config.get("popup_opacity", 0.8), is_result=False)
    finally:
        set_processing(False)
        is_multi_capturing = False
        multi_capture_texts = []

def handle_end_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts
    if is_processing or not is_multi_capturing: return

    from core.output import get_active_source_instance, update_multi_state
    active_source = get_active_source_instance()
    if active_source and active_source.name != "image": return

    set_processing(True)
    update_multi_state(False)
    threading.Thread(target=_execute_end_multi_capture, args=(config, active_profile, active_prompt_text), daemon=True).start()


def handle_new_chat_session(config):
    global session_manager
    if session_manager:
        session_id = session_manager.start_new_session()
        # Visual reset and popup
        if "popup" in config.get("output_mode", ["popup"]):
            # Close any open popup first
            close_popup()

            # Then show the new status popup
            show_popup(
                f"New Chat Session Started\nID: {session_id}",
                auto_close=3000,
                opacity=config.get("popup_opacity", 0.8),
                is_result=False,
            )


def handle_toggle_stitching(config, active_profile):
    current = active_profile.get("enable_stitching", True)
    active_profile["enable_stitching"] = not current

    # Save the profiles
    profiles = load_profiles()
    for p in profiles:
        if p["id"] == active_profile["id"]:
            p["enable_stitching"] = not current
            break

    from config.settings import save_profiles

    save_profiles(profiles)

    state_str = "Enabled" if not current else "Disabled"
    if "popup" in config.get("output_mode", ["popup"]):
        show_popup(
            f"Chat Stitching {state_str}",
            auto_close=3000,
            opacity=config.get("popup_opacity", 0.8),
            is_result=False,
        )


def handle_toggle_panel():
    # Toggle control panel state internally
    toggle_control_panel()


def handle_cancel():
    global is_processing, is_multi_capturing, multi_capture_texts
    print("Cancel requested.")
    cancel_event.set()

    # Reset multi-capture state if it was active
    if is_multi_capturing:
        is_multi_capturing = False
        multi_capture_texts = []
        update_multi_state(False)

    # Close any open popups and show a "Canceled" message
    from core.output import ui_signals

    ui_signals.close_popup.emit()
    show_popup("Cancelled", auto_close=2000, is_result=False)

    # This will be called in the finally block of the processing threads
    # set_processing(False)


def handle_start_record(config, enable_transcription):
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    def status_update(msg):
        from core.output import ui_signals

        if "popup" in config.get("output_mode", ["popup"]):
            ui_signals.show_popup.emit(
                {
                    "text": msg,
                    "auto_close": 3000,
                    "opacity": config.get("popup_opacity", 0.8),
                    "is_result": False,
                }
            )

    active_source.start_recording(
        status_callback=status_update, enable_transcription=enable_transcription
    )


def handle_stop_record(config, active_profile, _active_prompt_text, is_long_press):
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    from core.output import ui_signals

    def status_update(msg):
        if "popup" in config.get("output_mode", ["popup"]):
            ui_signals.show_popup.emit(
                {
                    "text": msg,
                    "auto_close": None,
                    "opacity": config.get("popup_opacity", 0.8),
                    "is_result": False,
                }
            )

    status_update("Processing audio...")

    def _process_audio():
        assert active_source is not None
        assert isinstance(active_source, SoundSource)
        text = active_source.stop_recording()

        if not is_long_press:
            status_update("Transcription stopped.")
            from core.output import clear_subtitles

            clear_subtitles()
            return

        if not text:
            status_update("No speech recognized.")
            return

        print(f"Recognized Speech: {text}")
        status_update(f"Recognized: {text}\nSending to LLM...")

        # We need to dispatch handle_text_submit via the callback dict or threading to not block,
        # but handle_text_submit itself spawns a thread. Let's just call it directly.
        handle_text_submit(config, active_profile, text)

    threading.Thread(target=_process_audio, daemon=True).start()


def handle_cycle_source(config, active_profile):
    global ocr_engine_instance
    from core.sources import ScreenshotSource, TextSource

    active_source = get_active_source_instance()
    if isinstance(active_source, TextSource):
        new_source = ScreenshotSource()
        if (
            ocr_engine_instance is None
            and active_profile.get("ocr_engine", "none") == "paddleocr"
        ):
            print("Loading PaddleOCR engine on demand for cycle source...")
            from core.sources.ocr import LocalPaddleOCREngine

            ocr_engine_instance = LocalPaddleOCREngine(warmup=False)
        new_source.ocr_engine = ocr_engine_instance
    elif isinstance(active_source, ScreenshotSource):
        global session_manager
        new_source = SoundSource(config, session_manager=session_manager)
    else:
        new_source = TextSource()

    set_active_source_instance(new_source)
    set_active_source_ui(new_source.name, opacity=config.get("popup_opacity", 0.8))
    print(f"Source cycled to: {new_source.name}")
    if "popup" in config.get("output_mode", ["popup"]):
        show_popup(
            f"Source changed to: {new_source.name.capitalize()}",
            auto_close=2000,
            opacity=config.get("popup_opacity", 0.8),
            is_result=False,
        )


def handle_reselect(config):
    global is_processing
    if is_processing:
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


def exit_app():
    global is_running, session_manager
    is_running = False
    print("Exiting...")

    if session_manager:
        session_manager.cleanup()

    app = QApplication.instance()
    if app:
        app.quit()
    keyboard.unhook_all()
    sys.exit(0)


def load_models_data():
    try:
        models_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "config", "llm_models.json"
        )
        with open(models_path, "r") as f:
            return json.load(f)
    except Exception as models_error:
        print(f"Warning: Could not load llm_models.json: {models_error}")
        return {}


def validate_config(active_profile):
    llm_type = active_profile.get("llm_engine", "gemini")
    model_id = active_profile.get("model", GEMINI_2_5_FLASH_LITE)
    fallback_model_id = active_profile.get("fallback_model", "None")
    ocr_type = active_profile.get("ocr_engine", "none")

    models_data = load_models_data()
    models = models_data.get(llm_type, [])

    supports_ocr = False
    for m in models:
        if m.get("id") == model_id:
            supports_ocr = m.get("supports_ocr", False)
            break

    if not supports_ocr and ocr_type == "none":
        print(
            f"Error: Selected model '{model_id}' does not support built-in OCR and no OCR engine is configured."
        )
        print("Please configure an OCR engine or select a model that supports OCR.")
        sys.exit(1)

    if fallback_model_id and fallback_model_id != "None":
        fallback_supports_ocr = False
        for m in models:
            if m.get("id") == fallback_model_id:
                fallback_supports_ocr = m.get("supports_ocr", False)
                break

        if not fallback_supports_ocr and ocr_type == "none":
            print(
                f"Error: Selected fallback model '{fallback_model_id}' does not support built-in OCR and no OCR engine is configured."
            )
            print(
                "Please configure an OCR engine or select a fallback model that supports OCR."
            )
            sys.exit(1)


def _read_warmup_stream(stream, prefix, is_error=False):
    import sys
    for line in iter(stream.readline, ""):
        if is_error:
            print(f"{prefix} {line.strip()}", file=sys.stderr)
        else:
            print(f"{prefix} {line.strip()}")
    stream.close()

def _run_whisperlive_warmup(script_path):
    import subprocess, sys, threading
    try:
        process = subprocess.Popen(
            [sys.executable, script_path], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True
        )
        t1 = threading.Thread(target=_read_warmup_stream, args=(process.stdout, "[WhisperLive Warmup]"), daemon=True)
        t2 = threading.Thread(target=_read_warmup_stream, args=(process.stderr, "[WhisperLive Warmup ERR]", True), daemon=True)
        t1.start()
        t2.start()
        process.wait()
        t1.join()
        t2.join()
        if process.returncode == 0:
            print("Real-time transcription warmup completed successfully.")
        else:
            print(f"Real-time transcription warmup failed with code {process.returncode}")
    except Exception as warmup_error:
        print(f"Error executing warmup script: {warmup_error}")

def _read_warmup_stream(stream, prefix, is_error=False):
    import sys
    for line in iter(stream.readline, ""):
        if is_error:
            print(f"{prefix} {line.strip()}", file=sys.stderr)
        else:
            print(f"{prefix} {line.strip()}")
    stream.close()

def _run_whisperlive_warmup(script_path):
    import subprocess, sys, threading
    try:
        process = subprocess.Popen(
            [sys.executable, script_path], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True
        )
        t1 = threading.Thread(target=_read_warmup_stream, args=(process.stdout, "[WhisperLive Warmup]"), daemon=True)
        t2 = threading.Thread(target=_read_warmup_stream, args=(process.stderr, "[WhisperLive Warmup ERR]", True), daemon=True)
        t1.start()
        t2.start()
        process.wait()
        t1.join()
        t2.join()
        if process.returncode == 0:
            print("Real-time transcription warmup completed successfully.")
        else:
            print(f"Real-time transcription warmup failed with code {process.returncode}")
    except Exception as warmup_error:
        print(f"Error executing warmup script: {warmup_error}")

def warmup_whisperlive_process(_config):
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "sanity", "test_whisperlive_warmup.py")
        if os.path.exists(script_path):
            print("Running Real-time transcription warmup (test_whisperlive_warmup.py)...")
            threading.Thread(target=_run_whisperlive_warmup, args=(script_path,), daemon=True).start()
        else:
            print("Warning: Real-time transcription warmup script not found.")
    except Exception as init_error:
        print(f"Error initializing Real-time transcription warmup: {init_error}")


def _setup_app_ui(config):
    global app
    app = QApplication(sys.argv)
    if "linux" in sys.platform:
        app.setQuitOnLastWindowClosed(False)
    icon_path = os.path.join("assets", "tray_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    _app_callbacks["capture"] = lambda coords=None: handle_hotkey_capture(coords=coords)
    _app_callbacks["multi_capture"] = lambda coords=None: handle_multi_capture(config, get_active_profile(config)[1], coords=coords)
    _app_callbacks["end_multi_capture"] = lambda: handle_end_multi_capture(config, *get_active_profile(config)[1:])
    _app_callbacks["cancel_multi_capture"] = lambda: handle_cancel_multi_capture(config)
    _app_callbacks["toggle_panel"] = lambda: ui_broker.toggle_panel_signal.emit()
    _app_callbacks["cancel"] = lambda: cancel_event.set()
    _app_callbacks["text_submit"] = lambda text: handle_text_submit(config, get_active_profile(config)[1], text)
    _app_callbacks["cancel_source"] = lambda: handle_cancel_source()

    ui_broker.config_changed.connect(handle_config_changed)
    ui_broker.source_changed.connect(handle_source_changed)

def _init_session(config):
    global session_manager
    if config.get("resume_session"):
        session_manager = SessionManager(session_id=config.get("resume_session"), save_transcriptions=config.get("save_transcriptions"))
        print(f"Resuming session: {session_manager.session_id}")
    else:
        session_manager = SessionManager(save_transcriptions=config.get("save_transcriptions"))

def _setup_app_ui(config, active_profile, active_prompt_text):
    global app
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon
    from core.output import set_app_callbacks, ui_broker

    app = QApplication(sys.argv)
    if "linux" in sys.platform: app.setQuitOnLastWindowClosed(False)
    icon_path = os.path.join("assets", "tray_icon.png")
    if os.path.exists(icon_path): app.setWindowIcon(QIcon(icon_path))

    callbacks = {
        "capture": lambda: handle_capture(config, active_profile, active_prompt_text),
        "reselect": lambda: handle_reselect(config),
        "multi_capture": lambda: handle_multi_capture(config, active_profile),
        "end_multi_capture": lambda: handle_end_multi_capture(config, active_profile, active_prompt_text),
        "cancel": handle_cancel,
        "toggle_stitching": lambda: handle_toggle_stitching(config, active_profile),
        "cycle_source": lambda: handle_cycle_source(config, active_profile),
        "text_submit": lambda text: handle_text_submit(config, active_profile, text),
        "start_record": lambda enable_transcription: handle_start_record(config, enable_transcription),
        "stop_record": lambda is_long_press: handle_stop_record(config, active_profile, active_prompt_text, is_long_press),
    }

    from core.output import init_ui_manager
    init_ui_manager()
    set_app_callbacks(callbacks)

    ui_broker.config_changed.connect(handle_config_changed)
    ui_broker.source_changed.connect(handle_source_changed)

def _init_session(config):
    from core.session_manager import SessionManager
    global session_manager
    if config.get("resume_session"):
        session_manager = SessionManager(session_id=config.get("resume_session"), save_transcriptions=config.get("save_transcriptions"))
        print(f"Resuming session: {session_manager.session_id}")
    else:
        session_manager = SessionManager(save_transcriptions=config.get("save_transcriptions"))

def _run_warmups(config, active_profile):
    from core.output import get_active_source_instance
    from core.sources import SoundSource
    global audio_sink_instance

    if config.get("warmup_tts", False) and hasattr(audio_sink_instance, "warmup"):
        threading.Thread(target=audio_sink_instance.warmup, daemon=True).start()

    if config.get("warmup_speech_recognition", True):
        temp_sr = SoundSource(config, session_manager=session_manager)
        threading.Thread(target=temp_sr.warmup, daemon=True).start()

    if config.get("warmup_realtime_transcription", False):
        warmup_whisperlive_process(config)

def main():
    global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance
    global audio_sink_instance, active_source_name, active_source, app, session_manager
    from config import load_config, get_active_profile
    from core.sinks.audio import AudioSink

    config = load_config()
    active_profile_id, active_profile, active_prompt_text = get_active_profile(config)

    from core.output import validate_config
    validate_config(active_profile)
    _init_session(config)

    audio_sink_instance = AudioSink(config, cancel_event)
    audio_sink_instance.warmup()

    from core.output import update_instances, get_active_source_instance, set_active_source_instance
    from core.sources import ScreenshotSource, SoundSource, TextSource

    default_source = config.get("default_source", "text")
    if default_source == "image": set_active_source_instance(ScreenshotSource())
    elif default_source == "audio": set_active_source_instance(SoundSource(config, session_manager=session_manager))
    else: set_active_source_instance(TextSource())

    active_source = get_active_source_instance()

    _setup_app_ui(config, active_profile, active_prompt_text)

    from core.output import set_active_source_ui, toggle_control_panel
    set_active_source_ui(active_source.name if active_source else "text", opacity=config.get("popup_opacity", 0.8))
    if config.get("show_control_panel", False): toggle_control_panel(True)

    update_instances(config)
    _run_warmups(config, active_profile)

    bind_hotkeys(config)

    from core.output import run_tray, show_config_panel
    run_tray(config, show_config_panel)
    logger.info("Main loop started. Waiting for hotkeys...")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
