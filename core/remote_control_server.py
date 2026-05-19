import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

import pyautogui

logger = logging.getLogger(__name__)

# Shared error message constant to avoid duplication.
X_Y_REQUIRED_ERROR = "x and y parameters are required"


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the SnapSolve remote control server.

    Endpoints
    ---------
    GET  /status              — Health-check; returns ``{"status": "running"}``.
    GET  /                    — Lists all available endpoints.
    POST /action              — Triggers a SnapSolve action (capture, cancel, etc.).
    POST /mouse/move          — Moves the cursor to a relative position (0–1 range).
    POST /mouse/click         — Single mouse-button click at the current position.
    POST /mouse/double_click  — Double mouse-button click at the current position.
    POST /mouse/drag_start    — Presses and holds a mouse button (drag begin).
    POST /mouse/drag_end      — Releases the held mouse button (drag end).
    POST /mouse/scroll        — Scrolls the wheel; positive delta = up, negative = down.
    """

    # The live application config dict is injected at server construction time so that
    # action handlers can look up the active profile without re-parsing CLI arguments
    # on every request.
    app_config: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _set_cors_headers(self) -> None:
        """Append permissive CORS headers required by the Android HTTP client."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json_response(self, status_code: int, data: dict) -> None:
        """Serialise *data* to JSON and write it as the HTTP response body."""
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error_response(self, status_code: int, message: str) -> None:
        """Convenience wrapper that sends a JSON ``{"error": message}`` response."""
        self._send_json_response(status_code, {"error": message})

    # ------------------------------------------------------------------
    # HTTP verb handlers
    # ------------------------------------------------------------------

    def do_OPTIONS(self):  # noqa: N802
        """Handle CORS pre-flight requests."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        """Handle GET requests for /status and /."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/status":
            self._send_json_response(200, {"status": "running", "server": "SnapSolve Remote Control"})
        elif parsed_path.path == "/":
            self._send_json_response(
                200,
                {
                    "message": "SnapSolve Remote Control Server",
                    "endpoints": [
                        "/status",
                        "/action",
                        "/mouse/move",
                        "/mouse/click",
                        "/mouse/double_click",
                        "/mouse/drag_start",
                        "/mouse/drag_end",
                        "/mouse/scroll",
                    ],
                },
            )
        else:
            self._send_error_response(404, "Endpoint not found")

    def do_POST(self):  # noqa: N802
        """Route POST requests to the appropriate handler."""
        parsed_path = urlparse(self.path)

        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))
        except (ValueError, KeyError, TypeError) as exc:
            self._send_error_response(400, f"Invalid JSON data: {exc}")
            return

        routes = {
            "/action": self._handle_action,
            "/mouse/move": self._handle_mouse_move,
            "/mouse/click": self._handle_mouse_click,
            "/mouse/double_click": self._handle_mouse_double_click,
            "/mouse/drag_start": self._handle_mouse_drag_start,
            "/mouse/drag_end": self._handle_mouse_drag_end,
            "/mouse/scroll": self._handle_mouse_scroll,
        }
        handler = routes.get(parsed_path.path)
        if handler:
            handler(data)
        else:
            self._send_error_response(404, "Endpoint not found")

    # ------------------------------------------------------------------
    # Action handler
    # ------------------------------------------------------------------

    def _handle_action(self, data: dict) -> None:
        """Dispatch a named SnapSolve action using the live application config.

        The config is passed in at server construction time (stored on the class) to
        avoid the expensive ``get_config()`` / ``parse_args()`` call on every request.

        Supported actions
        -----------------
        capture, reselect, multi_capture, end_multi_capture, cancel,
        toggle_stitching, cycle_source, toggle_panel, new_chat_session
        """
        action = data.get("action")
        if not action:
            self._send_error_response(400, "Action parameter is required")
            return

        # Import inside the function to avoid circular-import issues at module load.
        from main import (  # noqa: PLC0415
            handle_cancel,
            handle_capture,
            handle_cycle_source,
            handle_end_multi_capture,
            handle_multi_capture,
            handle_new_chat_session,
            handle_reselect,
            handle_toggle_panel,
            handle_toggle_stitching,
        )
        from config.settings import load_profiles, load_prompts  # noqa: PLC0415

        try:
            config = self.__class__.app_config
            profiles = load_profiles()
            prompts = load_prompts()

            active_profile_id = config.get("active_profile_id", "prof1")
            active_profile = next(
                (p for p in profiles if p.get("id") == active_profile_id),
                profiles[0] if profiles else {},
            )

            prompt_id = active_profile.get("prompt_id", "default")
            active_prompt = next(
                (p for p in prompts if p.get("id") == prompt_id),
                prompts[0] if prompts else {},
            )
            active_prompt_text = active_prompt.get("text", "answer the following question quickly and briefly")

            action_map = {
                "capture": lambda: handle_capture(config, active_profile, active_prompt_text),
                "reselect": lambda: handle_reselect(config),
                "multi_capture": lambda: handle_multi_capture(config, active_profile),
                "end_multi_capture": lambda: handle_end_multi_capture(config, active_profile, active_prompt_text),
                "cancel": handle_cancel,
                "toggle_stitching": lambda: handle_toggle_stitching(config, active_profile),
                "cycle_source": lambda: handle_cycle_source(config, active_profile),
                "toggle_panel": handle_toggle_panel,
                "new_chat_session": lambda: handle_new_chat_session(config),
            }

            fn = action_map.get(action)
            if fn is None:
                self._send_error_response(400, f"Unknown action: {action}")
                return

            fn()
            self._send_json_response(200, {"status": "success", "action": action})
            logger.info("Remote control action executed: %s", action)

        except Exception as exc:
            logger.error("Error executing action %s: %s", action, exc)
            self._send_error_response(500, f"Error executing action: {exc}")

    # ------------------------------------------------------------------
    # Mouse handlers
    # ------------------------------------------------------------------

    def _handle_mouse_move(self, data: dict) -> None:
        """Move the cursor to relative coordinates (0–1 range).

        The server maps the relative position to absolute screen pixels using
        ``pyautogui.size()`` at request time so it always reflects the current
        screen resolution.
        """
        try:
            x = data.get("x")
            y = data.get("y")
            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            screen_width, screen_height = pyautogui.size()
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)
            pyautogui.moveTo(abs_x, abs_y)
            self._send_json_response(200, {"status": "success", "position": {"x": abs_x, "y": abs_y}})

        except Exception as exc:
            logger.error("Error moving mouse: %s", exc)
            self._send_error_response(500, f"Error moving mouse: {exc}")

    def _handle_mouse_click(self, data: dict) -> None:
        """Send a single click with the specified button (``left``, ``right``, or ``middle``)."""
        try:
            button = data.get("button", "left")
            if button == "left":
                pyautogui.click()
            elif button == "right":
                pyautogui.rightClick()
            elif button == "middle":
                pyautogui.middleClick()
            else:
                self._send_error_response(400, f"Unknown button: {button}")
                return
            self._send_json_response(200, {"status": "success", "action": "click", "button": button})

        except Exception as exc:
            logger.error("Error clicking mouse: %s", exc)
            self._send_error_response(500, f"Error clicking mouse: {exc}")

    def _handle_mouse_double_click(self, data: dict) -> None:
        """Send a double click with the specified button."""
        try:
            button = data.get("button", "left")
            if button == "left":
                pyautogui.doubleClick()
            elif button == "right":
                pyautogui.rightClick()
                pyautogui.rightClick()
            elif button == "middle":
                pyautogui.middleClick()
                pyautogui.middleClick()
            else:
                self._send_error_response(400, f"Unknown button: {button}")
                return
            self._send_json_response(200, {"status": "success", "action": "double_click", "button": button})

        except Exception as exc:
            logger.error("Error double-clicking mouse: %s", exc)
            self._send_error_response(500, f"Error double-clicking mouse: {exc}")

    def _handle_mouse_drag_start(self, data: dict) -> None:
        """Press and hold the left mouse button at the specified relative position."""
        try:
            x = data.get("x")
            y = data.get("y")
            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            screen_width, screen_height = pyautogui.size()
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)
            pyautogui.mouseDown(abs_x, abs_y)
            self._send_json_response(200, {"status": "success", "action": "drag_start", "position": {"x": abs_x, "y": abs_y}})

        except Exception as exc:
            logger.error("Error starting drag: %s", exc)
            self._send_error_response(500, f"Error starting drag: {exc}")

    def _handle_mouse_drag_end(self, data: dict) -> None:
        """Release the held mouse button at the specified relative position."""
        try:
            x = data.get("x")
            y = data.get("y")
            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            screen_width, screen_height = pyautogui.size()
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)
            pyautogui.mouseUp(abs_x, abs_y)
            self._send_json_response(200, {"status": "success", "action": "drag_end", "position": {"x": abs_x, "y": abs_y}})

        except Exception as exc:
            logger.error("Error ending drag: %s", exc)
            self._send_error_response(500, f"Error ending drag: {exc}")

    def _handle_mouse_scroll(self, data: dict) -> None:
        """Scroll the mouse wheel.

        Parameters
        ----------
        data:
            JSON body with a ``delta`` integer.  Positive values scroll up;
            negative values scroll down.
        """
        try:
            delta = data.get("delta", 1)
            pyautogui.scroll(delta)
            self._send_json_response(200, {"status": "success", "action": "scroll", "delta": delta})

        except Exception as exc:
            logger.error("Error scrolling mouse: %s", exc)
            self._send_error_response(500, f"Error scrolling mouse: {exc}")

    def log_message(self, fmt: str, *args) -> None:  # noqa: N802
        """Route BaseHTTPRequestHandler access logs through the standard logger."""
        logger.info("%s - %s", self.address_string(), fmt % args if args else fmt)


class RemoteControlServer:
    """Threaded HTTP server that exposes mouse control and SnapSolve actions over LAN.

    Usage
    -----
    .. code-block:: python

        server = RemoteControlServer(host="0.0.0.0", port=8080, config=app_config)
        server.start()
        # … application runs …
        server.stop()
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080, config: dict | None = None):
        self.host = host
        self.port = port
        self.server: HTTPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.is_running = False

        # Inject the live config into the handler class so each request can use it
        # without re-parsing CLI arguments.
        RemoteControlHandler.app_config = config or {}

    def start(self) -> None:
        """Bind the socket and start accepting requests in a daemon thread."""
        if self.is_running:
            logger.warning("Remote control server is already running")
            return

        try:
            self.server = HTTPServer((self.host, self.port), RemoteControlHandler)
            self.is_running = True
            self.server_thread = threading.Thread(target=self._run_server, daemon=True, name="RemoteControlServer")
            self.server_thread.start()
            logger.info("Remote control server started on http://%s:%s", self.host, self.port)
            print(f"Remote control server started on http://{self.host}:{self.port}")

        except Exception as exc:
            logger.error("Failed to start remote control server: %s", exc)
            raise

    def _run_server(self) -> None:
        """Blocking serve loop executed on the daemon thread."""
        assert self.server is not None
        try:
            self.server.serve_forever()
        except Exception as exc:
            logger.error("Server error: %s", exc)
            self.is_running = False

    def stop(self) -> None:
        """Gracefully shut down the server and join the daemon thread."""
        if not self.is_running:
            return

        try:
            self.is_running = False
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            if self.server_thread:
                self.server_thread.join(timeout=5)
            logger.info("Remote control server stopped")

        except Exception as exc:
            logger.error("Error stopping remote control server: %s", exc)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

# Global singleton — one server per process.
remote_control_server: RemoteControlServer | None = None


def start_remote_control_server(host: str = "0.0.0.0", port: int = 8080, config: dict | None = None) -> RemoteControlServer:
    """Create (if needed) and start the global remote control server.

    Parameters
    ----------
    host:   Network interface to bind. Use ``"0.0.0.0"`` to accept connections on
            all interfaces (default).
    port:   TCP port to listen on (default 8080).
    config: The live application config dict. Passed to action handlers so they
            do not need to call ``get_config()`` on every request.

    Returns
    -------
    The running :class:`RemoteControlServer` instance.
    """
    global remote_control_server

    if remote_control_server is None:
        remote_control_server = RemoteControlServer(host, port, config)

    remote_control_server.start()
    return remote_control_server


def stop_remote_control_server() -> None:
    """Stop and discard the global remote control server."""
    global remote_control_server

    if remote_control_server:
        remote_control_server.stop()
        remote_control_server = None
