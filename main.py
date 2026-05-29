import json
import logging
import os
import platform
import signal
import subprocess
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
    toggle_all_widgets,
    set_app_callbacks,
    update_multi_state,
    set_active_source_ui,
    set_app_processing_state,
    get_subtitle_text,
    set_hide_from_capture,
    share_response_screenshot,
)
from core.remote_control_server import (
    start_remote_control_server,
    stop_remote_control_server,
    is_android_connected,
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

# Default model name
DEFAULT_MODEL_NAME = "gemini-2.5-flash-lite"

# Enable Windows DPI awareness to fix coordinate scaling issues
if platform.system() == "Windows":
    import ctypes

    try:
        SetProcessDpiAwareness = getattr(ctypes.windll.shcore, "SetProcessDpiAwareness")
        SetProcessDpiAwareness(2)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")

    # Register a console control handler BEFORE any library (keyboard, Qt,
    # pystray) has a chance to install its own.  This ensures PyCharm's Stop
    # button (which sends CTRL_C_EVENT or CTRL_BREAK_EVENT) terminates the
    # process immediately via os._exit().
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def _console_ctrl_handler(ctrl_type):
        # CTRL_C_EVENT=0, CTRL_BREAK_EVENT=1, CTRL_CLOSE_EVENT=2,
        # CTRL_LOGOFF_EVENT=5, CTRL_SHUTDOWN_EVENT=6
        os._exit(0)
        return True  # pragma: no cover

    ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_ctrl_handler, True)


def create_tray_icon(on_exit):
    # Load custom tray icon from assets, fall back to generated if missing
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
    if os.path.exists(icon_path):
        img = Image.open(icon_path)
    else:
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


def _show_status_popup(config, message, auto_close=None):
    """Show a non-result popup if popup output mode is enabled."""
    if "popup" in config.get("output_mode", ["popup"]):
        show_popup(
            message,
            auto_close=auto_close,
            opacity=config.get("opacity", 0.8),
            is_result=False,
        )


def _make_status_callback(config):
    """Create a status callback that shows popup messages."""

    def status_update(msg):
        _show_status_popup(config, msg)

    return status_update


def _run_in_processing_thread(config, work_fn, error_label="processing"):
    """Run work_fn in a daemon thread with standard error handling and processing state management."""

    def _worker():
        try:
            work_fn()
        except Exception as err:
            print(f"Error during {error_label}: {err}")
            _show_status_popup(config, f"Error: {err}", auto_close=5000)
        finally:
            set_processing(False)

    threading.Thread(target=_worker, daemon=True).start()


def _ensure_ocr_engine(active_profile, status_callback=None):
    """Lazily initialize PaddleOCR engine if needed."""
    global ocr_engine_instance
    if (
        ocr_engine_instance is None
        and active_profile.get("ocr_engine", "none") == "paddleocr"
    ):
        if status_callback:
            status_callback("Loading PaddleOCR engine...")
        else:
            print("Loading PaddleOCR engine on demand...")
        from core.sources.ocr import LocalPaddleOCREngine

        ocr_engine_instance = LocalPaddleOCREngine(warmup=False)
    return ocr_engine_instance


def _execute_text_pipeline(
    config, active_profile, prompt_text, status_update, text=None
):
    """Execute text pipeline."""
    global llm_engine_instance, fallback_llm_engine_instance, audio_sink_instance

    if text is None:
        text = prompt_text

    main_model = active_profile.get("model", DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    sink, popup_sink, show_headers = _setup_capture_sinks(
        config, active_profile, main_model, fallback_model
    )

    temp_source = TextSource()

    assert llm_engine_instance is not None

    result = process_pipeline(
        source=temp_source,
        llm=llm_engine_instance,
        prompt_text=prompt_text,
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
        return None

    print(f"Result: {result}")

    _process_capture_result(
        result, show_headers, popup_sink, fallback_model, main_model, config
    )

    return result


def handle_text_submit(config, active_profile, text):
    global is_processing
    if is_processing:
        return

    set_processing(True)
    print(f"Processing text input: {text}")

    status_update = _make_status_callback(config)

    _run_in_processing_thread(
        config,
        lambda: _execute_text_pipeline(config, active_profile, text, status_update),
        error_label="processing text input",
    )


def _handle_audio_source_capture():
    """Handle audio source capture."""
    from core.output import ui_manager

    if ui_manager and ui_manager.panel:
        record_btn = ui_manager.panel.btn_record
        if record_btn.is_recording:
            record_btn.stop_record_action()
        else:
            record_btn.start_record_action()


def _setup_capture_sinks(config, active_profile, main_model, fallback_model):
    """Setup capture sinks."""
    show_headers = False
    prompt_id = active_profile.get("prompt_id", "default")

    if fallback_model and fallback_model != "None" and prompt_id != "quick":
        show_headers = True

    popup_sink = PopupSink(
        config, show_headers, main_model, fallback_model, cancel_event
    )

    assert audio_sink_instance is not None
    sink = CompositeSink([popup_sink, audio_sink_instance], cancel_event)

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


def _execute_capture_pipeline(
    config, active_profile, active_prompt_text, status_update
):
    """Execute capture pipeline."""
    global \
        ocr_engine_instance, \
        llm_engine_instance, \
        fallback_llm_engine_instance, \
        audio_sink_instance

    active_src = get_active_source_instance()

    _ensure_ocr_engine(active_profile)
    if hasattr(active_src, "ocr_engine"):
        active_src.ocr_engine = ocr_engine_instance

    main_model = active_profile.get("model", DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    sink, popup_sink, show_headers = _setup_capture_sinks(
        config, active_profile, main_model, fallback_model
    )

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

    _process_capture_result(
        result, show_headers, popup_sink, fallback_model, main_model, config
    )


def handle_capture(config, active_profile, active_prompt_text):
    global is_processing
    if is_processing:
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
    global is_multi_capturing, multi_capture_texts
    if not is_multi_capturing:
        is_multi_capturing = True
        multi_capture_texts = []
        update_multi_state(True)


def _perform_multi_capture_ocr(active_profile, coords, status_update):
    """Perform multi-capture OCR."""
    _ensure_ocr_engine(active_profile, status_callback=status_update)

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

    return extracted_text


def _handle_multi_capture_ocr(active_profile, coords, config):
    """Handle OCR during multi-capture."""

    def status_update(msg):
        _show_status_popup(config, msg)

    status_update("Capturing screen...")

    extracted_text = _perform_multi_capture_ocr(active_profile, coords, status_update)

    if cancel_event.is_set():
        print("Multi-capture OCR was cancelled.")
        return None

    if extracted_text:
        multi_capture_texts.append(extracted_text)
        status_update(
            f"Captured {len(multi_capture_texts)} images... Multiple capture mode"
        )
    else:
        status_update(
            f"No text found. Captured {len(multi_capture_texts)} images... Multiple capture mode"
        )

    return extracted_text


def _multi_capture_loop(config, active_profile):
    """Main loop for multi-capture process."""
    coords = get_coordinates()
    if not coords or cancel_event.is_set():
        print("Multi-capture: Selection cancelled.")
        if is_multi_capturing:
            handle_cancel()
        return

    _handle_multi_capture_ocr(active_profile, coords, config)


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
        global is_multi_capturing, multi_capture_texts
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
    global is_processing, is_multi_capturing, multi_capture_texts
    if is_processing:
        return

    if not is_multi_capturing:
        return

    active_source = get_active_source_instance()
    if active_source and active_source.name != "image":
        return

    set_processing(True)

    update_multi_state(False)

    def _end_multi_capture():
        global is_multi_capturing, multi_capture_texts
        try:
            if not _check_multi_capture_texts(config, multi_capture_texts):
                is_multi_capturing = False
                update_multi_state(False)
                return

            combined_text = "\n\n".join(multi_capture_texts)
            print(f"Combined Text:\n{combined_text}")

            status_update = _make_status_callback(config)

            _execute_text_pipeline(
                config,
                active_profile,
                active_prompt_text,
                status_update,
                text=combined_text,
            )

        except Exception as multi_error:
            print(f"Error during processing multi-capture: {multi_error}")
            _show_status_popup(config, f"Error: {multi_error}", auto_close=5000)
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
            close_popup()
        _show_status_popup(
            config, f"New Chat Session Started\nID: {session_id}", auto_close=3000
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
    _show_status_popup(config, f"Chat Stitching {state_str}", auto_close=3000)


def handle_toggle_panel():
    # Toggle control panel state internally
    toggle_control_panel()


def handle_toggle_all_widgets():
    """Hide or unhide all overlay widgets at once."""
    toggle_all_widgets()


def handle_open_url():
    """Open the URL input popup."""
    from core.output import ui_signals

    ui_signals.show_url_input.emit()


def handle_open_session_browser():
    """Open the session browser dialog."""
    from core.output import ui_signals

    ui_signals.open_session_browser.emit()


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
                    "opacity": config.get("opacity", 0.8),
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
                    "opacity": config.get("opacity", 0.8),
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
        _ensure_ocr_engine(active_profile)
        new_source.ocr_engine = ocr_engine_instance
    elif isinstance(active_source, ScreenshotSource):
        global session_manager
        new_source = SoundSource(config, session_manager=session_manager)
    else:
        new_source = TextSource()

    set_active_source_instance(new_source)
    set_active_source_ui(new_source.name, opacity=config.get("opacity", 0.8))
    print(f"Source cycled to: {new_source.name}")
    _show_status_popup(
        config, f"Source changed to: {new_source.name.capitalize()}", auto_close=2000
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

    def _cleanup():
        """Best-effort cleanup on a background thread."""
        try:
            stop_remote_control_server()
        except Exception as e:
            print(f"Error stopping remote control server: {e}")

        if session_manager:
            try:
                session_manager.cleanup()
            except Exception as e:
                print(f"Error cleaning up session manager: {e}")

    # Run cleanup on a daemon thread so it cannot block the exit.
    cleanup_thread = threading.Thread(target=_cleanup, daemon=True)
    cleanup_thread.start()
    cleanup_thread.join(timeout=2)

    # Force-terminate immediately.  We intentionally skip app.quit() and
    # keyboard.unhook_all() because:
    #  - exit_app() may be called from the keyboard hook thread (via the quit
    #    hotkey), and keyboard.unhook_all() deadlocks in that context.
    #  - app.quit() can block when called from a non-main thread.
    # os._exit() terminates the process at the OS level, making both calls
    # unnecessary.
    os._exit(0)


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


def _check_model_ocr_support(models, model_id):
    """Check if model supports OCR."""
    for m in models:
        if m.get("id") == model_id:
            return m.get("supports_ocr", False)
    return False


def _validate_main_model(active_profile, models_data):
    """Validate main model configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    model_id = active_profile.get("model", DEFAULT_MODEL_NAME)
    ocr_type = active_profile.get("ocr_engine", "none")

    models = models_data.get(llm_type, [])
    supports_ocr = _check_model_ocr_support(models, model_id)

    if not supports_ocr and ocr_type == "none":
        print(
            f"Error: Selected model '{model_id}' does not support built-in OCR and no OCR engine is configured."
        )
        print("Please configure an OCR engine or select a model that supports OCR.")
        sys.exit(1)


def _validate_fallback_model(active_profile, models_data):
    """Validate fallback model configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    fallback_model_id = active_profile.get("fallback_model", "None")
    ocr_type = active_profile.get("ocr_engine", "none")

    if not fallback_model_id or fallback_model_id == "None":
        return

    models = models_data.get(llm_type, [])
    fallback_supports_ocr = _check_model_ocr_support(models, fallback_model_id)

    if not fallback_supports_ocr and ocr_type == "none":
        print(
            f"Error: Selected fallback model '{fallback_model_id}' does not support built-in OCR and no OCR engine is configured."
        )
        print(
            "Please configure an OCR engine or select a fallback model that supports OCR."
        )
        sys.exit(1)


def validate_config(active_profile):
    models_data = load_models_data()

    _validate_main_model(active_profile, models_data)
    _validate_fallback_model(active_profile, models_data)


def _read_process_output(process, output_type="stdout"):
    """Read process output in real time."""
    if output_type == "stdout":
        for line in iter(process.stdout.readline, ""):
            print(f"[WhisperLive Warmup] {line.strip()}")
        process.stdout.close()
    else:
        for line in iter(process.stderr.readline, ""):
            print(
                f"[WhisperLive Warmup ERR] {line.strip()}",
                file=sys.stderr,
            )
        process.stderr.close()


def _run_warmup_process(script_path):
    """Run the warmup process and handle its output."""
    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
        )

        # Read stdout and stderr in background threads
        t1 = threading.Thread(
            target=_read_process_output, args=(process, "stdout"), daemon=True
        )
        t2 = threading.Thread(
            target=_read_process_output, args=(process, "stderr"), daemon=True
        )
        t1.start()
        t2.start()

        process.wait()
        t1.join()
        t2.join()

        if process.returncode == 0:
            print("Real-time transcription warmup completed successfully.")
        else:
            print(
                f"Real-time transcription warmup failed with code {process.returncode}"
            )
    except Exception as warmup_error:
        print(f"Error executing warmup script: {warmup_error}")


def warmup_whisperlive_process(_config):
    """Executes the test_whisperlive_warmup script from main thread as a warmup."""
    try:
        # Get path to test_whisperlive_warmup.py
        script_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "tests",
            "sanity",
            "test_whisperlive_warmup.py",
        )
        if os.path.exists(script_path):
            print(
                "Running Real-time transcription warmup (test_whisperlive_warmup.py)..."
            )
            threading.Thread(
                target=_run_warmup_process, args=(script_path,), daemon=True
            ).start()
        else:
            print("Warning: Real-time transcription warmup script not found.")
    except Exception as init_error:
        print(f"Error initializing Real-time transcription warmup: {init_error}")


def _initialize_qt_app():
    """Initialize PyQt application."""
    app = QApplication.instance()
    if not app:
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
    return app


def _load_config_and_profiles():
    """Load configuration and profiles."""
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

    return config, active_profile, active_prompt_text


def _initialize_session_manager(config):
    """Initialize session manager."""
    manager = SessionManager(config)
    return manager


def _setup_active_source(config, manager):
    """Set up the active source based on configuration."""
    default_source = config.get("default_source", "text")
    if default_source == "image":
        set_active_source_instance(ScreenshotSource())
    elif default_source == "audio":
        set_active_source_instance(SoundSource(config, session_manager=manager))
    else:
        set_active_source_instance(TextSource())
    return get_active_source_instance()


def _setup_ui_callbacks(config, active_profile, active_prompt_text):
    """Set up UI callbacks."""
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
    return callbacks


def _initialize_ui(config, active_source, callbacks):
    """Initialize UI manager and set callbacks."""
    from core.output import init_ui_manager

    init_ui_manager()
    set_hide_from_capture(config.get("hide_from_capture", False))
    set_app_callbacks(callbacks)

    set_active_source_ui(
        active_source.name if active_source else "text",
        opacity=config.get("opacity", 0.8),
    )

    if config.get("show_control_panel", False):
        toggle_control_panel(True)


def _handle_coordinates_setup(config, active_source):
    """Handle coordinates setup if needed."""
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


def _initialize_ocr_engine(active_profile, config):
    """Initialize OCR engine based on profile configuration."""
    ocr_type = active_profile.get("ocr_engine", "none")
    if ocr_type == "paddleocr":
        ocr_engine = LocalPaddleOCREngine(
            status_callback=lambda msg: print(f"Init status: {msg}")
        )
    elif ocr_type == "remote_paddle":
        ocr_config = config.get("ocr_config", {})
        ocr_engine = RemotePaddleOCREngine(
            config=ocr_config, status_callback=lambda msg: print(f"Init status: {msg}")
        )
    else:
        ocr_engine = NoOCREngine()

    if config.get("warmup_ocr", True) and hasattr(ocr_engine, "warmup"):
        ocr_engine.warmup()

    return ocr_engine


def _initialize_llm_engines(active_profile, config, manager):
    """Initialize LLM engines based on profile configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    model = active_profile.get("model", DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    # noinspection PyUnusedLocal
    llm_engine = None
    fallback_llm_engine = None

    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine = OllamaEngine(
            model,
            config.get("ollama_url", "http://localhost:11434"),
            session_manager=manager,
        )
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine = OllamaEngine(
                fallback_model,
                config.get("ollama_url", "http://localhost:11434"),
                session_manager=manager,
            )
    elif llm_type == "google-genai":
        llm_engine = GoogleGenAIEngine(
            model,
            config.get("google_genai_api_key", ""),
            session_manager=manager,
        )
        if fallback_model and fallback_model != "None":
            fallback_llm_engine = GoogleGenAIEngine(
                fallback_model,
                config.get("google_genai_api_key", ""),
                session_manager=manager,
            )
    else:
        llm_engine = GeminiCLIEngine(model, session_manager=manager)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine = GeminiCLIEngine(
                fallback_model, session_manager=manager
            )

    # Use variables to avoid "unused" warnings
    _ = llm_engine, fallback_llm_engine
    return llm_engine, fallback_llm_engine


def _perform_llm_warmup(config, llm_engine, fallback_llm_engine):
    """Perform LLM warmup."""

    def warmup_status_cb(msg):
        print(f"Init status: {msg}")

    warmup_success = False
    if config.get("warmup_llm", True):
        if fallback_llm_engine and "fallback_llm_engine_instance" in globals():
            warmup_success = fallback_llm_engine.warmup(
                status_callback=warmup_status_cb
            )

        if not warmup_success and llm_engine:
            llm_engine.warmup(status_callback=warmup_status_cb)


def _initialize_audio_components(config, manager, cancel):
    """Initialize audio components."""
    audio_sink = AudioSink(config, cancel)

    if config.get("warmup_tts", False) and hasattr(audio_sink, "warmup"):
        threading.Thread(target=audio_sink.warmup, daemon=True).start()

    if config.get("warmup_speech_recognition", True):
        temp_sr = SoundSource(config, session_manager=manager)
        threading.Thread(target=temp_sr.warmup, daemon=True).start()

    if config.get("warmup_realtime_transcription", False):
        warmup_whisperlive_process(config)

    return audio_sink


def _register_test_hotkeys(config, active_profile):
    """Register test hotkeys for transcription testing."""

    def handle_test_transcription():
        import secrets
        from core.output import show_subtitle

        test_text = (
            f"Transcription test with random number: {secrets.randbelow(1000) + 1}"
        )
        print(f"Testing transcription display: {test_text}")
        show_subtitle(test_text)

    def handle_select_subtitle(index):
        text = get_subtitle_text(index)
        if text:
            print(f"Selected subtitle {index}: {text}")
            handle_text_submit(config, active_profile, text)
        else:
            print(f"No subtitle found at index {index}")

    keyboard.add_hotkey("ctrl+alt+shift+t", handle_test_transcription)

    for i in range(1, 6):
        keyboard.add_hotkey(f"ctrl+alt+shift+{i}", handle_select_subtitle, args=(i,))


def _register_config_hotkeys(config, active_profile, active_prompt_text):
    """Register hotkeys from configuration."""
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
        elif action == "toggle_all_widgets":
            keyboard.add_hotkey(key, handle_toggle_all_widgets)
        elif action == "open_url":
            keyboard.add_hotkey(key, handle_open_url)
        elif action == "open_session_browser":
            keyboard.add_hotkey(key, handle_open_session_browser)
        elif action == "quit_app":
            keyboard.add_hotkey(key, exit_app)


def _register_keyboard_shortcuts(config, active_profile, active_prompt_text):
    """Register keyboard shortcuts."""
    _register_test_hotkeys(config, active_profile)
    _register_config_hotkeys(config, active_profile, active_prompt_text)


def _setup_tray_or_console_mode(config, exit_handler):
    """Setup tray or console mode."""
    if config.get("background", False):
        print("Running in background tray mode with pystray...")

        def run_tray():
            icon = create_tray_icon(exit_handler)
            icon.run()

        threading.Thread(target=run_tray, daemon=True).start()
    else:
        print("Running in console/Qt mode. Press Ctrl+C or close via tray to exit.")
        # On Windows, the SetConsoleCtrlHandler registered at module load
        # handles SIGINT/console-close.  On other platforms, fall back to
        # Python signal handlers with a QTimer to ensure delivery.
        if platform.system() != "Windows":
            def _signal_exit(_sig, _frame):
                print("Exiting (signal)...")
                os._exit(0)

            signal.signal(signal.SIGINT, _signal_exit)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, _signal_exit)

            from PyQt6.QtCore import QTimer

            timer = QTimer()
            timer.start(500)
            timer.timeout.connect(lambda: None)


def main():
    # Configure logging early
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    global is_running

    print("Initializing Screen Capture & Gemini QA App...")

    app = _initialize_qt_app()

    config, active_profile, active_prompt_text = _load_config_and_profiles()

    validate_config(active_profile)

    global session_manager
    session_manager = _initialize_session_manager(config)

    active_source = _setup_active_source(config, session_manager)

    callbacks = _setup_ui_callbacks(config, active_profile, active_prompt_text)

    _initialize_ui(config, active_source, callbacks)

    _handle_coordinates_setup(config, active_source)

    print("Checking engine pre-initialization...")

    global ocr_engine_instance
    ocr_engine_instance = _initialize_ocr_engine(active_profile, config)

    if isinstance(active_source, ScreenshotSource):
        active_source.ocr_engine = ocr_engine_instance
        set_active_source_instance(active_source)

    global llm_engine_instance, fallback_llm_engine_instance
    llm_engine_instance, fallback_llm_engine_instance = _initialize_llm_engines(
        active_profile, config, session_manager
    )

    _perform_llm_warmup(config, llm_engine_instance, fallback_llm_engine_instance)

    global audio_sink_instance
    audio_sink_instance = _initialize_audio_components(
        config, session_manager, cancel_event
    )

    # Start remote control server if enabled
    if config.get("enable_remote_control", False):
        remote_host = config.get("remote_control_host", "0.0.0.0")
        remote_port = config.get("remote_control_port", 8080)
        try:
            start_remote_control_server(remote_host, remote_port, config)
        except Exception as remote_error:
            print(f"Failed to start remote control server: {remote_error}")

    _register_keyboard_shortcuts(config, active_profile, active_prompt_text)

    _setup_tray_or_console_mode(config, exit_app)

    print("Initialization done.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
