import base64
import mimetypes
import threading

from core.sinks.base import Sink

from .base import LLMEngine

# Model prefix -> config key. Keys go with each request rather than into
# os.environ, where every library and child process would see them.
_KEY_FOR_PROVIDER = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
}


class LiteLLMEngine(LLMEngine):
    def __init__(self, model: str, config: dict, session_manager=None):
        super().__init__(model, session_manager=session_manager)
        self.config = config

    def _api_key(self) -> str | None:
        provider = self.model.split("/", 1)[0] if "/" in self.model else "openai"
        key = self.config.get(_KEY_FOR_PROVIDER.get(provider, ""), "")
        return key or None  # None lets LiteLLM fall back to its own env lookup

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up LiteLLM engine...")
        try:
            import litellm  # noqa: F401  (availability check)

            if status_callback:
                status_callback("LiteLLM engine warmup complete.")
            return True
        except ImportError:
            if status_callback:
                status_callback("Error: litellm is not installed.")
            return False
        except Exception as e:
            if status_callback:
                status_callback(f"LiteLLM warmup failed: {e!s}")
            return False

    @property
    def supports_images(self) -> bool:
        return True  # LiteLLM handles image routing for vision-capable models

    def _execute_stream(
        self,
        messages: list,
        sink: Sink,
        is_main: bool,
        cancel_event: threading.Event | None = None,
    ) -> str:
        try:
            import litellm

            response = litellm.completion(
                model=self.model,
                messages=messages,
                stream=True,
                api_key=self._api_key(),
                timeout=float(self.config.get("llm_request_timeout", 600)),
            )

            ans_chunks = []
            buffer = ""

            for chunk in response:
                if cancel_event and cancel_event.is_set():
                    return "Cancelled"

                chunk_content = (
                    chunk.choices[0].delta.content
                    if chunk.choices and chunk.choices[0].delta
                    else None
                )
                if not chunk_content:
                    continue

                ans_chunks.append(chunk_content)
                buffer += chunk_content

                if "\n" in buffer:
                    last_newline_idx = buffer.rindex("\n")
                    complete_lines = buffer[: last_newline_idx + 1]
                    remaining_buffer = buffer[last_newline_idx + 1 :]

                    if sink and not (cancel_event and cancel_event.is_set()):
                        sink.process_chunk(complete_lines, is_main=is_main)

                    buffer = remaining_buffer

            if buffer and sink and not (cancel_event and cancel_event.is_set()):
                sink.process_chunk(buffer, is_main=is_main)

            return "".join(ans_chunks)
        except Exception as e:
            return f"Error calling LiteLLM API: {e!s}"

    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        if status_callback:
            status_callback(f"Processing with LiteLLM ({self.model})...")

        try:
            import litellm  # noqa: F401  (availability check)
        except ImportError:
            return "Error: litellm is not installed. Please install it."

        messages = self.history_messages(enable_chat_sessions)
        messages.append({"role": "user", "content": prompt})

        return self._execute_stream(messages, sink, is_main, cancel_event)

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
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        if status_callback:
            status_callback(f"Processing image with LiteLLM ({self.model})...")

        try:
            import litellm  # noqa: F401  (availability check)
        except ImportError:
            return "Error: litellm is not installed. Please install it."

        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type:
                    mime_type = "image/png"
        except Exception as e:
            return f"Error reading image: {e!s}"

        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded_string}"},
            },
        ]
        messages = self.history_messages(enable_chat_sessions)
        messages.append({"role": "user", "content": content})

        return self._execute_stream(messages, sink, is_main, cancel_event)
