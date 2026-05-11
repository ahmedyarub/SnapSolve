import tempfile
import threading

from PIL import ImageGrab

from .base import ImageSource
from .ocr.base import OCREngine

CAPTURE_CANCELLED_MSG = "Capture cancelled."


class ScreenshotSource(ImageSource):
    def __init__(self, ocr_engine: OCREngine = None):
        self.ocr_engine = ocr_engine
        self._temp_files = []

    def _capture(self, coords, cancel_event: threading.Event = None) -> str:
        if cancel_event and cancel_event.is_set():
            raise ValueError(CAPTURE_CANCELLED_MSG)

        if not coords or len(coords) != 4:
            raise ValueError(
                "Invalid coordinates. Please run coordinate selection again."
            )

        bbox = tuple(coords)
        try:
            img = ImageGrab.grab(bbox=bbox)
        except Exception as e:
            raise ValueError(f"Error capturing screen: {str(e)}")

        if cancel_event and cancel_event.is_set():
            raise ValueError(CAPTURE_CANCELLED_MSG)

        temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        temp_file_path = temp_file.name
        temp_file.close()

        self._temp_files.append(temp_file_path)
        img.save(temp_file_path)

        return temp_file_path

    def get_text(
        self,
        coords=None,
        status_callback=None,
        cancel_event: threading.Event = None,
        *args,
        **kwargs,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            raise ValueError(CAPTURE_CANCELLED_MSG)

        if not self.ocr_engine or self.ocr_engine.__class__.__name__ == "NoOCREngine":
            raise ValueError(
                "ScreenshotSource cannot provide text without an active OCR engine."
            )

        image_path = self._capture(coords, cancel_event)

        if cancel_event and cancel_event.is_set():
            raise ValueError(CAPTURE_CANCELLED_MSG)

        if (
            hasattr(self.ocr_engine, "extract_text")
            and "cancel_event" in self.ocr_engine.extract_text.__code__.co_varnames
        ):
            text = self.ocr_engine.extract_text(
                image_path, status_callback, cancel_event
            )
        else:
            text = self.ocr_engine.extract_text(image_path, status_callback)
        if not text:
            raise ValueError("OCR engine found no text.")
        return text

    def get_image(
        self, coords=None, cancel_event: threading.Event = None, *args, **kwargs
    ) -> str:
        return self._capture(coords, cancel_event)

    def cleanup_file(self, filepath):
        if filepath in self._temp_files:
            self._temp_files.remove(filepath)
        # Intentionally not deleting the file as requested

    def cleanup_all(self):
        for f in list(self._temp_files):
            self.cleanup_file(f)
