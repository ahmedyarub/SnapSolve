import platform
import sys
import threading
import time

import keyboard

from config import get_config, save_config
from output import output_result, show_popup
from processor import capture_and_process, PaddleOCREngine, NoOCREngine, GeminiCLIEngine, OllamaEngine, GoogleGenAIEngine
from selector import get_coordinates

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

def handle_capture(config):
    global is_processing
    if is_processing:
        return

    is_processing = True
    print("Capturing and processing...")

    def status_update(msg):
        if 'popup' in config.get('output_mode', ['popup']):
            show_popup(msg, auto_close=None)

    def _capture():
        global is_processing
        try:
            global ocr_engine_instance, llm_engine_instance
            result = capture_and_process(
                config.get('coordinates'),
                model=config.get('model', 'gemini-2.5-flash-lite'),
                llm_engine=config.get('llm_engine', 'gemini'),
                ocr_engine=config.get('ocr_engine', 'none'),
                ollama_url=config.get('ollama_url', 'http://localhost:11434'),
                google_genai_api_key=config.get('google_genai_api_key', ''),
                ocr_engine_instance=ocr_engine_instance,
                llm_engine_instance=llm_engine_instance,
                status_callback=status_update
            )
            print(f"Result: {result}")
            # Pass the voice_id config if present
            output_result(result, config.get('output_mode'), config.get('voice_id'))
        except Exception as e:
            print(f"Error during processing: {e}")

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

def main():
    global is_running

    print("Initializing Screen Capture & Gemini QA App...")
    config = get_config()

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
    global ocr_engine_instance, llm_engine_instance
    ocr_type = config.get('ocr_engine', 'none')
    if ocr_type == "paddleocr":
        print("Starting PaddleOCR (this may take a moment to warmup)...")
        ocr_engine_instance = PaddleOCREngine(status_callback=lambda msg: print(f"Init status: {msg}"))

    llm_type = config.get('llm_engine', 'gemini')
    model = config.get('model', 'gemini-2.5-flash-lite')
    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine_instance = OllamaEngine(model, config.get('ollama_url', 'http://localhost:11434'), status_callback=lambda msg: print(f"Init status: {msg}"))

    hotkeys = config.get('hotkeys', [])

    for hk in hotkeys:
        action = hk.get('action')
        key = hk.get('key')
        if not action or not key:
            continue

        print(f"Listening for '{action}' hotkey: {key}")

        if action == 'capture':
            keyboard.add_hotkey(key, handle_capture, args=[config])
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
