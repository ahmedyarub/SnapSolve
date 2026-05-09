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


def handle_text_submit(config, active_profile, text):
    global is_processing
    if is_processing:
        return

    set_processing(True)
    print(f"Processing text input: {text}")

    def status_update(msg):
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(
                msg,
                auto_close=None,
                opacity=config.get("popup_opacity", 0.8),
                is_result=False,
            )

    def _process():
        try:
            global \
                ocr_engine_instance, \
                llm_engine_instance, \
                fallback_llm_engine_instance, \
                audio_sink_instance
            show_headers = False
            fallback_model = active_profile.get("fallback_model", "None")
            main_model = active_profile.get("model", "gemini-2.5-flash-lite")
            prompt_id = active_profile.get("prompt_id", "default")

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            popup_sink = PopupSink(
                config, show_headers, main_model, fallback_model, cancel_event
            )

            assert audio_sink_instance is not None
            sink = CompositeSink([popup_sink, audio_sink_instance], cancel_event)

            from core.sources import TextSource

            temp_source = TextSource()

            assert llm_engine_instance is not None

            result = process_pipeline(
                source=temp_source,
                llm=llm_engine_instance,
                prompt_text=text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get("enable_stitching", True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance
                if "fallback_llm_engine_instance" in globals()
                else None,
                text=text,
                cancel_event=cancel_event,
            )
            if hasattr(sink, "finish"):
                sink.finish()

            if cancel_event.is_set():
                print("Text processing was cancelled.")
                return

            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if (
                    popup_sink.accumulated_fallback
                    and len(popup_sink.accumulated_result) == 1
                ):
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(
                final_result,
                config.get("output_mode"),
                None,  # Deprecated voice_id
                auto_close=config.get("auto_close_results", False),
                opacity=config.get("popup_opacity", 0.8),
            )
        except Exception as text_error:
            print(f"Error during processing text input: {text_error}")
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup(
                    f"Error: {text_error}",
                    auto_close=5000,
                    opacity=config.get("popup_opacity", 0.8),
                    is_result=False,
                )
        finally:
            set_processing(False)

    threading.Thread(target=_process, daemon=True).start()


def handle_capture(config, active_profile, active_prompt_text):
    global is_processing
    if is_processing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name == "audio":
        from core.output import ui_manager

        if ui_manager and ui_manager.panel:
            record_btn = ui_manager.panel.btn_record
            if record_btn.is_recording:
                record_btn.stop_record_action()
            else:
                record_btn.start_record_action()
        return

    if active_source and active_source.name != "image":
        print(f"Capture is disabled for {active_source.name} source.")
        return

    set_processing(True)
    print("Capturing and processing...")

    def status_update(msg):
        if "popup" in config.get("output_mode", ["popup"]):
            show_popup(
                msg,
                auto_close=None,
                opacity=config.get("popup_opacity", 0.8),
                is_result=False,
            )

    def _capture():
        try:
            global \
                ocr_engine_instance, \
                llm_engine_instance, \
                fallback_llm_engine_instance, \
                audio_sink_instance
            active_src = get_active_source_instance()

            if (
                ocr_engine_instance is None
                and active_profile.get("ocr_engine", "none") == "paddleocr"
            ):
                print("Loading PaddleOCR engine on demand...")
                from core.sources.ocr import LocalPaddleOCREngine

                ocr_engine_instance = LocalPaddleOCREngine(warmup=False)
                if hasattr(active_src, "ocr_engine"):
                    active_src.ocr_engine = ocr_engine_instance

            show_headers = False
            fallback_model = active_profile.get("fallback_model", "None")
            main_model = active_profile.get("model", "gemini-2.5-flash-lite")
            prompt_id = active_profile.get("prompt_id", "default")

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            popup_sink = PopupSink(
                config, show_headers, main_model, fallback_model, cancel_event
            )
            # Use the global audio_sink_instance
            assert audio_sink_instance is not None
            sink = CompositeSink([popup_sink, audio_sink_instance], cancel_event)

            assert active_src is not None
            assert llm_engine_instance is not None

            result = process_pipeline(
                source=active_src,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get("enable_stitching", True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance
                if "fallback_llm_engine_instance" in globals()
                else None,
                coords=config.get("coordinates"),
                cancel_event=cancel_event,
            )
            if hasattr(sink, "finish"):
                sink.finish()

            if hasattr(active_src, "cleanup_all"):
                active_src.cleanup_all()

            if cancel_event.is_set():
                print("Capture processing was cancelled.")
                return

            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if (
                    popup_sink.accumulated_fallback
                    and len(popup_sink.accumulated_result) == 1
                ):
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(
                final_result,
                config.get("output_mode"),
                None,  # Deprecated voice_id
                auto_close=config.get("auto_close_results", False),
                opacity=config.get("popup_opacity", 0.8),
            )
        except Exception as processing_error:
            print(f"Error during processing: {processing_error}")
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup(
                    f"Error: {processing_error}",
                    auto_close=5000,
                    opacity=config.get("popup_opacity", 0.8),
                    is_result=False,
                )
        finally:
            set_processing(False)

    # Must run in a separate thread so we don't block the global keyboard hook
    threading.Thread(target=_capture, daemon=True).start()


def handle_multi_capture(config, active_profile):
    global is_processing
    if is_processing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        print(f"Multi-capture is disabled for {active_source.name} source.")
        return

    set_processing(True)

    def _multi_capture():
        global is_multi_capturing, multi_capture_texts, ocr_engine_instance
        try:
            ocr_type = active_profile.get("ocr_engine", "none")
            if ocr_type == "none":
                if "popup" in config.get("output_mode", ["popup"]):
                    show_popup(
                        "Error: Multi-capture requires an OCR engine to be defined in the active profile.",
                        auto_close=5000,
                        opacity=config.get("popup_opacity", 0.8),
                        is_result=False,
                    )
                return

            if not is_multi_capturing:
                is_multi_capturing = True
                multi_capture_texts = []
                update_multi_state(True)

            if "popup" in config.get("output_mode", ["popup"]):
                show_popup(
                    "Multiple capture mode",
                    auto_close=None,
                    opacity=config.get("popup_opacity", 0.8),
                    is_result=False,
                )

            # Get coordinates specifically for this capture (don't update config)
            coords = get_coordinates()
            if not coords or cancel_event.is_set():
                print("Multi-capture: Selection cancelled.")
                if is_multi_capturing:
                    handle_cancel()
                return

            def status_update(msg):
                if "popup" in config.get("output_mode", ["popup"]):
                    show_popup(
                        msg,
                        auto_close=None,
                        opacity=config.get("popup_opacity", 0.8),
                        is_result=False,
                    )

            status_update("Capturing screen...")

            if (
                ocr_engine_instance is None
                and active_profile.get("ocr_engine", "none") == "paddleocr"
            ):
                status_update("Loading PaddleOCR engine...")
                from core.sources.ocr import LocalPaddleOCREngine

                ocr_engine_instance = LocalPaddleOCREngine(warmup=False)

            temp_source = ScreenshotSource()
            temp_source.ocr_engine = ocr_engine_instance
            extracted_text = None
            try:
                extracted_text = temp_source.get_text(
                    coords=coords,
                    status_callback=status_update,
                    cancel_event=cancel_event,
                )
            except Exception as ocr_error:
                status_update(f"Error during OCR: {str(ocr_error)}")
            finally:
                temp_source.cleanup_all()

            if cancel_event.is_set():
                print("Multi-capture OCR was cancelled.")
                return

            if extracted_text:
                multi_capture_texts.append(extracted_text)
                status_update(
                    f"Captured {len(multi_capture_texts)} images... Multiple capture mode"
                )
            else:
                status_update(
                    f"No text found. Captured {len(multi_capture_texts)} images... Multiple capture mode"
                )

        except Exception as multi_capture_error:
            print(f"Error during multi-capture: {multi_capture_error}")
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup(
                    f"Error: {multi_capture_error}",
                    auto_close=5000,
                    opacity=config.get("popup_opacity", 0.8),
                    is_result=False,
                )
        finally:
            set_processing(False)

    threading.Thread(target=_multi_capture, daemon=True).start()


def handle_end_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts
    if is_processing:
        return

    if not is_multi_capturing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        return

    set_processing(True)

    # Immediately update UI state to hide buttons before processing starts
    update_multi_state(False)

    def _end_multi_capture():
        global \
            is_processing, \
            is_multi_capturing, \
            multi_capture_texts, \
            llm_engine_instance, \
            fallback_llm_engine_instance, \
            audio_sink_instance
        try:
            if not multi_capture_texts:
                if "popup" in config.get("output_mode", ["popup"]):
                    show_popup(
                        "No text captured in multi-capture mode.",
                        auto_close=3000,
                        opacity=config.get("popup_opacity", 0.8),
                        is_result=False,
                    )
                is_multi_capturing = False
                update_multi_state(False)
                return

            combined_text = "\n\n".join(multi_capture_texts)
            print(f"Combined Text:\n{combined_text}")

            def status_update(msg):
                if "popup" in config.get("output_mode", ["popup"]):
                    show_popup(
                        msg,
                        auto_close=None,
                        opacity=config.get("popup_opacity", 0.8),
                        is_result=False,
                    )

            show_headers = False
            fallback_model = active_profile.get("fallback_model", "None")
            main_model = active_profile.get("model", "gemini-2.5-flash-lite")
            prompt_id = active_profile.get("prompt_id", "default")

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            popup_sink = PopupSink(
                config, show_headers, main_model, fallback_model, cancel_event
            )
            # Use the global audio_sink_instance
            assert audio_sink_instance is not None
            sink = CompositeSink([popup_sink, audio_sink_instance], cancel_event)

            from core.sources import TextSource

            temp_source = TextSource()

            assert llm_engine_instance is not None
            result = process_pipeline(
                source=temp_source,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get("enable_stitching", True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance
                if "fallback_llm_engine_instance" in globals()
                else None,
                text=combined_text,
                cancel_event=cancel_event,
            )
            if hasattr(sink, "finish"):
                sink.finish()

            if cancel_event.is_set():
                print("Multi-capture processing was cancelled.")
                return

            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if (
                    popup_sink.accumulated_fallback
                    and len(popup_sink.accumulated_result) == 1
                ):
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(
                final_result,
                config.get("output_mode"),
                None,  # Deprecated voice_id
                auto_close=config.get("auto_close_results", False),
                opacity=config.get("popup_opacity", 0.8),
            )

        except Exception as multi_error:
            print(f"Error during processing multi-capture: {multi_error}")
            if "popup" in config.get("output_mode", ["popup"]):
                show_popup(
                    f"Error: {multi_error}",
                    auto_close=5000,
                    opacity=config.get("popup_opacity", 0.8),
                    is_result=False,
                )
        finally:
            set_processing(False)
            is_multi_capturing = False
            multi_capture_texts = []

    threading.Thread(target=_end_multi_capture, daemon=True).start()


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


def handle_stop_record(config, active_profile, active_prompt_text, is_long_press):
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
        new_source = SoundSource(config)
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
    global is_running
    is_running = False
    print("Exiting...")
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
    model_id = active_profile.get("model", "gemini-2.5-flash-lite")
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


def warmup_whisperlive_process(config):
    """Executes the test_whisperlive_warmup script from main thread as a warmup."""
    try:
        import subprocess
        # Get path to test_whisperlive_warmup.py
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests", "sanity", "test_whisperlive_warmup.py")
        if os.path.exists(script_path):
            print("Running Real-time transcription warmup (test_whisperlive_warmup.py)...")
            
            # Start process asynchronously
            def _run_warmup():
                try:
                    process = subprocess.Popen(
                        [sys.executable, script_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,  # Line buffered
                        universal_newlines=True
                    )
                    
                    # Read stdout in a background thread to print in real time
                    def _read_stdout():
                        for line in iter(process.stdout.readline, ''):
                            print(f"[WhisperLive Warmup] {line.strip()}")
                        process.stdout.close()
                        
                    def _read_stderr():
                        for line in iter(process.stderr.readline, ''):
                            print(f"[WhisperLive Warmup ERR] {line.strip()}", file=sys.stderr)
                        process.stderr.close()
                        
                    t1 = threading.Thread(target=_read_stdout, daemon=True)
                    t2 = threading.Thread(target=_read_stderr, daemon=True)
                    t1.start()
                    t2.start()
                    
                    process.wait()
                    t1.join()
                    t2.join()
                    
                    if process.returncode == 0:
                        print("Real-time transcription warmup completed successfully.")
                    else:
                        print(f"Real-time transcription warmup failed with code {process.returncode}")
                except Exception as e:
                    print(f"Error executing warmup script: {e}")
                    
            threading.Thread(target=_run_warmup, daemon=True).start()
        else:
            print("Warning: Real-time transcription warmup script not found.")
    except Exception as e:
        print(f"Error initializing Real-time transcription warmup: {e}")

def main():
    # Configure logging early
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    global is_running

    # Initialize PyQt application in the main thread
    app = QApplication.instance()
    if not app:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv)
        # Needed for tray icon to keep app alive if windows are closed
        app.setQuitOnLastWindowClosed(False)

    print("Initializing Screen Capture & Gemini QA App...")

    config = get_config()
    profiles = load_profiles()
    prompts = load_prompts()

    active_profile_id = config.get("active_profile_id", "prof1")
    active_profile = next(
        (p for p in profiles if p.get("id") == active_profile_id),
        profiles[0] if profiles else {},
    )

    prompt_id = active_profile.get("prompt_id", "default")
    active_prompt = next(
        (p for p in prompts if p.get("id") == prompt_id), prompts[0] if prompts else {}
    )
    active_prompt_text = active_prompt.get(
        "text", "answer the following question quickly and briefly"
    )

    validate_config(active_profile)

    # Determine the initial source
    default_source = config.get("default_source", "text")
    if default_source == "image":
        set_active_source_instance(ScreenshotSource())
    elif default_source == "audio":
        set_active_source_instance(SoundSource(config))
    else:
        set_active_source_instance(TextSource())

    active_source = get_active_source_instance()

    # Set up UI callbacks before starting the main loop
    callbacks = {
        "capture": lambda: handle_capture(config, active_profile, active_prompt_text),
        "reselect": lambda: handle_reselect(config),
        "multi_capture": lambda: handle_multi_capture(config, active_profile),
        "end_multi_capture": lambda: handle_end_multi_capture(
            config, active_profile, active_prompt_text
        ),
        "cancel": handle_cancel,
        "toggle_stitching": lambda: handle_toggle_stitching(config, active_profile),
        "cycle_source": lambda: handle_cycle_source(config, active_profile),
        "text_submit": lambda text: handle_text_submit(config, active_profile, text),
        "start_record": lambda enable_transcription: handle_start_record(
            config, enable_transcription
        ),
        "stop_record": lambda is_long_press: handle_stop_record(
            config, active_profile, active_prompt_text, is_long_press
        ),
    }
    # Initialize the UI Manager and set callbacks
    from core.output import init_ui_manager

    init_ui_manager()
    set_app_callbacks(callbacks)

    # Initialize the UI with the active source before showing the panel
    set_active_source_ui(
        active_source.name if active_source else "text",
        opacity=config.get("popup_opacity", 0.8),
    )

    if config.get("show_control_panel", False):
        toggle_control_panel(True)

    if (
        active_source
        and active_source.name == "image"
        and not config.get("coordinates")
    ):
        print("Coordinates not found in config. Launching coordinate selector...")
        coords = get_coordinates()
        if coords:
            config["coordinates"] = coords
            save_config(config)
            print(f"Coordinates saved: {coords}")
        else:
            print("No coordinates selected. Exiting.")
            sys.exit(1)

    # Initialize Engines
    print("Checking engine pre-initialization...")
    global \
        ocr_engine_instance, \
        llm_engine_instance, \
        fallback_llm_engine_instance, \
        session_manager, \
        audio_sink_instance
    session_manager = SessionManager(config)
    ocr_type = active_profile.get("ocr_engine", "none")
    if ocr_type == "paddleocr":
        ocr_engine_instance = LocalPaddleOCREngine(
            status_callback=lambda msg: print(f"Init status: {msg}")
        )
    elif ocr_type == "remote_paddle":
        ocr_config = config.get("ocr_config", {})
        ocr_engine_instance = RemotePaddleOCREngine(
            config=ocr_config, status_callback=lambda msg: print(f"Init status: {msg}")
        )
    else:
        ocr_engine_instance = NoOCREngine()

    if config.get("warmup_ocr", True) and hasattr(ocr_engine_instance, "warmup"):
        ocr_engine_instance.warmup()

    if isinstance(active_source, ScreenshotSource):
        active_source.ocr_engine = ocr_engine_instance
        set_active_source_instance(active_source)

    llm_type = active_profile.get("llm_engine", "gemini")
    model = active_profile.get("model", "gemini-2.5-flash-lite")
    fallback_model = active_profile.get("fallback_model", "None")

    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(
            model,
            config.get("ollama_url", "http://localhost:11434"),
            session_manager=session_manager,
        )
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine_instance = OllamaEngine(
                fallback_model,
                config.get("ollama_url", "http://localhost:11434"),
                session_manager=session_manager,
            )
    elif llm_type == "google-genai":
        llm_engine_instance = GoogleGenAIEngine(
            model,
            config.get("google_genai_api_key", ""),
            session_manager=session_manager,
        )
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GoogleGenAIEngine(
                fallback_model,
                config.get("google_genai_api_key", ""),
                session_manager=session_manager,
            )
    else:
        llm_engine_instance = GeminiCLIEngine(model, session_manager=session_manager)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GeminiCLIEngine(
                fallback_model, session_manager=session_manager
            )

    # Perform Warmup: fallback first, then main if fallback fails or doesn't exist
    def warmup_status_cb(msg):
        print(f"Init status: {msg}")

    warmup_success = False
    if config.get("warmup_llm", True):
        if (
            fallback_model
            and fallback_model != "None"
            and "fallback_llm_engine_instance" in globals()
        ):
            assert fallback_llm_engine_instance is not None
            warmup_success = fallback_llm_engine_instance.warmup(
                status_callback=warmup_status_cb
            )

        if not warmup_success and llm_engine_instance:
            llm_engine_instance.warmup(status_callback=warmup_status_cb)

    # Initialize AudioSink globally
    audio_sink_instance = AudioSink(config, cancel_event)

    # Warmup AudioSink asynchronously if enabled
    if config.get("warmup_tts", False) and hasattr(audio_sink_instance, "warmup"):
        threading.Thread(target=audio_sink_instance.warmup, daemon=True).start()

    # Warmup Speech Recognition asynchronously if enabled
    if config.get("warmup_speech_recognition", True):
        temp_sr = SoundSource(config)
        threading.Thread(target=temp_sr.warmup, daemon=True).start()
        
    # Warmup WhisperLive (Real-time transcription) if enabled
    if config.get("warmup_realtime_transcription", False):
        warmup_whisperlive_process(config)

    # Function to test transcription display
    def handle_test_transcription():
        import random
        from core.output import show_subtitle

        test_text = f"Transcription test with random number: {random.randint(1, 1000)}"
        print(f"Testing transcription display: {test_text}")
        show_subtitle(test_text)
        
    def handle_select_subtitle(index):
        text = get_subtitle_text(index)
        if text:
            print(f"Selected subtitle {index}: {text}")
            handle_text_submit(config, active_profile, text)
        else:
            print(f"No subtitle found at index {index}")

    # Register keyboard shortcuts
    keyboard.add_hotkey("ctrl+alt+shift+t", handle_test_transcription)
    
    for i in range(1, 6):
        keyboard.add_hotkey(f"ctrl+alt+shift+{i}", handle_select_subtitle, args=(i,))

    hotkeys = config.get("hotkeys", [])

    for hk in hotkeys:
        action = hk.get("action")
        key = hk.get("key")
        if not action or not key:
            continue

        print(f"Listening for '{action}' hotkey: {key}")

        if action == "capture":
            keyboard.add_hotkey(
                key, handle_capture, args=(config, active_profile, active_prompt_text)
            )
        elif action == "reselect":
            keyboard.add_hotkey(key, handle_reselect, args=(config,))
        elif action == "multi_capture":
            keyboard.add_hotkey(
                key,
                handle_multi_capture,
                args=(config, active_profile, active_prompt_text),
            )
        elif action == "end_multi_capture":
            keyboard.add_hotkey(
                key,
                handle_end_multi_capture,
                args=(config, active_profile, active_prompt_text),
            )
        elif action == "cancel":
            keyboard.add_hotkey(key, handle_cancel)
        elif action == "toggle_panel":
            keyboard.add_hotkey(key, handle_toggle_panel, args=(config,))
        elif action == "new_chat_session":
            keyboard.add_hotkey(key, handle_new_chat_session, args=(config,))
        elif action == "toggle_stitching":
            keyboard.add_hotkey(
                key, handle_toggle_stitching, args=(config, active_profile)
            )
        elif action == "cycle_source":
            keyboard.add_hotkey(key, handle_cycle_source, args=(config, active_profile))

    if config.get("background", False):
        print("Running in background tray mode with pystray...")

        def run_tray():
            icon = create_tray_icon(exit_app)
            icon.run()

        threading.Thread(target=run_tray, daemon=True).start()
    else:
        print("Running in console/Qt mode. Press Ctrl+C or close via tray to exit.")
        import signal

        signal.signal(signal.SIGINT, lambda sig, frame: exit_app())
        from PyQt6.QtCore import QTimer

        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)

    print("Initialization done.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()