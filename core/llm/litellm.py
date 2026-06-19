import os
import mimetypes
import base64
import threading

from .base import LLMEngine
from core.sinks.base import Sink


class LiteLLMEngine(LLMEngine):
    def __init__(self, model: str, config: dict, session_manager=None):
        super().__init__(model, session_manager=session_manager)
        self.config = config
        self._set_env_keys()
        print(f"[LiteLLMEngine] Initialized with model: {self.model}")

    def _set_env_keys(self):
        keys = {
            "openai_api_key": "OPENAI_API_KEY",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "groq_api_key": "GROQ_API_KEY",
            "openrouter_api_key": "OPENROUTER_API_KEY",
        }
        for config_key, env_var in keys.items():
            val = self.config.get(config_key, "")
            if val:
                os.environ[env_var] = val

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up LiteLLM engine...")
        try:
            import litellm
            self._set_env_keys()
            if status_callback:
                status_callback("LiteLLM engine warmup complete.")
            return True
        except ImportError:
            if status_callback:
                status_callback("Error: litellm is not installed.")
            return False
        except Exception as e:
            if status_callback:
                status_callback(f"LiteLLM warmup failed: {str(e)}")
            return False

    @property
    def supports_images(self) -> bool:
        return True  # LiteLLM handles image routing for vision-capable models

    def _execute_stream(
        self,
        messages: list,
        sink: Sink,
        is_main: bool,
        cancel_event: threading.Event = None,
    ) -> str:
        try:
            import litellm
            print("[LiteLLMEngine] Calling litellm.completion...")

            response = litellm.completion(
                model=self.model,
                messages=messages,
                stream=True
            )

            ans_chunks = []
            buffer = ""

            for chunk in response:
                if cancel_event and cancel_event.is_set():
                    return "Cancelled"

                chunk_content = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
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

            ans = "".join(ans_chunks)
            print("[LiteLLMEngine] Request finished successfully")
            return ans
        except Exception as e:
            print(f"[LiteLLMEngine] Error during request: {str(e)}")
            return f"Error calling LiteLLM API: {str(e)}"

    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event = None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        if status_callback:
            status_callback(f"Processing with LiteLLM ({self.model})...")

        print(f"[LiteLLMEngine] Text Request started for model: {self.model}")

        try:
            import litellm
        except ImportError:
            return "Error: litellm is not installed. Please install it."

        self._set_env_keys()
        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
        messages = [{"role": "user", "content": full_prompt}]

        return self._execute_stream(messages, sink, is_main, cancel_event)

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
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        if status_callback:
            status_callback(f"Processing image with LiteLLM ({self.model})...")

        print(f"[LiteLLMEngine] Image Request started for model: {self.model}")

        try:
            import litellm
        except ImportError:
            return "Error: litellm is not installed. Please install it."

        self._set_env_keys()
        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)

        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                mime_type, _ = mimetypes.guess_type(image_path)
                if not mime_type:
                    mime_type = "image/png"
        except Exception as e:
            return f"Error reading image: {str(e)}"

        content = [
            {"type": "text", "text": full_prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{encoded_string}"
                }
            }
        ]
        messages = [{"role": "user", "content": content}]

        return self._execute_stream(messages, sink, is_main, cancel_event)
