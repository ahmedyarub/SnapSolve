"""Active window tracking via Windows API.

Provides :func:`get_active_window_info` which returns metadata about the
currently focused window (title, process name, executable path).  Uses
``ctypes`` exclusively — no ``pywin32`` dependency required.

On non-Windows platforms the function always returns ``None``.
"""
import logging
import os
import sys
from typing import Optional, TypedDict

logger = logging.getLogger(__name__)


class WindowInfo(TypedDict):
    """Metadata about the currently active (foreground) window."""
    window_title: str
    process_name: str
    app_name: str
    exe_path: str


# Friendly display names for common executables
_APP_DISPLAY_NAMES: dict[str, str] = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi",
    "code.exe": "VS Code",
    "devenv.exe": "Visual Studio",
    "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ",
    "webstorm64.exe": "WebStorm",
    "rider64.exe": "Rider",
    "clion64.exe": "CLion",
    "goland64.exe": "GoLand",
    "explorer.exe": "Explorer",
    "notepad.exe": "Notepad",
    "notepad++.exe": "Notepad++",
    "cmd.exe": "CMD",
    "powershell.exe": "PowerShell",
    "pwsh.exe": "PowerShell",
    "windowsterminal.exe": "Terminal",
    "slack.exe": "Slack",
    "teams.exe": "Teams",
    "discord.exe": "Discord",
    "zoom.exe": "Zoom",
    "spotify.exe": "Spotify",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook",
    "onenote.exe": "OneNote",
    "obsidian.exe": "Obsidian",
    "notion.exe": "Notion",
    "figma.exe": "Figma",
    "gimp-2.10.exe": "GIMP",
    "photoshop.exe": "Photoshop",
    "vlc.exe": "VLC",
    "antigravity ide.exe": "Antigravity IDE",
    "cursor.exe": "Cursor",
    "sublime_text.exe": "Sublime Text",
}


def _derive_app_name(process_name: str) -> str:
    """Derive a human-friendly app name from the process executable name."""
    lower = process_name.lower()

    # Check the lookup table first
    if lower in _APP_DISPLAY_NAMES:
        return _APP_DISPLAY_NAMES[lower]

    # Strip the extension and title-case
    stem = os.path.splitext(process_name)[0]

    # Remove common suffixes like "64", "32"
    for suffix in ("64", "32"):
        if stem.endswith(suffix) and len(stem) > len(suffix):
            stem = stem[:-len(suffix)]

    # Replace separators with spaces and title-case
    friendly = stem.replace("_", " ").replace("-", " ").strip()
    return friendly.title() if friendly else process_name


def get_active_window_info() -> Optional[WindowInfo]:
    """Return metadata about the currently focused foreground window.

    Returns ``None`` on non-Windows platforms, if no window is focused,
    or if any OS call fails.  This function never raises — all errors
    are logged and swallowed.
    """
    if sys.platform != "win32":
        return None

    try:
        return _get_active_window_info_win32()
    except Exception as exc:
        logger.debug("Failed to get active window info: %s", exc)
        return None


def _get_active_window_info_win32() -> Optional[WindowInfo]:
    """Windows-specific implementation using ctypes."""
    import ctypes  # noqa: PLC0415
    import ctypes.wintypes  # noqa: PLC0415

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # --- Get foreground window handle ---
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    # --- Get window title ---
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        window_title = ""
    else:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        window_title = buf.value

    # --- Get process ID ---
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == 0:
        return None

    # --- Get executable path via OpenProcess + QueryFullProcessImageNameW ---
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return None

    try:
        exe_buf = ctypes.create_unicode_buffer(1024)
        exe_size = ctypes.wintypes.DWORD(1024)
        result = kernel32.QueryFullProcessImageNameW(
            handle, 0, exe_buf, ctypes.byref(exe_size)
        )
        if not result:
            return None

        exe_path = exe_buf.value
    finally:
        kernel32.CloseHandle(handle)

    process_name = os.path.basename(exe_path)

    # Detect when the foreground window belongs to *this* app (SnapSolve)
    if pid.value == os.getpid():
        app_name = "SnapSolve"
        process_name = "snapsolve"
    else:
        app_name = _derive_app_name(process_name)

    return WindowInfo(
        window_title=window_title,
        process_name=process_name,
        app_name=app_name,
        exe_path=exe_path,
    )
