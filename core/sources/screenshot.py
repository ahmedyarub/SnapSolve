import os
import tempfile
from PIL import ImageGrab
from .base import Source
from .ocr.base import OCREngine

class ScreenshotSource(Source):
    def __init__(self, ocr_engine: OCREngine = None):
        self.ocr_engine = ocr_engine
        self._temp_files = []

    @property
    def name(self):
        return "image"

    def _capture(self, coords) -> str:
        if not coords or len(coords) != 4:
            raise ValueError("Invalid coordinates. Please run coordinate selection again.")

        bbox = tuple(coords)
        try:
            img = ImageGrab.grab(bbox=bbox)
        except Exception as e:
            raise ValueError(f"Error capturing screen: {str(e)}")

        temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_file_path = temp_file.name
        temp_file.close()

        self._temp_files.append(temp_file_path)
        img.save(temp_file_path)

        return temp_file_path

    def get_text(self, coords=None, status_callback=None, *args, **kwargs) -> str:
        if not self.ocr_engine or self.ocr_engine.__class__.__name__ == "NoOCREngine":
            raise ValueError("ScreenshotSource cannot provide text without an active OCR engine.")

        image_path = self._capture(coords)
        try:
            text = self.ocr_engine.extract_text(image_path, status_callback)
            if not text:
                raise ValueError("OCR engine found no text.")
            return text
        finally:
            self.cleanup_file(image_path)

    def get_image(self, coords=None, *args, **kwargs) -> str:
        return self._capture(coords)

    def cleanup_file(self, filepath):
        if filepath in self._temp_files:
            self._temp_files.remove(filepath)
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    def cleanup_all(self):
        for f in list(self._temp_files):
            self.cleanup_file(f)
