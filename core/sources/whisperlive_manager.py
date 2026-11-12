"""WhisperLive service lifecycle management.

Handles starting, health-checking, and cleaning up the WhisperLive
real-time transcription server process.
"""

import logging
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)

STARTUP_TIMEOUT_S = 90  # model download/load on first start can take a while

# Every server process this app started, so shutdown can stop them all even
# when the SoundSource that started one has been replaced.
_started: set[subprocess.Popen] = set()
_started_lock = threading.Lock()

# Path to WhisperLive service directory
_WHISPERLIVE_PATH = os.path.join(
    str(os.path.dirname(os.path.dirname(str(os.path.dirname(__file__))))),
    "services",
    "whisperlive",
)
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(_WHISPERLIVE_PATH)), "logs")


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

    # The server's output goes to a log file. Pipes would never be read here,
    # and a full pipe buffer blocks the server mid-transcription.
    os.makedirs(_LOG_DIR, exist_ok=True)
    log_path = os.path.join(_LOG_DIR, "whisperlive_server.log")

    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
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
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
        logger.info(f"WhisperLive server output: {log_path}")
        logger.info(f"WhisperLive service starting with PID: {process.pid}...")
        with _started_lock:
            _started.add(process)
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
            _wait_until_online(self.process)
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
            _stop_process(self.process)
            self.process = None


def _wait_until_online(process: subprocess.Popen | None) -> None:
    """Poll until the server accepts connections, exits, or the timeout passes."""
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    while time.monotonic() < deadline:
        if process is None or process.poll() is not None:
            return
        if is_whisperlive_service_online():
            return
        time.sleep(0.5)


def _stop_process(process: subprocess.Popen, timeout: float = 5) -> None:
    if process.poll() is None:
        logger.info("Terminating WhisperLive service (PID %s)...", process.pid)
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)
    with _started_lock:
        _started.discard(process)


def stop_all_services() -> None:
    """Stop every WhisperLive server this app started (called on exit)."""
    with _started_lock:
        processes = list(_started)
    for process in processes:
        try:
            _stop_process(process)
        except OSError as e:
            logger.warning("Could not stop WhisperLive PID %s: %s", process.pid, e)
