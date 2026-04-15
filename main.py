import platform
import sys
import threading
import time

import keyboard

from config.settings import get_config, save_config, load_profiles, load_prompts
from core.output import output_result, show_popup
from core.processor import capture_and_process, PaddleOCREngine, OllamaEngine
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

# Enable Windows DPI awareness to fix coordinate scaling issues
if platform.system() == "Windows":
    import ctypes

    try:
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as e:
        print(f"Warning: Failed to set DPI awareness: {e}")


def create_tray_icon(on_exit):
    # Create a simple tray icon
    img = Image.new('RGB', (64, 64), color=(73, 109, 137))

    def quit_action(icon, item):
        icon.stop()
        on_exit()

    menu = pystray.Menu(pystray.MenuItem('Exit', quit_action))
    icon = pystray.Icon("ScreenQA", img, "Screen Capture QA", menu)
    return icon


def handle_capture(config, active_profile, active_prompt_text):
    global is_processing
    if is_processing:
        return

    is_processing = True
    print("Capturing and processing...")

    def status_update(msg):
        if 'popup' in config.get('output_mode', ['popup']):
            show_popup(msg, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=False)

    def _capture():
        global is_processing
        try:
            global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance
            accumulated_result = []
            accumulated_fallback = []

            def chunk_callback(chunk_text, is_main=True, replace=False):
                if 'popup' in config.get('output_mode', ['popup']):
                    if replace:
                        accumulated_fallback.clear()
                        accumulated_result.clear()

                    if is_main:
                        accumulated_result.append(chunk_text)
                        current_text = "".join(accumulated_result)
                    else:
                        accumulated_fallback.append(chunk_text)
                        current_text = "".join(accumulated_fallback)

                    # Use is_result=True so it expands to a big readable box with scroll,
                    # and auto_close=None so it doesn't auto-close while streaming.
                    show_popup(current_text, auto_close=None, opacity=config.get('popup_opacity', 0.8), is_result=True, fallback_language=config.get('fallback_language', 'python'))

            result = capture_and_process(
                config.get('coordinates'),
                prompt_text=active_prompt_text,
                model=active_profile.get('model', 'gemini-2.5-flash-lite'),
                llm_engine=active_profile.get('llm_engine', 'gemini'),
                ocr_engine=active_profile.get('ocr_engine', 'none'),
                ollama_url=config.get('ollama_url', 'http://localhost:11434'),
                google_genai_api_key=config.get('google_genai_api_key', ''),
                ocr_engine_instance=ocr_engine_instance,
                llm_engine_instance=llm_engine_instance,
                status_callback=status_update,
                chunk_callback=chunk_callback,
                fallback_model=active_profile.get('fallback_model', 'None'),
                fallback_llm_engine_instance=fallback_llm_engine_instance if 'fallback_llm_engine_instance' in globals() else None
            )
            print(f"Result: {result}")
            # The final call will trigger output_result to handle auto_close, TTS, etc.
            # output_result does show_popup again with final text and configured auto-close.
            output_result(result, config.get('output_mode'), config.get('voice_id'), auto_close=config.get('auto_close_results', False), opacity=config.get('popup_opacity', 0.8), fallback_language=config.get('fallback_language', 'python'))
        except Exception as e:
            print(f"Error during processing: {e}")
            if 'popup' in config.get('output_mode', ['popup']):
                show_popup(f"Error: {e}", auto_close=5000, opacity=config.get('popup_opacity', 0.8), is_result=False)

        is_processing = False

    # Must run in a separate thread so we don't block the global keyboard hook
    threading.Thread(target=_capture, daemon=True).start()


def handle_reselect(config):
    global is_processing
    if is_processing:
        return

    is_processing = True
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

            global is_processing
            is_processing = False

        threading.Thread(target=_reselect, daemon=True).start()
        return
    except Exception as e:
        print(f"Error during reselection: {e}")
        is_processing = False


def exit_app():
    global is_running
    is_running = False
    print("Exiting...")


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
            print(f"Error: Selected fallback model '{fallback_model_id}' does not support built-in OCR and no OCR engine is configured.")
            print("Please configure an OCR engine or select a fallback model that supports OCR.")
            sys.exit(1)

def main():
    global is_running

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

    if not config.get('coordinates'):
        print("Coordinates not found in config. Launching coordinate selector...")
        coords = get_coordinates()
        if coords:
            config['coordinates'] = coords
            save_config(config)
            print(f"Coordinates saved: {coords}")
        else:
            print("No coordinates selected. Exiting.")
            sys.exit(1)

    # Initialize Engines (Only pre-init Ollama and PaddleOCR)
    print("Checking engine pre-initialization...")
    global ocr_engine_instance, llm_engine_instance, fallback_llm_engine_instance
    ocr_type = active_profile.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))

    llm_type = active_profile.get('llm_engine', 'gemini')
    model = active_profile.get('model', 'gemini-2.5-flash-lite')
    fallback_model = active_profile.get('fallback_model', 'None')
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'),
                                           status_callback=lambda msg: print(f"Init status: {msg}"))
        if fallback_model and fallback_model != "None":
             print("Initializing Fallback Ollama Engine...")
             fallback_llm_engine_instance = OllamaEngine(fallback_model, config.get('ollama_url', 'http://localhost:11434'),
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

    if config.get('background', False) and HAS_PYSTRAY:
        print("Running in background tray mode...")
        icon = create_tray_icon(exit_app)

        # This blocks until the icon is stopped
        icon.run()
    else:
        print("Running in console mode. Press Ctrl+C to exit.")
        try:
            while is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            exit_app()

    # Cleanup
    keyboard.unhook_all()
    print("Goodbye!")


if __name__ == '__main__':
    main()
