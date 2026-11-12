"""System tray icon and console/tray mode setup."""

import logging
import os
import platform
import signal
import threading

import pystray
from PIL import Image

from app.context import AppContext
from config.settings import load_profiles
from core.output import open_settings, show_pairing_dialog, toggle_control_panel

logger = logging.getLogger(__name__)


def _profile_menu(ctx: AppContext) -> pystray.Menu:
    """One radio item per profile; picking one switches to it."""
    from app.profiles import switch_profile

    def item(profile):
        profile_id = profile.get("id", "")
        return pystray.MenuItem(
            profile.get("name", profile_id),
            lambda _icon, _item: switch_profile(ctx, profile_id),
            checked=lambda _item: ctx.profile.get("id") == profile_id,
            radio=True,
        )

    return pystray.Menu(lambda: (item(p) for p in load_profiles()))


def create_tray_icon(ctx: AppContext):
    """Create and return a pystray system-tray icon."""
    from app.lifecycle import exit_app

    # Load custom tray icon from assets, fall back to generated if missing
    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "icon.ico",
    )
    if os.path.exists(icon_path):
        img = Image.open(icon_path)
    else:
        img = Image.new("RGB", (64, 64), color=(73, 109, 137))

    def quit_action(icon):
        icon.stop()
        exit_app(ctx)

    menu = pystray.Menu(
        pystray.MenuItem("Toggle Panel", lambda: toggle_control_panel()),
        pystray.MenuItem("Profile", _profile_menu(ctx)),
        pystray.MenuItem("Settings…", lambda: open_settings()),
        pystray.MenuItem("Pair Android Remote", lambda: show_pairing_dialog()),
        pystray.MenuItem("Exit", quit_action),
    )
    return pystray.Icon("SnapSolve", img, "SnapSolve", menu)


def setup_tray_or_console_mode(ctx: AppContext):
    """Run the tray icon (background mode) or wire console signals."""
    if ctx.config.get("background", False):
        logger.info("Running in background tray mode...")

        def run_tray():
            create_tray_icon(ctx).run()

        threading.Thread(target=run_tray, daemon=True, name="tray").start()
        return

    logger.info("Running in console/Qt mode. Press Ctrl+C or close via tray to exit.")
    # On Windows, the SetConsoleCtrlHandler registered at startup handles
    # SIGINT/console-close. Elsewhere, use signal handlers plus a QTimer so
    # Python gets a chance to run them.
    if platform.system() != "Windows":
        from app.lifecycle import exit_app

        def _signal_exit(_sig, _frame):
            exit_app(ctx)

        signal.signal(signal.SIGINT, _signal_exit)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _signal_exit)

        from PyQt6.QtCore import QTimer

        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)
