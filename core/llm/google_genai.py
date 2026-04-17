import time
import mimetypes
from .base import LLMEngine
from core.sinks.base import Sink

class GoogleGenAIEngine(LLMEngine):
    def __init__(self, model: str, api_key: str):
        super().__init__(model)
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
                pass # Just consume it
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

    def _prepare_contents(self, prompt: str, session_manager, enable_stitching: bool, types):
        contents = []

        if session_manager and enable_stitching:
            history = session_manager.get_history()
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

    def _execute_stream(self, client, contents, sink: Sink, is_main: bool, start_time: float) -> str:
        print("[GoogleGenAIEngine] Calling generate_content_stream...")
        response_stream = client.models.generate_content_stream(
            model=self.model,
            contents=contents,
        )

        print("[GoogleGenAIEngine] Stream started, waiting for chunks...")
        ans_chunks = []
        buffer = ""
        for i, chunk in enumerate(response_stream):
            print(f"[GoogleGenAIEngine] Received chunk {i}: {repr(chunk.text)}")
            ans_chunks.append(chunk.text)
            buffer += chunk.text
            if "\n" in buffer:
                last_newline_idx = buffer.rindex("\n")
                complete_lines = buffer[:last_newline_idx + 1]
                buffer = buffer[last_newline_idx + 1:]
                if sink:
                    sink.process_chunk(complete_lines, is_main=is_main)

        if buffer and sink:
            sink.process_chunk(buffer, is_main=is_main)

        ans = "".join(ans_chunks)

        elapsed_ms = (time.time() - start_time) * 1000
        print(f"[GoogleGenAIEngine] Request finished successfully in {elapsed_ms:.2f} ms")
        return ans

    def process_text(self, prompt: str, status_callback=None, session_manager=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True) -> str:
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

        start_time = time.time()

        try:
            client = genai.Client(api_key=self.api_key)
            contents = self._prepare_contents(prompt, session_manager, enable_stitching, types)

            current_parts = [types.Part.from_text(text=prompt)]
            contents.append(types.Content(role="user", parts=current_parts))

            return self._execute_stream(client, contents, sink, is_main, start_time)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"

    def process_image(self, prompt: str, image_path: str, status_callback=None, session_manager=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True) -> str:
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

        start_time = time.time()

        try:
            client = genai.Client(api_key=self.api_key)
            contents = self._prepare_contents(prompt, session_manager, enable_stitching, types)

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

            return self._execute_stream(client, contents, sink, is_main, start_time)
        except Exception as e:
            print(f"[GoogleGenAIEngine] Error during request: {str(e)}")
            return f"Error calling Google GenAI API: {str(e)}"
