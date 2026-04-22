import json
import time
import urllib.request
import urllib.error
import base64
import threading
from .base import LLMEngine
from core.sinks.base import Sink

class OllamaEngine(LLMEngine):
    def __init__(self, model: str, ollama_url: str, session_manager=None, status_callback=None):
        super().__init__(model, session_manager=session_manager)
        self.ollama_url = ollama_url



    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Ollama (loading model into memory)...")
        try:
            payload = {
                "model": self.model,
                "prompt": "Hello",
                "stream": False
            }
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                _ = response.read()
            if status_callback:
                status_callback("Ollama warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Ollama warmup failed: {str(e)}")
            print(f"Ollama warmup failed: {str(e)}")
            return False


    @property
    def supports_images(self) -> bool:
        return True # Ollama generally supports images if the model does, we let it try.


    def _execute_request(self, payload: dict, sink: Sink, is_main: bool, cancel_event: threading.Event = None) -> str:
        try:
            if cancel_event and cancel_event.is_set():
                return "Cancelled"
                
            print(f"[OllamaEngine] Sending request...")
            req = urllib.request.Request(
                f"{self.ollama_url.rstrip('/')}/api/generate",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req) as response:
                if cancel_event and cancel_event.is_set():
                    return "Cancelled"
                data = json.loads(response.read().decode('utf-8'))
                ans = data.get("response", "").strip()

            if sink and not (cancel_event and cancel_event.is_set()):
                sink.process_chunk(ans, is_main=is_main)
            print(f"Request finished successfully")
            return ans
        except Exception as e:
            print(f"[OllamaEngine] Error calling Ollama API: {str(e)}")
            return f"Error calling Ollama API: {str(e)}"

    def process_text(self, prompt: str, status_callback=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True, cancel_event: threading.Event = None) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"
            
        print(f"[OllamaEngine] Text Request started for model: {self.model} at {self.ollama_url}")
        if status_callback:
            status_callback("Processing text with Ollama...")

        full_prompt = self._prepare_prompt(prompt, enable_stitching)

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        return self._execute_request(payload, sink, is_main, cancel_event)

    def process_image(self, prompt: str, image_path: str, status_callback=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True, cancel_event: threading.Event = None) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"
            
        print(f"[OllamaEngine] Image Request started for model: {self.model} at {self.ollama_url}")
        if status_callback:
            status_callback("Processing image with Ollama...")

        full_prompt = self._prepare_prompt(prompt, enable_stitching)

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                payload["images"] = [encoded_string]
        except Exception as e:
            return f"Error reading image: {str(e)}"

        return self._execute_request(payload, sink, is_main, cancel_event)
