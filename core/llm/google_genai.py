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
            contents = [types.Content(role="user", parts=[types.Part.from_text(text="Hello")])]
            response_stream = client.models.generate_content_stream(model=self.model, contents=contents)
            for chunk in response_stream:
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

    def _prepare_contents(self, prompt: str, enable_stitching: bool, types):
        contents = []

        if self.session_manager and enable_stitching:
            history = self.session_manager.get_history()
            for h in history:
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=h.get('prompt', ''))]
                ))
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=h.get('response', ''))]
                ))

        return contents

    def _execute_stream(self, client, contents, sink: Sink, is_main: bool, cancel_event: threading.Event = None) -> str:
        if cancel_event and cancel_event.is_set():
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
            if cancel_event and cancel_event.is_set():
                return "Cancelled"

            print(f"[GoogleGenAIEngine] Received chunk {i}: {repr(chunk.text)}")

            if chunk.text is None:
                continue

            ans_chunks.append(chunk.text)
            buffer += chunk.text
            if "\n" in buffer:
                last_newline_idx = buffer.rindex("\n")
                complete_lines = buffer[:last_newline_idx + 1]
                buffer = buffer[last_newline_idx + 1:]
                if sink and not (cancel_event and cancel_event.is_set()):
                    sink.process_chunk(complete_lines, is_main=is_main)

        if buffer and sink and not (cancel_event and cancel_event.is_set()):
            sink.process_chunk(buffer, is_main=is_main)

        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        ans = "".join(ans_chunks)
        print(f"Request finished successfully")
        return ans

    def process_text(self, prompt: str, status_callback=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True, cancel_event: threading.Event = None) -> str:
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
            contents = self._prepare_contents(prompt, enable_stitching, types)

            current_parts = [types.Part.from_text(text=prompt)]
            contents.append(types.Content(role="user", parts=current_parts))

            assert sink is not None
            return self._execute_stream(client, contents, sink, is_main, cancel_event)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"

    def process_image(self, prompt: str, image_path: str, status_callback=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True, cancel_event: threading.Event = None) -> str:
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
            contents = self._prepare_contents(prompt, enable_stitching, types)

            current_parts = [types.Part.from_text(text=prompt)]

            print(f"[GoogleGenAIEngine] Loading image from {image_path}...")
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type:
                mime_type = 'image/png'

            current_parts.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                )
            )

            contents.append(types.Content(role="user", parts=current_parts))

            assert sink is not None
            return self._execute_stream(client, contents, sink, is_main, cancel_event)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"
