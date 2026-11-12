import abc
import threading

from core.llm.errors import LLMError, is_error_text
from core.sinks.base import Sink

# Chat history sent with each request. Older turns are dropped first.
DEFAULT_HISTORY_MAX_TURNS = 10
DEFAULT_HISTORY_MAX_CHARS = 24_000

CANCELLED = "Cancelled"


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
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Processes a text prompt and returns the generated answer."""

    @abc.abstractmethod
    def process_image(
        self,
        prompt: str,
        image_path: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Processes an image with a text prompt and returns the generated answer."""

    def generate(
        self,
        prompt: str,
        image_path: str | None = None,
        status_callback=None,
        enable_chat_sessions: bool = True,
        sink: Sink | None = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """The answer to ``prompt`` (with the image, if any).

        Raises :class:`LLMError` on failure, including failures an engine
        reports as an ``"Error..."`` string. Returns ``"Cancelled"`` when
        ``cancel_event`` stopped the call.
        """
        try:
            if image_path:
                result = self.process_image(
                    prompt,
                    image_path,
                    status_callback,
                    enable_chat_sessions,
                    sink,
                    is_main=is_main,
                    cancel_event=cancel_event,
                )
            else:
                result = self.process_text(
                    prompt,
                    status_callback,
                    enable_chat_sessions,
                    sink,
                    is_main=is_main,
                    cancel_event=cancel_event,
                )
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"{type(self).__name__}: {e}") from e
        if is_error_text(result):
            raise LLMError(result)
        return result

    # ------------------------------------------------------------------ #
    #  Chat history
    # ------------------------------------------------------------------ #

    def _history_limits(self) -> tuple[int, int]:
        config = getattr(self.session_manager, "config", None) or {}
        return (
            int(config.get("history_max_turns", DEFAULT_HISTORY_MAX_TURNS)),
            int(config.get("history_max_chars", DEFAULT_HISTORY_MAX_CHARS)),
        )

    def history_turns(self, enable_chat_sessions: bool) -> list[tuple[str, str]]:
        """Recent ``(user, assistant)`` pairs to send, oldest first.

        Honours the session's context settings (include questions / answers)
        and the ``history_max_turns`` / ``history_max_chars`` limits.
        """
        if not (self.session_manager and enable_chat_sessions):
            return []
        context = self.session_manager.get_context_config()
        include_q = context.get("include_previous_questions", True)
        include_a = context.get("include_previous_answers", True)
        if not (include_q or include_a):
            return []

        max_turns, max_chars = self._history_limits()
        turns: list[tuple[str, str]] = []
        used = 0
        for h in reversed(self.session_manager.get_history()):
            if len(turns) >= max_turns:
                break
            user = (h.get("prompt") or "") if include_q else ""
            assistant = (h.get("response") or "") if include_a else ""
            if not (user or assistant):
                continue
            used += len(user) + len(assistant)
            if used > max_chars and turns:
                break
            turns.append((user, assistant))
        turns.reverse()
        return turns

    def history_messages(self, enable_chat_sessions: bool) -> list[dict[str, str]]:
        """The history as chat messages (``role``: ``user`` / ``assistant``)."""
        messages = []
        for user, assistant in self.history_turns(enable_chat_sessions):
            if user:
                messages.append({"role": "user", "content": user})
            if assistant:
                messages.append({"role": "assistant", "content": assistant})
        return messages

    def _prepare_prompt(self, prompt: str, enable_chat_sessions: bool) -> str:
        """The prompt with the history written in front, for single-prompt engines."""
        turns = self.history_turns(enable_chat_sessions)
        if not turns:
            return prompt
        history_text = "Previous conversation:\n"
        for user, assistant in turns:
            if user:
                history_text += f"User: {user}\n"
            if assistant:
                history_text += f"Assistant: {assistant}\n\n"
        return history_text + "Current request:\n" + prompt


__all__ = ["CANCELLED", "LLMEngine", "LLMError"]
