"""WhisperLive service lifecycle management.

Handles starting, health-checking, and cleaning up the WhisperLive
real-time transcription server process.
"""
import logging
import os
import subprocess
import sys
import time

logger = logging.getLogger(__name__)

# Path to WhisperLive service directory
_WHISPERLIVE_PATH = os.path.join(
    str(os.path.dirname(os.path.dirname(str(os.path.dirname(__file__))))),
    "services",
    "whisperlive",
)


def is_whisperlive_service_online(host: str = "localhost", port: int = 9090) -> bool:
    """Check if WhisperLive service is online by checking if port is open."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"WhisperLive service health check failed: {e}")
        return False


def start_whisperlive_service(model_size: str = "small") -> subprocess.Popen | None:
    """Start WhisperLive service if not already running."""
    server_script = os.path.join(_WHISPERLIVE_PATH, "run_server.py")
    if not os.path.exists(server_script):
        logger.error(f"WhisperLive server script not found at {server_script}")
        return None

    venv_python = (
        os.path.join(_WHISPERLIVE_PATH, ".venv", "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(_WHISPERLIVE_PATH, ".venv", "bin", "python")
    )
    python_exec = venv_python if os.path.exists(venv_python) else sys.executable

    try:
        process = subprocess.Popen(
            [
                python_exec,
                server_script,
                "--port",
                "9090",
                "--backend",
                "faster_whisper",
                "--faster_whisper_custom_model_path",
                model_size,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info(f"WhisperLive service starting with PID: {process.pid}...")
        return process
    except Exception as e:
        logger.error(f"Error starting WhisperLive service: {e}")
        return None


class WhisperLiveManager:
    """Manages the WhisperLive service process lifecycle."""

    def __init__(self):
        self.process: subprocess.Popen | None = None

    def ensure_service(self, config: dict) -> bool:
        """Ensure WhisperLive service is running, starting it if necessary.

        Returns ``True`` if the service is online.
        """
        if is_whisperlive_service_online():
            return True

        logger.warning("WhisperLive service not detected. Attempting to start...")
        self.warmup(config)
        return is_whisperlive_service_online()

    def warmup(self, config: dict):
        """Start WhisperLive service and wait for it to be ready."""
        logger.info("Warming up WhisperLive service...")
        if not is_whisperlive_service_online():
            logger.info("WhisperLive service is not running. Starting it now...")
            model_size = config.get("transcription_model", "small")
            self.process = start_whisperlive_service(model_size)
            time.sleep(10)  # Give it time to start and load models
            if self.process and self.process.poll() is not None:
                logger.error("Failed to start WhisperLive service.")
                self.process = None
            elif not is_whisperlive_service_online():
                logger.error("WhisperLive service failed to become online.")
            else:
                logger.info("WhisperLive service started successfully.")
        else:
            logger.info("WhisperLive service is already running.")

    def cleanup(self):
        """Terminate the WhisperLive service process if we started it."""
        if self.process:
            logger.info("Terminating WhisperLive service process...")
            self.process.terminate()
            self.process.wait()
            self.process = None
