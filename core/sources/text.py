from .base import Source

class TextSource(Source):
    @property
    def name(self):
        return "text"

    def get_text(self, text: str = None, *args, **kwargs) -> str:
        if not text:
            raise ValueError("No text provided to TextSource.")
        return text

    def get_image(self, *args, **kwargs) -> str:
        raise ValueError("TextSource cannot provide an image.")
