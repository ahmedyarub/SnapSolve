import json
import os
import shutil
import subprocess
import time
from .base import LLMEngine
from core.sinks.base import Sink

class GeminiCLIEngine(LLMEngine):
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

    def _prepare_prompt(self, prompt: str, session_manager, enable_stitching: bool) -> str:
        full_prompt = prompt
        if session_manager and enable_stitching:
            history = session_manager.get_history()
            if history:
                history_text = "Previous conversation:\n"
                for h in history:
                    history_text += f"User: {h.get('prompt', '')}\n"
                    history_text += f"Assistant: {h.get('response', '')}\n\n"
                history_text += "Current request:\n"
                full_prompt = history_text + prompt
        return full_prompt

    def process_text(self, prompt: str, status_callback=None, session_manager=None, enable_stitching=True,
                     sink: Sink = None, is_main: bool = True) -> str:
        print(f"[GeminiCLIEngine] Text Request started for model: {self.model}")
        start_time = time.time()

        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, session_manager, enable_stitching)
        combined_prompt = f'"{full_prompt}"'

        cmd_args = [
            gemini_cmd,
            "-p", combined_prompt,
            "-o", "json",
            "-m", self.model
        ]

        return self._execute_request(cmd_args, status_callback, sink, is_main, start_time)

    def process_image(self, prompt: str, image_path: str, status_callback=None, session_manager=None, enable_stitching=True,
                      sink: Sink = None, is_main: bool = True) -> str:
        print(f"[GeminiCLIEngine] Image Request started for model: {self.model}")
        start_time = time.time()

        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, session_manager, enable_stitching)
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

        return self._execute_request(cmd_args, status_callback, sink, is_main, start_time)

    def _execute_request(self, cmd_args: list, status_callback, sink: Sink, is_main: bool, start_time: float) -> str:
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
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"Processing took {elapsed_ms:.2f} ms")

            data = json.loads(result.stdout)
            ans = data.get("response", "").strip()

            if sink:
                sink.process_chunk(ans, is_main=is_main)

            return ans
        except subprocess.CalledProcessError as e:
            return f"CLI Error: {e.stderr}"
