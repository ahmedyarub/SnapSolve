import base64
import json
import logging
import threading
import urllib.error
import urllib.request

from core.sinks.base import Sink

from .base import LLMEngine

logger = logging.getLogger(__name__)


class OllamaEngine(LLMEngine):
    def __init__(
        self,
        model: str,
        ollama_url: str,
        session_manager=None,
        status_callback=None,
        timeout: float = 300,
    ):
        super().__init__(model, session_manager=session_manager)
        self.ollama_url = ollama_url
        # Seconds to wait for the server (model loading on first use is slow).
        self.timeout = timeout
        if status_callback:
            status_callback("Ollama engine initialized")

    def is_available(self) -> tuple[bool, str]:
        """Check if the Ollama API server is reachable."""
        try:
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return True, ""
            return False, f"Ollama returned status {resp.status}"
        except OSError:  # URLError, HTTPError and timeouts are all OSErrors
            return False, f"Ollama is not reachable at {self.ollama_url}"

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Ollama (loading model into memory)...")
        try:
            payload = {"model": self.model, "prompt": "Hello", "stream": False}
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # The first call loads the model into memory, which can take minutes.
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                _ = response.read()
            if status_callback:
                status_callback("Ollama warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Ollama warmup failed: {e!s}")
            logger.warning("Ollama warmup failed: %s", e)
            return False

    @property
    def supports_images(self) -> bool:
        return (
            True  # Ollama generally supports images if the model does, we let it try.
        )

    def _execute_request(
        self,
        payload: dict,
        sink: Sink,
        is_main: bool,
        cancel_event: threading.Event | None = None,
    ) -> str:
        try:
            if cancel_event and cancel_event.is_set():
                return "Cancelled"

            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps({**payload, "stream": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            pieces: list[str] = []
            # Streams one JSON object per line; the timeout applies to each read.
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                for line in response:
                    if cancel_event and cancel_event.is_set():
                        return "Cancelled"
                    if not line.strip():
                        continue
                    data = json.loads(line.decode("utf-8"))
                    if data.get("error"):
                        return f"Error calling Ollama API: {data['error']}"
                    piece = data.get("response", "")
                    if piece:
                        pieces.append(piece)
                        if sink:
                            sink.process_chunk(piece, is_main=is_main)
                    if data.get("done"):
                        break
            return "".join(pieces).strip()
        except Exception as e:
            return f"Error calling Ollama API: {e!s}"

    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        logger.info("Ollama text request: %s at %s", self.model, self.ollama_url)
        if status_callback:
            status_callback("Processing text with Ollama...")

        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)

        payload = {"model": self.model, "prompt": full_prompt, "stream": False}

        return self._execute_request(payload, sink, is_main, cancel_event)

    def process_image(
        self,
        prompt: str,
        image_path: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        logger.info("Ollama image request: %s at %s", self.model, self.ollama_url)
        if status_callback:
            status_callback("Processing image with Ollama...")

        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)

        payload = {"model": self.model, "prompt": full_prompt, "stream": False}

        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                payload["images"] = [encoded_string]
        except Exception as e:
            return f"Error reading image: {e!s}"

        return self._execute_request(payload, sink, is_main, cancel_event)
