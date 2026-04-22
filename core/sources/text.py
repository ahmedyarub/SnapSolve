from .base import Source
import threading

class TextSource(Source):
    @property
    def name(self):
        return "text"

    def get_text(self, text: str = None, cancel_event: threading.Event = None, *args, **kwargs) -> str:
        if cancel_event and cancel_event.is_set():
            raise ValueError("Cancelled.")
        if not text:
            raise ValueError("No text provided to TextSource.")
        return text

    def get_image(self, *args, **kwargs) -> str:
        raise ValueError("TextSource cannot provide an image.")
