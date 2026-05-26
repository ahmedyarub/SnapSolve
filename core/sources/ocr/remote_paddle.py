import tempfile
import httpx
import threading
from PIL import Image, ImageDraw

from .base import OCREngine
from .exceptions import OCRCancelledError


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

        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            img = Image.new("RGB", (100, 100), color="white")
            d = ImageDraw.Draw(img)
            d.text((10, 10), "Warmup Text", fill=(0, 0, 0))
            img.save(temp_file.name)
            self.extract_text(temp_file.name)
        except Exception as e:
            print(f"Warmup failed: {e}")
        finally:
            temp_file.close()
            # Intentionally not deleting the file

    def extract_text(
        self,
        image_path: str,
        status_callback=None,
        cancel_event: threading.Event = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            raise OCRCancelledError("OCR cancelled.")

        print("Using remote PaddleOCR engine.")
        if status_callback:
            status_callback("Sending to Remote PaddleOCR...")
        try:
            payload = {"file_path": image_path}
            print(f"Sending payload to remote OCR: {payload}")
            with httpx.Client() as client:
                response = client.post(self.url, json=payload, timeout=30.0)
                if cancel_event and cancel_event.is_set():
                    raise OCRCancelledError("OCR cancelled.")
                response.raise_for_status()
                response_data = response.json()
                print(f"Received response from remote OCR: {response_data}")
                return response_data.get("text", "")
        except httpx.RequestError as e:
            print(f"Error requesting OCR from remote service: {e}")
            return ""
