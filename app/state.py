"""Global mutable state and shared utility helpers.

Every module in the ``app`` package reads/writes these module-level variables
via ``import app.state as state`` so that mutations are visible everywhere.
"""
import os
import threading

from core.output import show_popup, set_app_processing_state
from core.remote_control_server import stop_remote_control_server

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
is_running = True
is_processing = False
ocr_engine_instance = None
cancel_event = threading.Event()

llm_engine_instance = None  # LLMEngine | None
fallback_llm_engine_instance = None  # LLMEngine | None
session_manager = None  # SessionManager | None
audio_sink_instance = None  # AudioSink | None

# Multi-capture state
is_multi_capturing = False
multi_capture_texts: list[str] = []
multi_capture_images: list[str] = []

# Default model name
DEFAULT_MODEL_NAME = "gemini-2.5-flash-lite"


# ---------------------------------------------------------------------------
# Processing helpers
# ---------------------------------------------------------------------------
def set_processing(processing: bool):
    """Update the global processing flag and notify the UI."""
    global is_processing
    is_processing = processing
    set_app_processing_state(processing)
    if not processing:
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


# ---------------------------------------------------------------------------
# Application exit
# ---------------------------------------------------------------------------
def exit_app():
    """Perform best-effort cleanup and force-terminate the process."""
    global is_running
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
