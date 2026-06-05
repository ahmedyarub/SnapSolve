"""IDE integration helpers — language maps, code-to-IDE opening, and custom web page."""
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import QUrl
from PyQt6.QtWebEngineCore import QWebEnginePage

from core.ui.signals import _last_user_prompt


# --- Language → file extension mapping for temp files ---
_LANG_EXTENSIONS: dict[str, str] = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "java": ".java",
    "c": ".c", "cpp": ".cpp", "c++": ".cpp",
    "csharp": ".cs", "cs": ".cs",
    "go": ".go",
    "rust": ".rs", "rs": ".rs",
    "kotlin": ".kt", "kt": ".kt",
    "swift": ".swift",
    "ruby": ".rb", "rb": ".rb",
    "php": ".php",
    "html": ".html",
    "css": ".css",
    "scss": ".scss",
    "less": ".less",
    "json": ".json",
    "xml": ".xml",
    "yaml": ".yaml", "yml": ".yaml",
    "toml": ".toml",
    "sql": ".sql",
    "bash": ".sh", "sh": ".sh", "shell": ".sh",
    "powershell": ".ps1", "ps1": ".ps1",
    "bat": ".bat", "batch": ".bat",
    "markdown": ".md", "md": ".md",
    "lua": ".lua",
    "r": ".r",
    "scala": ".scala",
    "dart": ".dart",
    "groovy": ".groovy",
    "perl": ".pl",
    "jsx": ".jsx", "tsx": ".tsx",
    "vue": ".vue",
    "svelte": ".svelte",
}

# --- Language → block comment style mapping ---
# Maps normalized language keys to (start, end) comment delimiters.
# Languages with only line-comments use a synthetic block built from line prefixes.
_LANG_BLOCK_COMMENT: dict[str, tuple[str, str | None]] = {
    # C-style block comments
    ".js": ("/*", "*/"), ".ts": ("/*", "*/"), ".java": ("/*", "*/"),
    ".c": ("/*", "*/"), ".cpp": ("/*", "*/"), ".cs": ("/*", "*/"),
    ".go": ("/*", "*/"), ".rs": ("/*", "*/"), ".kt": ("/*", "*/"),
    ".swift": ("/*", "*/"), ".php": ("/*", "*/"), ".scss": ("/*", "*/"),
    ".less": ("/*", "*/"), ".css": ("/*", "*/"), ".dart": ("/*", "*/"),
    ".groovy": ("/*", "*/"), ".scala": ("/*", "*/"),
    ".jsx": ("/*", "*/"), ".tsx": ("/*", "*/"),
    ".vue": ("<!--", "-->"), ".svelte": ("<!--", "-->"),
    ".html": ("<!--", "-->"), ".xml": ("<!--", "-->"),
    ".md": ("<!--", "-->"),
    # Hash-style line comments (synthesized block)
    ".py": ("#", None), ".rb": ("#", None), ".sh": ("#", None),
    ".ps1": ("#", None), ".r": ("#", None), ".pl": ("#", None),
    ".yaml": ("#", None), ".toml": ("#", None),
    # SQL
    ".sql": ("/*", "*/"),
    # Lua
    ".lua": ("--[[", "]]"),
    # Batch
    ".bat": ("REM ", None),
}


def _wrap_prompt_as_comment(prompt: str, ext: str) -> str:
    """Wrap *prompt* in a language-appropriate block comment for *ext*."""
    delimiters = _LANG_BLOCK_COMMENT.get(ext)
    if not delimiters:
        # Unknown language — fall back to generic C-style
        delimiters = ("/*", "*/")

    start, end = delimiters
    lines = prompt.splitlines()

    if end is None:
        # Line-comment style: prefix every line
        header = f"{start} AI Prompt / Context:"
        commented = [header] + [f"{start} {line}" if line.strip() else start for line in lines]
        return "\n".join(commented) + "\n\n"
    else:
        # Block-comment style
        inner = "\n".join(f"  {line}" if line.strip() else "" for line in lines)
        return f"{start}\n  AI Prompt / Context:\n\n{inner}\n{end}\n\n"


def _get_extension_for_language(lang: str) -> str:
    """Map a code-fence language tag to a file extension."""
    return _LANG_EXTENSIONS.get(lang.lower().strip(), ".txt") if lang else ".txt"


def _open_code_in_ide(ide: str, code: str, lang: str):
    """Write *code* to a temp file and open it in the specified IDE.

    When a user prompt is available (stored in the module-level
    ``_last_user_prompt``), it is prepended to the file as a
    language-appropriate block comment so that AI agents in the
    external IDE have context about what was created.
    """
    logger = logging.getLogger(__name__)
    ext = _get_extension_for_language(lang)

    # Prepend prompt context as a block comment if available
    prompt = _last_user_prompt
    if prompt:
        comment_block = _wrap_prompt_as_comment(prompt, ext)
        file_content = comment_block + code
    else:
        file_content = code

    try:
        import hashlib
        content_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]
        temp_dir = os.path.join(tempfile.gettempdir(), "snapsolve_code")
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"snippet_{content_hash}{ext}")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(file_content)
    except OSError as e:
        logger.error(f"Failed to write temp file for IDE: {e}")
        return

    logger.info(f"Opening code in {ide}: {temp_path} (lang={lang})")

    try:
        from config.settings import load_config
        app_config = load_config()

        if ide == "pycharm":
            pycharm_path = app_config.get("ide_pycharm_path", "pycharm")
            subprocess.Popen(f'"{pycharm_path}" "{temp_path}"', shell=True)
        elif ide == "antigravity":
            default_antigravity = str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe")
            antigravity_path = app_config.get("ide_antigravity_path", default_antigravity)
            subprocess.Popen(f'"{antigravity_path}" --goto "{temp_path}"', shell=True)
        else:
            logger.warning(f"Unknown IDE: {ide}")
    except FileNotFoundError:
        logger.error(
            f"IDE executable for '{ide}' not found. "
            f"Make sure it is on your PATH or installed in a standard location."
        )
    except OSError as e:
        logger.error(f"Failed to launch {ide}: {e}")


class _PopupWebPage(QWebEnginePage):
    """Custom page that intercepts snapsolve:// navigation for IDE integration."""

    # noinspection PyPep8Naming
    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        if url.scheme() == "snapsolve" and url.host() == "open-in-ide":
            parsed = urlparse(url.toString())
            params = parse_qs(parsed.query)
            ide = params.get("ide", [""])[0]
            lang = params.get("lang", [""])[0]
            code = params.get("code", [""])[0]

            if ide and code:
                threading.Thread(
                    target=_open_code_in_ide,
                    args=(ide, code, lang),
                    daemon=True,
                ).start()

            return False  # Don't actually navigate

        return super().acceptNavigationRequest(url, nav_type, is_main_frame)
