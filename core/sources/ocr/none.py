from .base import OCREngine

class NoOCREngine(OCREngine):
    def extract_text(self, image_path: str, status_callback=None) -> str:
        return None
