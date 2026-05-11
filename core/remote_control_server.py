import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import pyautogui

logger = logging.getLogger(__name__)

# Constants for error messages
X_Y_REQUIRED_ERROR = "x and y parameters are required"


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP handler for remote control requests."""

    def _set_cors_headers(self):
        """Set CORS headers for cross-origin requests."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json_response(self, status_code, data):
        """Send JSON response."""
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = json.dumps(data)
        self.wfile.write(response.encode("utf-8"))

    def _send_error_response(self, status_code, message):
        """Send error response."""
        self._send_json_response(status_code, {"error": message})

    def do_OPTIONS(self):  # noqa: N802
        """Handle OPTIONS request for CORS preflight."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        """Handle GET requests."""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/status":
            self._send_json_response(
                200, {"status": "running", "server": "SnapSolve Remote Control"}
            )
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
        """Handle POST requests."""
        parsed_path = urlparse(self.path)

        try:
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))
        except (ValueError, KeyError, TypeError) as e:
            self._send_error_response(400, f"Invalid JSON data: {str(e)}")
            return

        if parsed_path.path == "/action":
            self._handle_action(data)
        elif parsed_path.path == "/mouse/move":
            self._handle_mouse_move(data)
        elif parsed_path.path == "/mouse/click":
            self._handle_mouse_click(data)
        elif parsed_path.path == "/mouse/double_click":
            self._handle_mouse_double_click(data)
        elif parsed_path.path == "/mouse/drag_start":
            self._handle_mouse_drag_start(data)
        elif parsed_path.path == "/mouse/drag_end":
            self._handle_mouse_drag_end(data)
        elif parsed_path.path == "/mouse/scroll":
            self._handle_mouse_scroll(data)
        else:
            self._send_error_response(404, "Endpoint not found")

    def _handle_action(self, data):
        """Handle action requests."""
        action = data.get("action")

        if not action:
            self._send_error_response(400, "Action parameter is required")
            return

        # Import here to avoid circular imports
        from main import (
            handle_capture,
            handle_reselect,
            handle_multi_capture,
            handle_end_multi_capture,
            handle_cancel,
            handle_toggle_stitching,
            handle_cycle_source,
            handle_toggle_panel,
            handle_new_chat_session,
        )

        # Import config and profile data
        from config.settings import get_config, load_profiles, load_prompts

        try:
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
                (p for p in prompts if p.get("id") == prompt_id),
                prompts[0] if prompts else {},
            )
            active_prompt_text = active_prompt.get(
                "text", "answer the following question quickly and briefly"
            )

            # Execute the appropriate action
            if action == "capture":
                handle_capture(config, active_profile, active_prompt_text)
            elif action == "reselect":
                handle_reselect(config)
            elif action == "multi_capture":
                handle_multi_capture(config, active_profile)
            elif action == "end_multi_capture":
                handle_end_multi_capture(config, active_profile, active_prompt_text)
            elif action == "cancel":
                handle_cancel()
            elif action == "toggle_stitching":
                handle_toggle_stitching(config, active_profile)
            elif action == "cycle_source":
                handle_cycle_source(config, active_profile)
            elif action == "toggle_panel":
                handle_toggle_panel()
            elif action == "new_chat_session":
                handle_new_chat_session(config)
            else:
                self._send_error_response(400, f"Unknown action: {action}")
                return

            self._send_json_response(200, {"status": "success", "action": action})
            logger.info(f"Remote control action executed: {action}")

        except Exception as e:
            logger.error(f"Error executing action {action}: {str(e)}")
            self._send_error_response(500, f"Error executing action: {str(e)}")

    def _handle_mouse_move(self, data):
        """Handle mouse move requests."""
        try:
            x = data.get("x")
            y = data.get("y")

            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            # Get screen dimensions
            screen_width, screen_height = pyautogui.size()

            # Convert relative coordinates (0-1) to absolute coordinates
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)

            pyautogui.moveTo(abs_x, abs_y)
            self._send_json_response(
                200, {"status": "success", "position": {"x": abs_x, "y": abs_y}}
            )

        except Exception as e:
            logger.error(f"Error moving mouse: {str(e)}")
            self._send_error_response(500, f"Error moving mouse: {str(e)}")

    def _handle_mouse_click(self, data):
        """Handle mouse click requests."""
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

            self._send_json_response(
                200, {"status": "success", "action": "click", "button": button}
            )

        except Exception as e:
            logger.error(f"Error clicking mouse: {str(e)}")
            self._send_error_response(500, f"Error clicking mouse: {str(e)}")

    def _handle_mouse_double_click(self, data):
        """Handle mouse double click requests."""
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

            self._send_json_response(
                200, {"status": "success", "action": "double_click", "button": button}
            )

        except Exception as e:
            logger.error(f"Error double clicking mouse: {str(e)}")
            self._send_error_response(500, f"Error double clicking mouse: {str(e)}")

    def _handle_mouse_drag_start(self, data):
        """Handle mouse drag start requests."""
        try:
            x = data.get("x")
            y = data.get("y")

            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            # Get screen dimensions
            screen_width, screen_height = pyautogui.size()

            # Convert relative coordinates (0-1) to absolute coordinates
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)

            pyautogui.mouseDown(abs_x, abs_y)
            self._send_json_response(
                200,
                {
                    "status": "success",
                    "action": "drag_start",
                    "position": {"x": abs_x, "y": abs_y},
                },
            )

        except Exception as e:
            logger.error(f"Error starting drag: {str(e)}")
            self._send_error_response(500, f"Error starting drag: {str(e)}")

    def _handle_mouse_drag_end(self, data):
        """Handle mouse drag end requests."""
        try:
            x = data.get("x")
            y = data.get("y")

            if x is None or y is None:
                self._send_error_response(400, X_Y_REQUIRED_ERROR)
                return

            # Get screen dimensions
            screen_width, screen_height = pyautogui.size()

            # Convert relative coordinates (0-1) to absolute coordinates
            abs_x = int(x * screen_width)
            abs_y = int(y * screen_height)

            pyautogui.mouseUp(abs_x, abs_y)
            self._send_json_response(
                200,
                {
                    "status": "success",
                    "action": "drag_end",
                    "position": {"x": abs_x, "y": abs_y},
                },
            )

        except Exception as e:
            logger.error(f"Error ending drag: {str(e)}")
            self._send_error_response(500, f"Error ending drag: {str(e)}")

    def _handle_mouse_scroll(self, data):
        """Handle mouse scroll requests."""
        try:
            delta = data.get("delta", 1)

            pyautogui.scroll(delta)
            self._send_json_response(
                200, {"status": "success", "action": "scroll", "delta": delta}
            )

        except Exception as e:
            logger.error(f"Error scrolling mouse: {str(e)}")
            self._send_error_response(500, f"Error scrolling mouse: {str(e)}")

    def log_message(self, format, *args):
        """Override log_message to use proper logging."""
        logger.info("%s - %s", self.address_string(), format % args if args else format)


class RemoteControlServer:
    """HTTP server for remote control functionality."""

    def __init__(self, host="0.0.0.0", port=8080):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.is_running = False

    def start(self):
        """Start the remote control server."""
        if self.is_running:
            logger.warning("Remote control server is already running")
            return

        try:
            self.server = HTTPServer((self.host, self.port), RemoteControlHandler)
            self.is_running = True

            # Start server in a separate thread
            self.server_thread = threading.Thread(target=self._run_server, daemon=True)
            self.server_thread.start()

            logger.info(
                f"Remote control server started on http://{self.host}:{self.port}"
            )
            print(f"Remote control server started on http://{self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Failed to start remote control server: {str(e)}")
            raise

    def _run_server(self):
        """Run the server loop."""
        try:
            self.server.serve_forever()
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
            self.is_running = False

    def stop(self):
        """Stop the remote control server."""
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

        except Exception as e:
            logger.error(f"Error stopping remote control server: {str(e)}")


# Global server instance
remote_control_server = None


def start_remote_control_server(host="0.0.0.0", port=8080):
    """Start the remote control server."""
    global remote_control_server

    if remote_control_server is None:
        remote_control_server = RemoteControlServer(host, port)

    remote_control_server.start()
    return remote_control_server


def stop_remote_control_server():
    """Stop the remote control server."""
    global remote_control_server

    if remote_control_server:
        remote_control_server.stop()
        remote_control_server = None
