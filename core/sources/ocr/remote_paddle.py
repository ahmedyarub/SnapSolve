import logging
import os
import tempfile
import threading

import httpx
from PIL import Image, ImageDraw

from .base import OCREngine
from .exceptions import OCRCancelledError

logger = logging.getLogger(__name__)


class RemotePaddleOCREngine(OCREngine):
    def __init__(self, config=None, status_callback=None, warmup=False):
        if config is None:
            config = {}
        self.config = config
        protocol = config.get("remote_ocr_protocol", "http")
        host = config.get("remote_ocr_host", "127.0.0.1")
        port = config.get("port", 8000)
        self.url = f"{protocol}://{host}:{port}/ocr"
        if status_callback:
            status_callback("Remote PaddleOCR Engine Initialized")

        if warmup:
            self.warmup(status_callback)

    def warmup(self, status_callback=None):
        if status_callback:
            status_callback("Warming up Remote PaddleOCR...")

        fd, temp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            img = Image.new("RGB", (100, 100), color="white")
            d = ImageDraw.Draw(img)
            d.text((10, 10), "Warmup Text", fill=(0, 0, 0))
            img.save(temp_path)
            self.extract_text(temp_path)
        except Exception as e:
            logger.warning("Remote OCR warmup failed: %s", e)
        finally:
            os.remove(temp_path)
            # Intentionally not deleting the file

    def extract_text(
        self,
        image_path: str,
        status_callback=None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            raise OCRCancelledError("OCR cancelled.")

        logger.debug("Using remote PaddleOCR engine.")
        if status_callback:
            status_callback("Sending to Remote PaddleOCR...")
        try:
            payload = {"file_path": image_path}
            logger.debug("Sending an image to the remote OCR service at %s", self.url)
            with httpx.Client() as client:
                response = client.post(self.url, json=payload, timeout=30.0)
                if cancel_event and cancel_event.is_set():
                    raise OCRCancelledError("OCR cancelled.")
                response.raise_for_status()
                response_data = response.json()
                logger.debug(
                    "Remote OCR returned %d characters",
                    len(response_data.get("text") or ""),
                )
                return response_data.get("text", "")
        except httpx.RequestError as e:
            logger.error("Error requesting OCR from remote service: %s", e)
            return ""
