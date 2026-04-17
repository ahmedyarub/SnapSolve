import json
import os
import shutil
import subprocess
import time
from .base import LLMEngine
from core.sinks.base import Sink

class GeminiCLIEngine(LLMEngine):
    def __init__(self, model: str, session_manager=None):
        super().__init__(model, session_manager=session_manager)

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Gemini CLI...")
        try:
            gemini_cmd = shutil.which("gemini")
            if not gemini_cmd:
                return False
            cmd_args = [gemini_cmd, "-p", '"Hello"', "-o", "json", "-m", self.model]
            subprocess.run(cmd_args, capture_output=True, text=True, check=True)
            if status_callback:
                status_callback("Gemini CLI warmup complete.")
            return True
        except Exception as e:
            if status_callback:
                status_callback(f"Gemini CLI warmup failed: {str(e)}")
            return False


    @property
    def supports_images(self) -> bool:
        return True


    def process_text(self, prompt: str, status_callback=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True) -> str:
        print(f"[GeminiCLIEngine] Text Request started for model: {self.model}")

        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, enable_stitching)
        combined_prompt = f'"{full_prompt}"'

        cmd_args = [
            gemini_cmd,
            "-p", combined_prompt,
            "-o", "json",
            "-m", self.model
        ]

        return self._execute_request(cmd_args, status_callback, sink, is_main)

    def process_image(self, prompt: str, image_path: str, status_callback=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True) -> str:
        print(f"[GeminiCLIEngine] Image Request started for model: {self.model}")

        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, enable_stitching)
        combined_prompt = f'"{full_prompt} @{image_path}"'

        temp_dir = os.path.dirname(image_path)
        if not temp_dir.endswith(os.sep):
            temp_dir += os.sep
        include_dir_arg = f'{temp_dir}'

        cmd_args = [
            gemini_cmd,
            "-p", combined_prompt,
            "-o", "json",
            "--include-directories", include_dir_arg,
            "-m", self.model
        ]

        return self._execute_request(cmd_args, status_callback, sink, is_main)

    def _execute_request(self, cmd_args: list, status_callback, sink: Sink, is_main: bool) -> str:
        print(f"Executing command: {' '.join(cmd_args)}")

        if status_callback:
            status_callback("Processing with Gemini CLI...")

        try:
            result = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                check=True
            )
            print("Processing command complete.")

            data = json.loads(result.stdout)
            ans = data.get("response", "").strip()

            if sink:
                sink.process_chunk(ans, is_main=is_main)

            return ans
        except subprocess.CalledProcessError as e:
            return f"CLI Error: {e.stderr}"
