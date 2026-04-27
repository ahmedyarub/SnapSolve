import abc
import threading

from core.sinks.base import Sink


class LLMEngine(abc.ABC):
    def __init__(self, model: str, session_manager=None):
        self.session_manager = session_manager
        self.model = model

    @property
    @abc.abstractmethod
    def supports_images(self) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def warmup(self, status_callback=None) -> bool:
        """Warms up the engine. Returns True if successful."""
        pass

    @abc.abstractmethod
    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_stitching=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        """Processes a text prompt and returns the generated answer."""
        return "Error: process_text is not implemented for this engine."

    @abc.abstractmethod
    def process_image(
        self,
        prompt: str,
        image_path: str,
        status_callback=None,
        enable_stitching=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        """Processes an image with a text prompt and returns the generated answer."""
        return "Error: process_image is not implemented for this engine."

    def _prepare_prompt(self, prompt: str, enable_stitching: bool) -> str:
        full_prompt = prompt
        if self.session_manager and enable_stitching:
            history = self.session_manager.get_history()
            if history:
                history_text = "Previous conversation:\n"
                for h in history:
                    history_text += f"User: {h.get('prompt', '')}\n"
                    history_text += f"Assistant: {h.get('response', '')}\n\n"
                history_text += "Current request:\n"
                full_prompt = history_text + prompt
        return full_prompt
