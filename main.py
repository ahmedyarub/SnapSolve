import platform
import sys
import threading
import time

import keyboard
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from config.settings import get_config, save_config, load_profiles, load_prompts
from core.output import output_result, show_popup, toggle_control_panel, set_app_callbacks, update_multi_state, set_active_source_ui, set_app_processing_state
from core.pipeline import process_pipeline
from core.sinks import PopupSink
from core.sources.ocr import PaddleOCREngine, NoOCREngine
from core.llm import OllamaEngine, GeminiCLIEngine, GoogleGenAIEngine
from core.session_manager import SessionManager
from core.sources import ScreenshotSource, TextSource
from ui.selector import get_coordinates

try:
    from PIL import Image
    import pystray

    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Global state
is_running = True
is_processing = False
ocr_engine_instance = None
llm_engine_instance = None
session_manager = None
active_source_instance = None

# Multi-capture state
is_multi_capturing = False
multi_capture_texts = []

# Enable Windows DPI awareness to fix coordinate scaling issues
if platform.system() == "Windows":
    import ctypes

    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")


def create_tray_icon(on_exit, config):
    # Create a simple tray icon
    img = Image.new('RGB', (64, 64), color=(73, 109, 137))

    def quit_action(icon, item):
        icon.stop()
        on_exit()

    def toggle_panel_action(icon, item):
        toggle_control_panel()

    menu = pystray.Menu(
        pystray.MenuItem('Toggle Panel', toggle_panel_action),
        pystray.MenuItem('Exit', quit_action)
    )
    icon = pystray.Icon("ScreenQA", img, "Screen Capture QA", menu)
    return icon


def set_processing(state):
    global is_processing
    is_processing = state
    set_app_processing_state(state)

def handle_text_submit(config, active_profile, active_prompt_text, text):
    global is_processing
    if is_processing:
        return

    set_processing(True)
    print(f"Processing text input: {text}")

    def status_update(msg):
        if 'popup' in config.get('output_mode', ['popup']):
            show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

    def _process():
        try:
            global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance
            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)
            from core.sources import TextSource
            temp_source = TextSource()

            result = process_pipeline(
                source=temp_source,
                llm=llm_engine_instance,
                prompt_text=text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                text=text
            )
            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if sink.accumulated_fallback and len(sink.accumulated_result) == 1:
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(final_result, config.get('output_mode'), config.get('voice_id'),
                          auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8),
                          fallback_language=config.get('fallback_language', 'python'))
        except Exception as e:
            print(f"Error during processing text input: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)

    threading.Thread(target=_process, daemon=True).start()

def handle_capture(config, active_profile, active_prompt_text):
    global is_processing, active_source_instance
    if is_processing:
        return

    if active_source_instance and active_source_instance.name != "image":
        print(f"Capture is disabled for {active_source_instance.name} source.")
        return

    set_processing(True)
    print("Capturing and processing...")

    def status_update(msg):
        if 'popup' in config.get('output_mode', ['popup']):
            show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

    def _capture():
        try:
            global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, active_source_instance
            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)

            result = process_pipeline(
                source=active_source_instance,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                coords=config.get('coordinates')
            )
            if hasattr(active_source_instance, 'cleanup_all'):
                active_source_instance.cleanup_all()
            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if sink.accumulated_fallback and len(sink.accumulated_result) == 1:
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(final_result, config.get('output_mode'), config.get('voice_id'),
                          auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8),
                          fallback_language=config.get('fallback_language', 'python'))
        except Exception as e:
            print(f"Error during processing: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)

    # Must run in a separate thread so we don't block the global keyboard hook
    threading.Thread(target=_capture, daemon=True).start()


def handle_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts, active_source_instance
    if is_processing:
        return

    if active_source_instance and active_source_instance.name != "image":
        print(f"Multi-capture is disabled for {active_source_instance.name} source.")
        return

    set_processing(True)

    def _multi_capture():
        global is_multi_capturing, multi_capture_texts, ocr_engine_instance
        try:
            ocr_type = active_profile.get('ocr_engine', 'none')
            if ocr_type == 'none':
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup("Error: Multi-capture requires an OCR engine to be defined in the active profile.", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
                return

            if not is_multi_capturing:
                is_multi_capturing = True
                multi_capture_texts = []
                update_multi_state(True)

            if 'popup' in config.get('output_mode', ['popup']):
                show_popup("Multiple capture mode", auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

            # Get coordinates specifically for this capture (don't update config)
            coords = get_coordinates()
            if not coords:
                print("Multi-capture: Selection cancelled.")
                return

            def status_update(msg):
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

            # Extract text via capture_and_process but tell it to just extract and stop, or do it manually here.
            # Let's do it manually since we just need OCR.
            import tempfile
            from PIL import ImageGrab
            import os
            from core.sources import ScreenshotSource

            status_update("Capturing screen...")

            ocr = ocr_engine_instance
            if not ocr:
                from core.sources.ocr import PaddleOCREngine, NoOCREngine
                if ocr_type == "paddleocr":
                    ocr = PaddleOCREngine()
                else:
                    ocr = NoOCREngine()

            temp_source = ScreenshotSource()
            temp_source.ocr_engine = ocr
            extracted_text = None
            try:
                extracted_text = temp_source.get_text(coords=coords, status_callback=status_update)
            except Exception as e:
                status_update(f"Error during OCR: {str(e)}")
            finally:
                temp_source.cleanup_all()

            if extracted_text:
                multi_capture_texts.append(extracted_text)
                status_update(f"Captured {len(multi_capture_texts)} images... Multiple capture mode")
            else:
                status_update(f"No text found. Captured {len(multi_capture_texts)} images... Multiple capture mode")

        except Exception as e:
            print(f"Error during multi-capture: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
        finally:
            set_processing(False)

    threading.Thread(target=_multi_capture, daemon=True).start()


def handle_end_multi_capture(config, active_profile, active_prompt_text):
    global is_processing, is_multi_capturing, multi_capture_texts, active_source_instance
    if is_processing:
        return

    if not is_multi_capturing:
        return

    if active_source_instance and active_source_instance.name != "image":
        return

    set_processing(True)

    # Immediately update UI state to hide buttons before processing starts
    update_multi_state(False)

    def _end_multi_capture():
        global is_processing, is_multi_capturing, multi_capture_texts, llm_engine_instance, fallback_llm_engine_instance
        try:
            if not multi_capture_texts:
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup("No text captured in multi-capture mode.", auto_close=3000, opacity=config.get('popup_opacity', 0.8), is_result=False)
                is_multi_capturing = False
                update_multi_state(False)
                return

            combined_text = "\n\n".join(multi_capture_texts)
            print(f"Combined Text:\n{combined_text}")

            def status_update(msg):
                if 'popup' in config.get('output_mode', ['popup']):
                    show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

            show_headers = False
            fallback_model = active_profile.get('fallback_model', 'None')
            main_model = active_profile.get('model', 'gemini-2.5-flash-lite')
            prompt_id = active_profile.get('prompt_id', 'default')

            if fallback_model and fallback_model != "None" and prompt_id != "quick":
                show_headers = True

            sink = PopupSink(config, show_headers, main_model, fallback_model)
            from core.sources import TextSource
            temp_source = TextSource()

            result = process_pipeline(
                source=temp_source,
                llm=llm_engine_instance,
                prompt_text=active_prompt_text,
                status_callback=status_update,
                session_manager=session_manager,
                enable_stitching=active_profile.get('enable_stitching', True),
                sink=sink,
                fallback_llm=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None,
                text=combined_text
            )
            print(f"Result: {result}")

            final_result = result
            if show_headers:
                if sink.accumulated_fallback and len(sink.accumulated_result) == 1:
                    final_result = f"## Fallback Model ({fallback_model})\n\n{result}"
                else:
                    final_result = f"## Main Model ({main_model})\n\n{result}"

            output_result(final_result, config.get('output_mode'), config.get('voice_id'),
                          auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8),
                          fallback_language=config.get('fallback_language', 'python'))

        except Exception as e:
            print(f"Error during processing multi-capture: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)
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
        if 'popup' in config.get('output_mode', ['popup']):
            # Find and destroy any open result popups first
            from ui.popups import active_popups
            for popup in list(active_popups):
                try:
                    popup.destroy()
                    active_popups.remove(popup)
                except Exception:
                    pass

            # Then show the new status popup
            show_popup(f"New Chat Session Started\nID: {session_id}", auto_close=3000, opacity=config.get('popup_opacity', 0.8), is_result=False)

def handle_toggle_stitching(config, active_profile):
    current = active_profile.get('enable_stitching', True)
    active_profile['enable_stitching'] = not current

    # Save the profiles
    profiles = load_profiles()
    for p in profiles:
        if p['id'] == active_profile['id']:
            p['enable_stitching'] = not current
            break

    from config.settings import save_profiles
    save_profiles(profiles)

    state_str = "Enabled" if not current else "Disabled"
    if 'popup' in config.get('output_mode', ['popup']):
        show_popup(f"Chat Stitching {state_str}", auto_close=3000, opacity=config.get('popup_opacity', 0.8), is_result=False)

def handle_toggle_panel(config):
    # Toggle control panel state internally
    toggle_control_panel()


def handle_cancel_multi_capture(config):
    global is_processing, is_multi_capturing, multi_capture_texts
    if is_multi_capturing:
        is_multi_capturing = False
        multi_capture_texts = []
        update_multi_state(False)
        print("Multi-capture canceled.")
        if 'popup' in config.get('output_mode', ['popup']):
            show_popup("Multi-capture canceled", auto_close=3000, opacity=config.get('popup_opacity', 0.8), is_result=False)


def handle_cycle_source(config):
    global active_source_instance, ocr_engine_instance
    from core.sources import ScreenshotSource, TextSource
    if isinstance(active_source_instance, ScreenshotSource):
        active_source_instance = TextSource()
    else:
        active_source_instance = ScreenshotSource()
        active_source_instance.ocr_engine = ocr_engine_instance

    set_active_source_ui(active_source_instance.name, opacity=config.get('popup_opacity', 0.8))
    print(f"Source cycled to: {active_source_instance.name}")
    if 'popup' in config.get('output_mode', ['popup']):
        show_popup(f"Source changed to: {active_source_instance.name.capitalize()}", auto_close=2000, opacity=config.get('popup_opacity', 0.8), is_result=False)

def handle_reselect(config):
    global is_processing, active_source_instance
    if is_processing:
        return

    if active_source_instance and active_source_instance.name != "image":
        print(f"Reselect is disabled for {active_source_instance.name} source.")
        return

    set_processing(True)
    print("Reselecting coordinates...")

    try:
        # Run in a separate thread so it doesn't block keyboard hooks
        def _reselect():
            coords = get_coordinates()
            if coords:
                config['coordinates'] = coords
                save_config(config)
                print(f"New coordinates saved: {coords}")
            else:
                print("Reselection cancelled.")

            set_processing(False)

        threading.Thread(target=_reselect, daemon=True).start()
        return
    except Exception as e:
        print(f"Error during reselection: {e}")
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

import json
import os


def load_models_data():
    try:
        models_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "llm_models.json")
        with open(models_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load llm_models.json: {e}")
        return {}


def validate_config(active_profile):
    llm_type = active_profile.get('llm_engine', 'gemini')
    model_id = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model_id = active_profile.get('fallback_model', 'None')
    ocr_type = active_profile.get('ocr_engine', 'none')

    models_data = load_models_data()
    models = models_data.get(llm_type, [])

    supports_ocr = False
    for m in models:
        if m.get('id') == model_id:
            supports_ocr = m.get('supports_ocr', False)
            break

    if not supports_ocr and ocr_type == 'none':
        print(f"Error: Selected model '{model_id}' does not support built-in OCR and no OCR engine is configured.")
        print("Please configure an OCR engine or select a model that supports OCR.")
        sys.exit(1)

    if fallback_model_id and fallback_model_id != "None":
        fallback_supports_ocr = False
        for m in models:
            if m.get('id') == fallback_model_id:
                fallback_supports_ocr = m.get('supports_ocr', False)
                break

        if not fallback_supports_ocr and ocr_type == 'none':
            print(
                f"Error: Selected fallback model '{fallback_model_id}' does not support built-in OCR and no OCR engine is configured.")
            print("Please configure an OCR engine or select a fallback model that supports OCR.")
            sys.exit(1)


def main():
    global is_running, active_source_instance

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

    active_profile_id = config.get('active_profile_id', 'prof1')
    active_profile = next((p for p in profiles if p.get('id') == active_profile_id), profiles[0] if profiles else {})

    prompt_id = active_profile.get('prompt_id', 'default')
    active_prompt = next((p for p in prompts if p.get('id') == prompt_id), prompts[0] if prompts else {})
    active_prompt_text = active_prompt.get('text', 'answer the following question quickly and briefly')

    validate_config(active_profile)

    # Determine the initial source
    default_source = config.get('default_source', 'text')
    if default_source == 'image':
        active_source_instance = ScreenshotSource()
    else:
        active_source_instance = TextSource()

    # Set up UI callbacks before starting the main loop
    callbacks = {
        'capture': lambda: handle_capture(config, active_profile, active_prompt_text),
        'reselect': lambda: handle_reselect(config),
        'multi_capture': lambda: handle_multi_capture(config, active_profile, active_prompt_text),
        'end_multi_capture': lambda: handle_end_multi_capture(config, active_profile, active_prompt_text),
        'cancel_multi_capture': lambda: handle_cancel_multi_capture(config),
        'toggle_stitching': lambda: handle_toggle_stitching(config, active_profile),
        'cycle_source': lambda: handle_cycle_source(config),
        'text_submit': lambda text: handle_text_submit(config, active_profile, active_prompt_text, text)
    }
        # Initialize the UI Manager and set callbacks
    from core.output import init_ui_manager
    init_ui_manager()
    set_app_callbacks(callbacks)

    # Initialize the UI with the active source before showing the panel
    set_active_source_ui(active_source_instance.name, opacity=config.get('popup_opacity', 0.8))

    if config.get('show_control_panel', False):
        toggle_control_panel(True)

    if config.get('qa_testing', False):
        from ui.qa_panel import QAPanelWidget
        # We need to keep a reference to it so it doesn't get garbage collected
        global qa_panel_instance
        qa_panel_instance = QAPanelWidget(callbacks)
        qa_panel_instance.show()

    if active_source_instance.name == "image" and not config.get('coordinates'):
        print("Coordinates not found in config. Launching coordinate selector...")
        coords = get_coordinates()
        if coords:
            config['coordinates'] = coords
            save_config(config)
            print(f"Coordinates saved: {coords}")
        else:
            print("No coordinates selected. Exiting.")
            sys.exit(1)

    # Initialize Engines
    print("Checking engine pre-initialization...")
    global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance, session_manager
    session_manager = SessionManager(config)
    ocr_type = active_profile.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))
    else:
        ocr_engine_instance = NoOCREngine()

    if isinstance(active_source_instance, ScreenshotSource):
        active_source_instance.ocr_engine = ocr_engine_instance

    llm_type = active_profile.get('llm_engine', 'gemini')
    model = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model = active_profile.get('fallback_model', 'None')

    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'), session_manager=session_manager)
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine_instance = OllamaEngine(fallback_model, config.get('ollama_url', 'http://localhost:11434'), session_manager=session_manager)
    elif llm_type == "google-genai":
        llm_engine_instance = GoogleGenAIEngine(model, config.get('google_genai_api_key', ''), session_manager=session_manager)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GoogleGenAIEngine(fallback_model, config.get('google_genai_api_key', ''), session_manager=session_manager)
    else:
        llm_engine_instance = GeminiCLIEngine(model, session_manager=session_manager)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine_instance = GeminiCLIEngine(fallback_model, session_manager=session_manager)

    # Perform Warmup: fallback first, then main if fallback fails or doesn't exist
    warmup_status_cb = lambda msg: print(f"Init status: {msg}")
    warmup_success = False
    if fallback_model and fallback_model != "None" and 'fallback_llm_engine_instance' in globals():
        warmup_success = fallback_llm_engine_instance.warmup(status_callback=warmup_status_cb)

    if not warmup_success and llm_engine_instance:
        llm_engine_instance.warmup(status_callback=warmup_status_cb)

    llm_type = active_profile.get('llm_engine', 'gemini')
    model = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model = active_profile.get('fallback_model', 'None')
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'),
                                           status_callback=lambda msg: print(f"Init status: {msg}"))
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine...")
            fallback_llm_engine_instance = OllamaEngine(fallback_model,
                                                        config.get('ollama_url', 'http://localhost:11434'),
                                                        status_callback=lambda msg: print(f"Init status: {msg}"))

    hotkeys = config.get('hotkeys', [])

    for hk in hotkeys:
        action = hk.get('action')
        key = hk.get('key')
        if not action or not key:
            continue

        print(f"Listening for '{action}' hotkey: {key}")

        if action == 'capture':
            keyboard.add_hotkey(key, handle_capture, args=[config, active_profile, active_prompt_text])
        elif action == 'reselect':
            keyboard.add_hotkey(key, handle_reselect, args=[config])
        elif action == 'multi_capture':
            keyboard.add_hotkey(key, handle_multi_capture, args=[config, active_profile, active_prompt_text])
        elif action == 'end_multi_capture':
            keyboard.add_hotkey(key, handle_end_multi_capture, args=[config, active_profile, active_prompt_text])
        elif action == 'cancel_multi_capture':
            keyboard.add_hotkey(key, handle_cancel_multi_capture, args=[config])
        elif action == 'toggle_panel':
            keyboard.add_hotkey(key, handle_toggle_panel, args=[config])
        elif action == 'new_chat_session':
            keyboard.add_hotkey(key, handle_new_chat_session, args=[config])
        elif action == 'toggle_stitching':
            keyboard.add_hotkey(key, handle_toggle_stitching, args=[config, active_profile])
        elif action == 'cycle_source':
            keyboard.add_hotkey(key, handle_cycle_source, args=[config])

    if config.get('background', False) and HAS_PYSTRAY:
        print("Running in background tray mode with pystray...")
        import threading
        def run_tray():
            icon = create_tray_icon(exit_app, config)
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

    sys.exit(app.exec())

    # Cleanup
    keyboard.unhook_all()
    print("Goodbye!")


if __name__ == '__main__':
    main()
