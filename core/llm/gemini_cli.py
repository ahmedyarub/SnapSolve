import json
import logging
import os
import shutil
import subprocess
import threading

from core.sinks.base import Sink

from .base import LLMEngine

logger = logging.getLogger(__name__)


def _execute_request(
    cmd_args: list,
    status_callback,
    sink: Sink,
    is_main: bool,
    cancel_event: threading.Event | None = None,
) -> str:
    if cancel_event and cancel_event.is_set():
        return "Cancelled"

    # The command line holds the prompt; log only that a request is made.
    logger.info("Running the Gemini CLI")

    if status_callback:
        status_callback("Processing with Gemini CLI...")

    try:
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        # communicate() keeps draining both pipes (a long answer would otherwise
        # fill one and hang the CLI); the short timeout lets us check for cancel.
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancel_event and cancel_event.is_set():
                    process.kill()
                    process.communicate()
                    return "Cancelled"
        if process.returncode != 0:
            return f"CLI Error: {stderr}"

        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        data = json.loads(stdout)
        ans = data.get("response", "").strip()

        if sink and not (cancel_event and cancel_event.is_set()):
            sink.process_chunk(ans, is_main=is_main)

        return ans
    except subprocess.CalledProcessError as e:
        return f"CLI Error: {e.stderr}"
    except Exception as e:
        return f"Error executing CLI: {e!s}"


class GeminiCLIEngine(LLMEngine):
    def __init__(self, model: str, session_manager=None):
        super().__init__(model, session_manager=session_manager)

    def warmup(self, status_callback=None) -> bool:
        if status_callback:
            status_callback("Warming up Gemini CLI...")
        try:
            # noinspection PyDeprecation
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
                status_callback(f"Gemini CLI warmup failed: {e!s}")
            return False

    @property
    def supports_images(self) -> bool:
        return True

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

        logger.info("Gemini CLI text request: %s", self.model)

        # noinspection PyDeprecation
        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
        combined_prompt = f'"{full_prompt}"'

        cmd_args = [gemini_cmd, "-p", combined_prompt, "-o", "json", "-m", self.model]

        return _execute_request(cmd_args, status_callback, sink, is_main, cancel_event)

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

        logger.info("Gemini CLI image request: %s", self.model)

        # noinspection PyDeprecation
        gemini_cmd = shutil.which("gemini")
        if not gemini_cmd:
            return "Error: Could not find 'gemini' executable in PATH."

        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
        combined_prompt = f'"{full_prompt} @{image_path}"'

        temp_dir = os.path.dirname(image_path)
        if not temp_dir.endswith(os.sep):
            temp_dir += os.sep
        include_dir_arg = f"{temp_dir}"

        cmd_args = [
            gemini_cmd,
            "-p",
            combined_prompt,
            "-o",
            "json",
            "--include-directories",
            include_dir_arg,
            "-m",
            self.model,
        ]

        return _execute_request(cmd_args, status_callback, sink, is_main, cancel_event)
