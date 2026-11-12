"""Claude engine that runs on the user's Claude subscription via the Claude Code CLI.

The ``claude`` CLI is logged in with a claude.ai account (Pro/Max), so requests
made through it are billed to that subscription instead of an API key. Each
request runs ``claude -p`` in headless mode with all tools disabled, so it
behaves as a plain chat model, and streams text deltas back to the sink.
"""

import base64
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from core.sinks.base import Sink

from .base import LLMEngine

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"

# Replaces Claude Code's coding-agent system prompt: this engine only answers.
_SYSTEM_PROMPT = (
    "You are a helpful assistant inside a desktop question-answering app. "
    "Answer the user's request directly. Format answers in Markdown."
)

# Environment variables that would make the CLI bill an API key instead of the
# subscription login. LiteLLMEngine exports ANTHROPIC_API_KEY into os.environ
# when one is configured, so they must be removed for the child process.
_API_KEY_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _subscription_env() -> dict:
    env = os.environ.copy()
    for var in _API_KEY_ENV_VARS:
        env.pop(var, None)
    return env


def _neutral_cwd() -> str:
    """Directory with no CLAUDE.md or project settings for the CLI to pick up."""
    path = os.path.join(tempfile.gettempdir(), "snapsolve_claude")
    os.makedirs(path, exist_ok=True)
    return path


class ClaudeCodeEngine(LLMEngine):
    def __init__(self, model: str, config: dict | None = None, session_manager=None):
        super().__init__(model or DEFAULT_CLAUDE_MODEL, session_manager=session_manager)
        self.cli_path = (config or {}).get("claude_cli_path", "claude")
        print(f"[ClaudeCodeEngine] Initialized with model: {self.model}")

    @property
    def supports_images(self) -> bool:
        return True

    def _resolve_cli(self) -> str | None:
        return shutil.which(self.cli_path)

    def is_available(self) -> tuple[bool, str]:
        if self._resolve_cli():
            return True, ""
        return False, (
            f"Could not find the Claude Code CLI ('{self.cli_path}') in PATH. "
            "Install it and run 'claude' once to log in with your Claude subscription."
        )

    def warmup(self, status_callback=None) -> bool:
        """Checks that the CLI is installed and logged in with a claude.ai account.

        No prompt is sent, so warmup does not use subscription quota.
        """
        if status_callback:
            status_callback("Checking Claude subscription login...")
        cli = self._resolve_cli()
        if not cli:
            if status_callback:
                status_callback(self.is_available()[1])
            return False
        try:
            proc = subprocess.run(
                [cli, "auth", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=_subscription_env(),
                cwd=_neutral_cwd(),
                timeout=30,
                creationflags=_no_window_flag(),
            )
            status = json.loads(proc.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            if status_callback:
                status_callback(f"Claude login check failed: {e}")
            return False

        ok = bool(status.get("loggedIn")) and status.get("authMethod") == "claude.ai"
        if status_callback:
            if ok:
                plan = status.get("subscriptionType", "unknown")
                status_callback(f"Claude subscription login OK ({plan}).")
            else:
                status_callback(
                    "Claude CLI is not logged in with a claude.ai subscription. Run 'claude' to log in."
                )
        return ok

    def _build_command(self, cli: str) -> list[str]:
        return [
            cli,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--model",
            self.model,
            "--system-prompt",
            _SYSTEM_PROMPT,
            "--tools",
            "",
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--strict-mcp-config",
        ]

    def _run(
        self,
        content: list[dict],
        status_callback,
        sink: Sink,
        is_main: bool,
        cancel_event: threading.Event | None,
    ) -> str:
        if cancel_event and cancel_event.is_set():
            return "Cancelled"

        cli = self._resolve_cli()
        if not cli:
            return f"Error: {self.is_available()[1]}"

        if status_callback:
            status_callback("Processing with Claude...")

        user_message = {"type": "user", "message": {"role": "user", "content": content}}

        try:
            process = subprocess.Popen(
                self._build_command(cli),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=_subscription_env(),
                cwd=_neutral_cwd(),
                creationflags=_no_window_flag(),
            )
        except OSError as e:
            return f"Error starting Claude CLI: {e}"

        stderr_lines: list[str] = []
        stderr_thread = threading.Thread(
            target=lambda: stderr_lines.extend(process.stderr), daemon=True
        )
        stderr_thread.start()

        finished = threading.Event()
        if cancel_event:

            def _kill_on_cancel():
                while not finished.wait(0.1):
                    if cancel_event.is_set():
                        process.kill()
                        return

            threading.Thread(target=_kill_on_cancel, daemon=True).start()

        try:
            process.stdin.write(json.dumps(user_message) + "\n")
            process.stdin.close()
            answer, error = self._consume_stream(
                process.stdout, sink, is_main, cancel_event
            )
            process.wait()
        except OSError as e:
            process.kill()
            return f"Error communicating with Claude CLI: {e}"
        finally:
            finished.set()

        stderr_thread.join(timeout=1)

        if cancel_event and cancel_event.is_set():
            return "Cancelled"
        if error:
            return f"Error from Claude: {error}"
        if process.returncode != 0:
            detail = "".join(stderr_lines).strip() or f"exit code {process.returncode}"
            return f"Error from Claude CLI: {detail}"
        return answer

    @staticmethod
    def _consume_stream(
        stdout, sink: Sink, is_main: bool, cancel_event
    ) -> tuple[str, str | None]:
        """Reads stream-json events, forwarding whole lines of text to the sink.

        Returns ``(answer, error)``.
        """
        chunks: list[str] = []
        buffer = ""
        result_text = ""
        error = None

        def emit(piece: str):
            if sink and piece and not (cancel_event and cancel_event.is_set()):
                sink.process_chunk(piece, is_main=is_main)

        for line in stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = event.get("type")
            if kind == "stream_event":
                inner = event.get("event", {})
                delta = inner.get("delta", {})
                if (
                    inner.get("type") == "content_block_delta"
                    and delta.get("type") == "text_delta"
                ):
                    text = delta.get("text", "")
                    chunks.append(text)
                    buffer += text
                    if "\n" in buffer:
                        cut = buffer.rindex("\n") + 1
                        emit(buffer[:cut])
                        buffer = buffer[cut:]
            elif kind == "result":
                result_text = event.get("result") or ""
                if event.get("is_error"):
                    error = result_text or event.get("subtype", "unknown error")

        emit(buffer)

        answer = "".join(chunks)
        if not answer and result_text and not error:
            # No partial messages arrived; fall back to the final result.
            answer = result_text
            emit(answer)
        return answer.strip(), error

    def process_text(
        self,
        prompt: str,
        status_callback=None,
        enable_chat_sessions=True,
        sink: Sink = None,
        is_main: bool = True,
        cancel_event: threading.Event | None = None,
    ) -> str:
        print(f"[ClaudeCodeEngine] Text Request started for model: {self.model}")
        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
        content = [{"type": "text", "text": full_prompt}]
        return self._run(content, status_callback, sink, is_main, cancel_event)

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
        print(f"[ClaudeCodeEngine] Image Request started for model: {self.model}")
        try:
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("ascii")
        except OSError as e:
            return f"Error reading image for Claude: {e}"

        media_type, _ = mimetypes.guess_type(image_path)
        full_prompt = self._prepare_prompt(prompt, enable_chat_sessions)
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type or "image/png",
                    "data": image_data,
                },
            },
            {"type": "text", "text": full_prompt},
        ]
        return self._run(content, status_callback, sink, is_main, cancel_event)


def _no_window_flag() -> int:
    """Keeps the CLI from opening a console window when the app runs without one."""
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
