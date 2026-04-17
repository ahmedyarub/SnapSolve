import abc
from core.sinks.base import Sink

class LLMEngine(abc.ABC):
    def __init__(self, model: str):
        self.model = model

    @property
    @abc.abstractmethod
    def supports_images(self) -> bool:
        pass

    @abc.abstractmethod
    def warmup(self, status_callback=None) -> bool:
        """Warms up the engine. Returns True if successful."""
        pass

    @abc.abstractmethod
    def process_text(self, prompt: str, status_callback=None, session_manager=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True) -> str:
        """Processes a text prompt and returns the generated answer."""
        pass

    @abc.abstractmethod
    def process_image(self, prompt: str, image_path: str, status_callback=None, session_manager=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True) -> str:
        """Processes an image with a text prompt and returns the generated answer."""
        pass
