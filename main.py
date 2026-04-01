import time
import keyboard
import threading
import sys
import os

from config import get_config, save_config
from selector import get_coordinates
from processor import capture_and_process
from output import output_result

try:
    from PIL import Image
    import pystray
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# Global state
is_running = True
is_processing = False

def create_tray_icon(on_exit):
    # Create a simple tray icon
    img = Image.new('RGB', (64, 64), color=(73, 109, 137))

    def quit_action(icon, item):
        icon.stop()
        on_exit()

    menu = pystray.Menu(pystray.MenuItem('Exit', quit_action))
    icon = pystray.Icon("ScreenQA", img, "Screen Capture QA", menu)
    return icon

def handle_hotkey(config):
    global is_processing
    if is_processing:
        return

    is_processing = True
    print("Capturing and processing...")

    try:
        result = capture_and_process(config.get('api_key'), config.get('coordinates'))
        print(f"Result: {result}")
        output_result(result, config.get('output_mode'))
    except Exception as e:
        print(f"Error during processing: {e}")

    is_processing = False

def exit_app():
    global is_running
    is_running = False
    print("Exiting...")

def main():
    global is_running

    print("Initializing Screen Capture & Gemini QA App...")
    config = get_config()

    if not config.get('api_key'):
        print("Warning: API Key not set. Please set it via --api-key or config.json.")

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

    hotkey = config.get('hotkey', 'ctrl+alt+shift+s')

    print(f"Listening for hotkey: {hotkey}")

    # We use add_hotkey with suppress=True if possible, but default is fine
    keyboard.add_hotkey(hotkey, handle_hotkey, args=[config])

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
