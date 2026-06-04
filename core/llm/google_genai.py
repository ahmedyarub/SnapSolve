import mimetypes
import threading

from core.sinks.base import Sink
from .base import LLMEngine


class GoogleGenAIEngine(LLMEngine):
    def __init__(self, model: str, api_key: str, session_manager=None):
        super().__init__(model, session_manager=session_manager)
        self.api_key = api_key
        print(f"[GoogleGenAIEngine] Initialized with model: {self.model}")

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Google GenAI...")
        if not self.api_key:
            return False
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            contents = [
                types.Content(role="user", parts=[types.Part.from_text(text="Hello")])
            ]
            response_stream = client.models.generate_content_stream(
                model=self.model, contents=contents
            )
            for _ in response_stream:
                pass  # Just consume it
            if status_callback:
                status_callback("Google GenAI warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Google GenAI warmup failed: {str(e)}")
            return False

    @property
    def supports_images(self) -> bool:
        return True



    @staticmethod
    def _check_cancelled(cancel_event: threading.Event):
        """Check if operation is cancelled."""
        return cancel_event and cancel_event.is_set()

    @staticmethod
    def _process_stream_chunk(chunk, _sink, _is_main, _cancel_event):
        """Process stream chunk."""
        if chunk.text is None:
            return None

        return chunk.text

    def _process_buffer_lines(self, buffer, sink, is_main, cancel_event):
        """Process buffer lines."""
        if "\n" not in buffer:
            return buffer

        last_newline_idx = buffer.rindex("\n")
        complete_lines = buffer[: last_newline_idx + 1]
        remaining_buffer = buffer[last_newline_idx + 1 :]

        if sink and not self._check_cancelled(cancel_event):
            sink.process_chunk(complete_lines, is_main=is_main)

        return remaining_buffer

    def _process_remaining_buffer(self, buffer, sink, is_main, cancel_event):
        """Process remaining buffer."""
        if buffer and sink and not self._check_cancelled(cancel_event):
            sink.process_chunk(buffer, is_main=is_main)

    def _execute_stream(
        self,
        client,
        contents,
        sink: Sink,
        is_main: bool,
        cancel_event: threading.Event = None,
    ) -> str:
        if self._check_cancelled(cancel_event):
            return "Cancelled"

        print("[GoogleGenAIEngine] Calling generate_content_stream...")
        response_stream = client.models.generate_content_stream(
            model=self.model,
            contents=contents,
        )

        print("[GoogleGenAIEngine] Stream started, waiting for chunks...")
        ans_chunks = []
        buffer = ""
        for i, chunk in enumerate(response_stream):
            if self._check_cancelled(cancel_event):
                return "Cancelled"

            print(f"[GoogleGenAIEngine] Received chunk {i}: {repr(chunk.text)}")

            chunk_text = self._process_stream_chunk(chunk, sink, is_main, cancel_event)
            if chunk_text is None:
                continue

            ans_chunks.append(chunk_text)
            buffer += chunk_text
            buffer = self._process_buffer_lines(buffer, sink, is_main, cancel_event)

        self._process_remaining_buffer(buffer, sink, is_main, cancel_event)

        if self._check_cancelled(cancel_event):
            return "Cancelled"

        ans = "".join(ans_chunks)
        print("Request finished successfully")
        return ans

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
            status_callback("Processing with Google GenAI...")

        print(f"[GoogleGenAIEngine] Text Request started for model: {self.model}")

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return "Error: google-genai is not installed. Please install it to use the 'google-genai' engine."

        if not self.api_key:
            return "Error: Google GenAI API key is missing. Please add it to your configuration."

        try:
            client = genai.Client(api_key=self.api_key)
            
            full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
            
            current_parts = [types.Part.from_text(text=full_prompt)]
            contents = [types.Content(role="user", parts=current_parts)]

            assert sink is not None
            return self._execute_stream(client, contents, sink, is_main, cancel_event)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"

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
            status_callback("Processing with Google GenAI...")

        print(f"[GoogleGenAIEngine] Image Request started for model: {self.model}")

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return "Error: google-genai is not installed. Please install it to use the 'google-genai' engine."

        if not self.api_key:
            return "Error: Google GenAI API key is missing. Please add it to your configuration."

        try:
            client = genai.Client(api_key=self.api_key)
            
            full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
            
            current_parts = [types.Part.from_text(text=full_prompt)]

            print(f"[GoogleGenAIEngine] Loading image from {image_path}...")
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = "image/png"

            current_parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                )
            )

            contents = [types.Content(role="user", parts=current_parts)]

            assert sink is not None
            return self._execute_stream(client, contents, sink, is_main, cancel_event)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"
