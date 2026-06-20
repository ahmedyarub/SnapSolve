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

    @property
    def ai_coding_tool(self) -> bool:
        return False

    @abc.abstractmethod
    def warmup(self, status_callback=None) -> bool:
        """Warms up the engine. Returns True if successful."""
        pass

    def is_available(self) -> tuple[bool, str]:
        """Check if this engine's backend service is reachable.

        Returns ``(True, "")`` if available, or
        ``(False, "human-readable error message")`` if not.

        The default implementation assumes the engine is always available.
        Override in subclasses that depend on network services.
        """
        return True, ""

    @abc.abstractmethod
    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
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
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        """Processes an image with a text prompt and returns the generated answer."""
        return "Error: process_image is not implemented for this engine."

    def _prepare_prompt(self, prompt: str, enable_chat_sessions: bool) -> str:
        full_prompt = prompt
        if self.session_manager and enable_chat_sessions:
            history = self.session_manager.get_history()
            
            ctx = self.session_manager.get_context_config()
            include_q = ctx.get("include_previous_questions", True)
            include_a = ctx.get("include_previous_answers", True)
            
            if history and (include_q or include_a):
                history_text = "Previous conversation:\n"
                for h in history:
                    if include_q and "prompt" in h:
                        history_text += f"User: {h.get('prompt', '')}\n"
                    if include_a and "response" in h:
                        history_text += f"Assistant: {h.get('response', '')}\n\n"
                history_text += "Current request:\n"
                full_prompt = history_text + prompt
        return full_prompt
