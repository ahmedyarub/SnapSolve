import base64
import json
import logging
import mimetypes

import threading
from typing import Optional

import requests

from core.sinks.base import Sink
from .base import LLMEngine

logger = logging.getLogger(__name__)


class AntigravityEngine(LLMEngine):
    """LLM engine that communicates with the Antigravity SDK service over HTTP+SSE.

    The service wraps the google-antigravity Python SDK.
    Responses are streamed via Server-Sent Events for real-time token delivery.
    """

    def __init__(self, model: str, service_url: str, session_manager=None):
        super().__init__(model, session_manager=session_manager)
        self.service_url = service_url.rstrip("/")

    @property
    def supports_images(self) -> bool:
        return True

    @property
    def ai_coding_tool(self) -> bool:
        return True

    def warmup(self, status_callback=None) -> bool:
        """Check that the Antigravity service is reachable."""
        if status_callback:
            status_callback("Checking Antigravity service...")
        try:
            resp = requests.get(f"{self.service_url}/health", timeout=5)
            if resp.status_code == 200:
                if status_callback:
                    status_callback("Antigravity service ready.")
                return True
        except requests.ConnectionError:
            pass
        except Exception as e:
            logger.warning("Antigravity warmup error: %s", e)

        if status_callback:
            status_callback(f"Antigravity service not reachable at {self.service_url}")
        return False



    def _stream_chat(
        self,
        prompt: str,
        status_callback,
        sink: Optional[Sink],
        is_main: bool,
        cancel_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        new_session: bool = False,
        system_instructions: Optional[str] = None,
        image_base64: Optional[str] = None,
        image_mime_type: Optional[str] = None,
    ) -> str:
        """Send a chat request and stream SSE tokens to the sink."""
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        if status_callback:
            status_callback("Processing with Antigravity...")

        payload = {
            "prompt": prompt,
            "model": self.model,
            "cwd": cwd,
            "new_session": new_session,
            "system_instructions": system_instructions,
            "image_base64": image_base64,
            "image_mime_type": image_mime_type,
        }

        logger.info("[AntigravityEngine] POST %s/chat (cwd=%s)", self.service_url, cwd)

        try:
            resp = requests.post(
                f"{self.service_url}/chat",
                json=payload,
                stream=True,
                timeout=(10, None),  # 10s connect, no read timeout
            )
            resp.raise_for_status()
        except requests.ConnectionError:
            return f"Error: Cannot connect to Antigravity service at {self.service_url}. Is the service running?"
        except requests.HTTPError as e:
            return f"Error: Antigravity service returned {e.response.status_code}"
        except Exception as e:
            return f"Error: {str(e)}"

        result_chunks = []
        for line in resp.iter_lines(decode_unicode=True):
            if cancel_event and cancel_event.is_set():
                resp.close()
                return "Cancelled"

            if not line or not line.startswith("data: "):
                continue

            data = line[6:]  # Strip "data: " prefix
            if data == "[DONE]":
                break

            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue

            if "error" in parsed:
                return f"Error from Antigravity: {parsed['error']}"

            token = parsed.get("token", "")
            if token:
                result_chunks.append(token)
                if sink:
                    sink.process_chunk(token, is_main=is_main)

        result = "".join(result_chunks)
        logger.info("[AntigravityEngine] Captured %d chars of output", len(result))
        return result

    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        logger.info("[AntigravityEngine] Text Request started")

        project_folder = None
        new_session = False
        if self.session_manager:
            history = self.session_manager.get_history()
            new_session = len(history) == 0

            ctx = self.session_manager.get_context_config()
            folder = ctx.get("project_folder", "")
            if folder:
                project_folder = folder

        return self._stream_chat(
            prompt=prompt,
            status_callback=status_callback,
            sink=sink,
            is_main=is_main,
            cancel_event=cancel_event,
            cwd=project_folder,
            new_session=new_session,
        )

    def process_image(
        self,
        prompt: str,
        image_path: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        logger.info("[AntigravityEngine] Image Request started")

        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            return f"Error reading image: {e}"

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/png"

        project_folder = None
        new_session = False
        if self.session_manager:
            history = self.session_manager.get_history()
            new_session = len(history) == 0

            ctx = self.session_manager.get_context_config()
            folder = ctx.get("project_folder", "")
            if folder:
                project_folder = folder

        return self._stream_chat(
            prompt=prompt,
            status_callback=status_callback,
            sink=sink,
            is_main=is_main,
            cancel_event=cancel_event,
            cwd=project_folder,
            new_session=new_session,
            image_base64=image_b64,
            image_mime_type=mime_type,
        )
