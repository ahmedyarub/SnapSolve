"""System tray icon and console/tray mode setup."""
import os
import platform
import signal
import threading

import pystray
from PIL import Image

from core.output import toggle_control_panel


def create_tray_icon(on_exit):
    """Create and return a pystray system-tray icon."""
    # Load custom tray icon from assets, fall back to generated if missing
    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icon.ico"
    )
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
