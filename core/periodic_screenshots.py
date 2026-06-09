"""Periodic screenshot capture service.

Captures full-screen screenshots during active sessions at a configurable
interval and/or on keyboard/mouse activity.  Screenshots are saved to
``sessions/<session_id>/screenshots/`` with timestamped filenames.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING

from PIL import ImageGrab, ImageChops

if TYPE_CHECKING:
    from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"


class PeriodicScreenshotService:
    """Captures periodic full-screen screenshots during a session.

    Supports two capture triggers:

    1. **Time-based**: captures every *interval* seconds.
    2. **Activity-based**: captures on keyboard/mouse events with a
       configurable minimum delay between activity-triggered captures.

    Parameters
    ----------
    config : dict
        Live application config dict (mutated in place by callers).
    session_manager : SessionManager
        Used to resolve the current session's screenshots directory.
    """

    def __init__(self, config: dict, session_manager: "SessionManager") -> None:
        self._config = config
        self._session_manager = session_manager
        self._running = False
        self._timer_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_capture_time: float = 0.0
        self._last_activity_capture_time: float = 0.0
        self._keyboard_hook = None
        self._mouse_hook = None
        self._lock = threading.Lock()
        self._last_image: ImageGrab.Image.Image | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start capturing periodic screenshots."""
        if self._running:
            logger.debug("PeriodicScreenshotService is already running")
            return

        self._running = True
        self._stop_event.clear()
        self._last_image = None

        interval = self._config.get("periodic_screenshots_interval", 15)

        # Start the timer thread for periodic captures
        self._timer_thread = threading.Thread(
            target=self._timer_loop,
            args=(interval,),
            daemon=True,
            name="PeriodicScreenshots",
        )
        self._timer_thread.start()

        # Hook keyboard/mouse activity if enabled
        if self._config.get("periodic_screenshots_on_activity", False):
            self._install_activity_hooks()

        logger.info(
            "Periodic screenshots started (interval=%ds, activity=%s)",
            interval,
            self._config.get("periodic_screenshots_on_activity", False),
        )

    def stop(self) -> None:
        """Stop capturing periodic screenshots."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        self._remove_activity_hooks()

        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=3)
        self._timer_thread = None

        logger.info("Periodic screenshots stopped")

    def set_enabled(self, enabled: bool) -> None:
        """Toggle the service on or off."""
        if enabled and not self._running:
            self.start()
        elif not enabled and self._running:
            self.stop()

    def update_activity_hooks(self) -> None:
        """Re-evaluate activity hooks based on current config.

        Call this after changing ``periodic_screenshots_on_activity`` at
        runtime so the hooks are installed or removed accordingly.
        """
        if not self._running:
            return

        if self._config.get("periodic_screenshots_on_activity", False):
            self._install_activity_hooks()
        else:
            self._remove_activity_hooks()

    @property
    def is_running(self) -> bool:
        """Whether the service is currently capturing screenshots."""
        return self._running

    # ------------------------------------------------------------------
    # Internal — timer loop
    # ------------------------------------------------------------------

    def _timer_loop(self, interval: int) -> None:
        """Periodic capture loop running on a daemon thread."""
        while not self._stop_event.is_set():
            self._capture_screenshot()
            # Use wait() for interruptible sleep
            self._stop_event.wait(timeout=interval)

    # ------------------------------------------------------------------
    # Internal — activity hooks
    # ------------------------------------------------------------------

    def _install_activity_hooks(self) -> None:
        """Install keyboard and mouse hooks for activity-triggered captures."""
        if self._keyboard_hook is not None:
            return  # Already installed

        try:
            import keyboard as kb  # noqa: PLC0415

            self._keyboard_hook = kb.hook(self._on_keyboard_activity, suppress=False)
            logger.debug("Keyboard activity hook installed")
        except Exception as exc:
            logger.warning("Failed to install keyboard activity hook: %s", exc)

        try:
            import mouse  # noqa: PLC0415

            self._mouse_hook = mouse.hook(self._on_mouse_activity)
            logger.debug("Mouse activity hook installed")
        except Exception as exc:
            logger.warning("Failed to install mouse activity hook: %s", exc)

    def _remove_activity_hooks(self) -> None:
        """Remove keyboard and mouse hooks."""
        if self._keyboard_hook is not None:
            try:
                import keyboard as kb  # noqa: PLC0415

                kb.unhook(self._keyboard_hook)
            except Exception as exc:
                logger.warning("Failed to unhook keyboard activity: %s", exc)
            self._keyboard_hook = None

        if self._mouse_hook is not None:
            try:
                import mouse  # noqa: PLC0415

                mouse.unhook(self._mouse_hook)
            except Exception as exc:
                logger.warning("Failed to unhook mouse activity: %s", exc)
            self._mouse_hook = None

    def _on_keyboard_activity(self, _event) -> None:
        """Callback for keyboard events — triggers an activity capture."""
        self._on_activity()

    def _on_mouse_activity(self, _event) -> None:
        """Callback for mouse events — triggers an activity capture."""
        self._on_activity()

    def _on_activity(self) -> None:
        """Handle an activity event from keyboard or mouse.

        Captures a screenshot only if the minimum delay since the last
        activity-triggered capture has elapsed.
        """
        if not self._running:
            return

        min_delay = self._config.get("periodic_screenshots_activity_min_delay", 5)
        now = time.monotonic()

        with self._lock:
            if now - self._last_activity_capture_time < min_delay:
                return
            self._last_activity_capture_time = now

        # Capture in background so we don't block the hook callback
        threading.Thread(
            target=self._capture_screenshot,
            daemon=True,
            name="ActivityScreenshot",
        ).start()

    # ------------------------------------------------------------------
    # Internal — capture
    # ------------------------------------------------------------------

    def _screenshots_dir(self) -> str | None:
        """Return the screenshots directory for the current session, or None."""
        session_id = self._session_manager.current_session_id
        if not session_id:
            return None
        from core.session_manager import _session_screenshots_dir  # noqa: PLC0415

        screenshots_dir = _session_screenshots_dir(session_id)
        os.makedirs(screenshots_dir, exist_ok=True)
        return screenshots_dir

    def _capture_screenshot(self) -> None:
        """Capture a full-screen screenshot and save it to the session folder."""
        try:
            save_dir = self._screenshots_dir()
            if not save_dir:
                logger.debug("No active session — skipping periodic screenshot")
                return

            img = ImageGrab.grab()

            if self._last_image is not None:
                if img.size == self._last_image.size and img.mode == self._last_image.mode:
                    diff = ImageChops.difference(img, self._last_image)
                    if diff.getbbox() is None:
                        logger.debug("Screenshot identical to previous, skipping capture")
                        return

            self._last_image = img

            timestamp = datetime.now().strftime(DATE_FORMAT)
            filename = f"{timestamp}.png"
            filepath = os.path.join(save_dir, filename)
            img.save(filepath)

            with self._lock:
                self._last_capture_time = time.monotonic()

            logger.debug("Periodic screenshot saved: %s", filepath)

            # Write JSON sidecar with active window metadata
            if self._config.get("track_active_window", True):
                self._write_window_sidecar(save_dir, timestamp)

        except Exception as exc:
            logger.error("Failed to capture periodic screenshot: %s", exc)

    def _write_window_sidecar(self, save_dir: str, timestamp: str) -> None:
        """Write a JSON sidecar file with the active window's metadata."""
        try:
            from core.active_window import get_active_window_info  # noqa: PLC0415

            info = get_active_window_info()
            if info is None:
                return

            sidecar_path = os.path.join(save_dir, f"{timestamp}.json")
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)

            logger.debug("Window sidecar saved: %s", sidecar_path)
        except Exception as exc:
            logger.debug("Failed to write window sidecar: %s", exc)
