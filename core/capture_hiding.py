"""Platform-specific helpers to hide Qt widgets from screen-capture APIs.

- **Windows 10 2004+** — ``SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)``
- **macOS** — ``NSWindow.setSharingType_(NSWindowSharingNone)``
  (requires ``pyobjc-framework-Cocoa``)
- **Linux** — unsupported (no universal X11 / Wayland API)
"""

import logging
import platform

logger = logging.getLogger(__name__)


def _apply_display_affinity_windows(widget, exclude: bool) -> bool:
    """Windows: use SetWindowDisplayAffinity to hide from capture.

    Requires Windows 10 2004+.  Sets WDA_EXCLUDEFROMCAPTURE when
    *exclude* is True, or WDA_NONE to restore normal behaviour.
    """
    import ctypes

    hwnd = int(widget.winId())
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    WDA_NONE = 0x00000000
    affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
    result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
    return bool(result)


def _apply_display_affinity_macos(widget, exclude: bool) -> bool:
    """macOS: use NSWindow.setSharingType_ to hide from capture.

    Sets ``NSWindowSharingNone`` (0) when *exclude* is True so the
    window is excluded from screen-capture / screen-sharing APIs.
    Restores ``NSWindowSharingReadOnly`` (1) otherwise.
    Requires the ``pyobjc-framework-Cocoa`` package.
    """
    try:
        # noinspection PyUnresolvedReferences
        from AppKit import NSApp  # noqa: F401 – validates pyobjc is available
    except ImportError:
        logger.warning(
            "pyobjc-framework-Cocoa is not installed — capture-hiding "
            "is unavailable on macOS.  Install it with:  "
            "pip install pyobjc-framework-Cocoa"
        )
        return False

    try:
        win_handle = widget.windowHandle()
        if win_handle is None:
            return False

        # noinspection PyUnresolvedReferences
        import objc  # noqa: F811
        from ctypes import c_void_p

        ns_view = objc.objc_object(c_void_p=c_void_p(int(widget.winId())))
        ns_window = ns_view.window()
        if ns_window is None:
            return False

        NSWindowSharingNone = 0
        NSWindowSharingReadOnly = 1
        sharing = NSWindowSharingNone if exclude else NSWindowSharingReadOnly
        ns_window.setSharingType_(sharing)
        return True
    except Exception as exc:
        logger.debug("Failed to set macOS window sharing type: %s", exc)
        return False


def _apply_display_affinity_linux(widget, exclude: bool) -> bool:
    """Linux: no reliable API exists to hide a window from capture.

    Neither X11 nor Wayland expose a universal mechanism for excluding
    a window from screen-capture.  Log a one-time informational message
    and return False so callers know the operation is unsupported.
    """
    _ = widget, exclude  # unused — intentional no-op
    if not hasattr(_apply_display_affinity_linux, "_warned"):
        logger.info(
            "Capture-hiding is not supported on Linux. "
            "Neither X11 nor Wayland provide a universal API for this."
        )
        _apply_display_affinity_linux._warned = True
    return False


def apply_display_affinity(widget, exclude: bool = True) -> bool:
    """Hide or unhide a widget from screen-capture APIs.

    Dispatches to the platform-specific implementation:
    - **Windows 10 2004+**: ``SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)``
    - **macOS**: ``NSWindow.setSharingType_(NSWindowSharingNone)``
    - **Linux**: No-op (unsupported) — logs an informational message.
    """
    system = platform.system()
    if system == "Windows":
        return _apply_display_affinity_windows(widget, exclude)
    if system == "Darwin":
        return _apply_display_affinity_macos(widget, exclude)
    if system == "Linux":
        return _apply_display_affinity_linux(widget, exclude)
    return False
