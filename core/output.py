import json
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QEvent, QPoint, QSize, QRect, QUrl
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
    QLineEdit,
    QComboBox,
)


# --- Signal Broker ---
class UISignals(QObject):
    toggle_panel = pyqtSignal(object)
    set_multi_state = pyqtSignal(bool)
    set_source = pyqtSignal(str, float)
    set_processing_state = pyqtSignal(bool)
    show_popup = pyqtSignal(dict)
    close_popup = pyqtSignal()
    capture_popup_screenshot = pyqtSignal()
    request_active_source = pyqtSignal(object)
    show_subtitle = pyqtSignal(str)
    update_subtitle = pyqtSignal(str, bool)
    clear_subtitles = pyqtSignal()
    toggle_all_visibility = pyqtSignal()
    show_url_input = pyqtSignal()
    open_url = pyqtSignal(str)
    open_session_browser = pyqtSignal()
    set_transcription_language = pyqtSignal(str)


class SelectorSignals(QObject):
    request_coords = pyqtSignal(object)
    coords_ready = pyqtSignal(object)


ui_signals = UISignals()
selector_signals = SelectorSignals()
_app_callbacks = {}


def _apply_display_affinity(widget, exclude: bool = True) -> bool:
    """Set or clear WDA_EXCLUDEFROMCAPTURE on a widget's native window.

    When *exclude* is True the window becomes invisible to screen-capture
    APIs (video-call sharing, OBS, Win+Shift+S, etc.) while remaining
    fully visible on the user's monitor.  Requires Windows 10 2004+.
    """
    import platform

    if platform.system() != "Windows":
        return False

    import ctypes

    hwnd = int(widget.winId())
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    WDA_NONE = 0x00000000
    affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
    result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
    return bool(result)


# --- Mixins for frameless window interaction ---


_RESIZE_MARGIN = 8  # Pixels from edge to trigger resize


class DraggableWidgetMixin:
    """Mixin that adds drag-to-move behaviour to a frameless QWidget.

    Drag starts only when the mouse press lands on the widget background
    (i.e. not on a child button, text edit, or other interactive control).
    """

    def _init_draggable(self):
        self._drag_pos: QPoint | None = None

    def _is_on_interactive_child(self, pos) -> bool:
        """Return True if *pos* (local coords) is over a child that should
        consume the click instead of starting a drag."""
        child = self.childAt(pos)  # type: ignore[attr-defined]
        if child is None:
            return False
        return isinstance(child, (QPushButton, QTextEdit, QWebEngineView))

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._is_on_interactive_child(event.pos())
        ):
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)  # type: ignore[misc]

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)  # type: ignore[attr-defined]
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)  # type: ignore[misc]

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)  # type: ignore[misc]


class _DragHandleBar(QWidget):
    """A thin bar at the top of a frameless widget that acts as a drag handle.

    Includes a subtle grip indicator and a close button.  Dragging anywhere
    on this bar moves the *parent* window.
    """

    def __init__(self, parent_window: QWidget):
        super().__init__(parent_window)
        self._parent_window = parent_window
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(24)
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self.setStyleSheet(
            "background-color: rgba(50, 50, 50, 200); border: none;"
            " border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )

        bar_layout = QHBoxLayout(self)
        bar_layout.setContentsMargins(8, 2, 4, 2)

        grip_label = QLabel("⠿")
        grip_label.setStyleSheet("color: #888; font-size: 14px; background: transparent;")
        bar_layout.addWidget(grip_label)
        bar_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: gray;"
            " border: none; font-weight: bold; }"
            " QPushButton:hover { color: white; }"
        )
        close_btn.clicked.connect(parent_window.hide)
        bar_layout.addWidget(close_btn)

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()  # Prevent propagation to parent's DraggableWidgetMixin
        else:
            super().mousePressEvent(event)

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._parent_window.move(self._parent_window.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event):
        if self._drag_pos is not None:
            self._drag_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _apply_opacity(self, opacity: float):
        """Adjust the drag bar background alpha to match the global opacity."""
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(50, 50, 50, {alpha_int}); border: none;"
            f" border-top-left-radius: 8px; border-top-right-radius: 8px;"
        )


class ResizableWidgetMixin:
    """Mixin that adds edge/corner resize handles to a frameless QWidget."""

    _EDGE_NONE = 0
    _EDGE_LEFT = 1
    _EDGE_RIGHT = 2
    _EDGE_TOP = 4
    _EDGE_BOTTOM = 8

    _CURSOR_MAP = {
        _EDGE_LEFT: Qt.CursorShape.SizeHorCursor,
        _EDGE_RIGHT: Qt.CursorShape.SizeHorCursor,
        _EDGE_TOP: Qt.CursorShape.SizeVerCursor,
        _EDGE_BOTTOM: Qt.CursorShape.SizeVerCursor,
        _EDGE_LEFT | _EDGE_TOP: Qt.CursorShape.SizeFDiagCursor,
        _EDGE_RIGHT | _EDGE_BOTTOM: Qt.CursorShape.SizeFDiagCursor,
        _EDGE_RIGHT | _EDGE_TOP: Qt.CursorShape.SizeBDiagCursor,
        _EDGE_LEFT | _EDGE_BOTTOM: Qt.CursorShape.SizeBDiagCursor,
    }

    def _init_resizable(self, min_size: QSize | None = None):
        self._resize_edge = self._EDGE_NONE
        self._resize_origin: QPoint | None = None
        self._resize_geom: QRect | None = None
        self._min_resize_size = min_size or QSize(200, 100)
        self.setMouseTracking(True)  # type: ignore[attr-defined]

    def _detect_edge(self, pos) -> int:
        """Determine which edge(s) *pos* (local coords) is near."""
        rect = self.rect()  # type: ignore[attr-defined]
        edge = self._EDGE_NONE
        if pos.x() <= _RESIZE_MARGIN:
            edge |= self._EDGE_LEFT
        elif pos.x() >= rect.width() - _RESIZE_MARGIN:
            edge |= self._EDGE_RIGHT
        if pos.y() <= _RESIZE_MARGIN:
            edge |= self._EDGE_TOP
        elif pos.y() >= rect.height() - _RESIZE_MARGIN:
            edge |= self._EDGE_BOTTOM
        return edge

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._detect_edge(event.pos())
            if edge != self._EDGE_NONE:
                self._resize_edge = edge
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()  # type: ignore[attr-defined]
                return  # Consume – don't start a drag
        super().mousePressEvent(event)  # type: ignore[misc]

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event):
        if self._resize_edge != self._EDGE_NONE and self._resize_origin is not None:
            assert self._resize_geom is not None
            delta = event.globalPosition().toPoint() - self._resize_origin
            new_geom = QRect(self._resize_geom)

            if self._resize_edge & self._EDGE_LEFT:
                new_geom.setLeft(new_geom.left() + delta.x())
            if self._resize_edge & self._EDGE_RIGHT:
                new_geom.setRight(new_geom.right() + delta.x())
            if self._resize_edge & self._EDGE_TOP:
                new_geom.setTop(new_geom.top() + delta.y())
            if self._resize_edge & self._EDGE_BOTTOM:
                new_geom.setBottom(new_geom.bottom() + delta.y())

            # Enforce minimum size
            if new_geom.width() < self._min_resize_size.width():
                if self._resize_edge & self._EDGE_LEFT:
                    new_geom.setLeft(new_geom.right() - self._min_resize_size.width())
                else:
                    new_geom.setRight(new_geom.left() + self._min_resize_size.width())
            if new_geom.height() < self._min_resize_size.height():
                if self._resize_edge & self._EDGE_TOP:
                    new_geom.setTop(new_geom.bottom() - self._min_resize_size.height())
                else:
                    new_geom.setBottom(new_geom.top() + self._min_resize_size.height())

            self.setGeometry(new_geom)  # type: ignore[attr-defined]
            return

        # Update cursor shape when hovering near edges
        edge = self._detect_edge(event.pos())
        cursor_shape = self._CURSOR_MAP.get(edge)
        if cursor_shape is not None:
            self.setCursor(QCursor(cursor_shape))  # type: ignore[attr-defined]
        else:
            self.unsetCursor()  # type: ignore[attr-defined]

        super().mouseMoveEvent(event)  # type: ignore[misc]

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event):
        if self._resize_edge != self._EDGE_NONE:
            self._resize_edge = self._EDGE_NONE
            self._resize_origin = None
            self._resize_geom = None
            return
        super().mouseReleaseEvent(event)  # type: ignore[misc]


# --- PyQt UI Components ---


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


def _get_extension_for_language(lang: str) -> str:
    """Map a code-fence language tag to a file extension."""
    return _LANG_EXTENSIONS.get(lang.lower().strip(), ".txt") if lang else ".txt"


def _open_code_in_ide(ide: str, code: str, lang: str):
    """Write *code* to a temp file and open it in the specified IDE."""
    logger = logging.getLogger(__name__)
    ext = _get_extension_for_language(lang)

    try:
        fd, temp_path = tempfile.mkstemp(suffix=ext, prefix="snapsolve_code_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code)
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


class PopupWidget(ResizableWidgetMixin, DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self._init_resizable(QSize(250, 120))
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._bg_opacity = 0.8
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 10px;"
        )

        self.layout = QVBoxLayout(self)

        # Top Bar
        self.top_bar = QHBoxLayout()
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: white; border: none; font-weight: bold; } QPushButton:hover { color: red; }"
        )
        self.close_btn.clicked.connect(self.hide)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.close_btn)
        self.layout.addLayout(self.top_bar)

        # WebEngine View for Markdown/Math — uses custom page for IDE interception
        self.web_view = QWebEngineView()
        self._popup_page = _PopupWebPage(self.web_view)
        self.web_view.setPage(self._popup_page)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self._popup_page.setBackgroundColor(Qt.GlobalColor.transparent)
        self.web_view.setStyleSheet("background-color: transparent; border: none;")
        self.layout.addWidget(self.web_view)

        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.timeout.connect(self.hide)

        self._is_loaded = False
        self._pending_js = []
        self.web_view.loadFinished.connect(self._on_load_finished)

        # Load HTML using a file:// URL to avoid IPC size limits
        _assets_dir = Path(__file__).parent / "web_assets"
        _popup_html = _assets_dir / "popup.html"
        self.web_view.setUrl(QUrl.fromLocalFile(str(_popup_html)))

    def _on_load_finished(self, ok: bool):
        self._is_loaded = True
        for js in self._pending_js:
            self.web_view.page().runJavaScript(js)
        self._pending_js.clear()

    def _apply_opacity(self, opacity: float):
        """Apply opacity to the popup window.

        Because QWebEngineView has an opaque background (#1e1e1e) to prevent 
        scrolling shadows, we use setWindowOpacity to make the entire window
        translucent as requested.
        """
        self._bg_opacity = opacity
        self.setStyleSheet(
            "background-color: #1e1e1e;"
            " border: 2px solid #555; border-radius: 10px;"
        )
        self.setWindowOpacity(opacity)

    def show_content(self, data):
        text = data.get("text", "")
        auto_close = data.get("auto_close", 5000)
        opacity = data.get("opacity", 0.8)
        is_result = data.get("is_result", False)

        self._apply_opacity(opacity)

        # Safely serialize string for JS injection using json.dumps
        js_text = json.dumps(text)
        js_code = f"updateContent({js_text});"

        # Update via JS evaluation (buffer if page is not yet loaded)
        if self._is_loaded:
            self.web_view.page().runJavaScript(js_code)
        else:
            self._pending_js.append(js_code)

        # Determine size and position
        screen = QApplication.primaryScreen().size()
        max_w, max_h = int(screen.width() * 0.5), int(screen.height() * 0.5)

        word_count = len(text.split())
        is_long = is_result and word_count > 10

        if is_long:
            # Estimate sizing, max out at 50%
            self.resize(max_w, max_h)
        else:
            # Small popup
            self.resize(400, 150)

        # Position bottom right
        w, h = self.width(), self.height()
        x = screen.width() - w - 50
        y = screen.height() - h - 100
        self.move(x, y)

        if auto_close:
            self.close_btn.hide()
            self.auto_close_timer.start(auto_close)
        else:
            self.close_btn.show()
            self.auto_close_timer.stop()

        self.show()

    def load_url(self, url: str):
        self._is_loaded = False
        screen = QApplication.primaryScreen().size()
        w, h = int(screen.width() * 0.6), int(screen.height() * 0.6)
        x = (screen.width() - w) // 2
        y = (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)
        
        self.web_view.setUrl(QUrl(url))
        self.show()
        self.raise_()
        self.activateWindow()

    def capture_full_page_screenshot(self):
        """Capture the full web view content as a PNG and send to remote control server."""
        import os
        import tempfile
        import logging

        logger = logging.getLogger(__name__)

        def on_size_eval(size_data):
            width = self.width() # Keep current width to avoid text reflow
            content_height = size_data.get('height', self.height())
            
            # Account for layout margins and the top bar's height
            extra_height = self.height() - self.web_view.height()
            total_height = content_height + extra_height + 20 # Add some padding
            
            original_size = self.size()
            
            # Force size past screen limits
            self.setFixedSize(width, int(total_height))
            
            # Wait longer for Chromium to reflow and repaint the larger surface
            QTimer.singleShot(600, lambda: capture_now(original_size))

        def capture_now(original_size):
            pixmap = self.grab()
            
            # Restore normal resizing
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.resize(original_size)

            try:
                fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="snapsolve_response_")
                os.close(fd)
                pixmap.save(temp_path, "PNG")

                from core.remote_control_server import set_response_image_path
                set_response_image_path(temp_path)
            except Exception as e:
                logger.error(f"Failed to capture and save popup screenshot: {e}")

        # Scroll to top and get the actual scroll dimensions
        self.web_view.page().runJavaScript(
            "window.scrollTo(0, 0); ({ width: document.documentElement.scrollWidth, height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) })",
            on_size_eval
        )


class RecordButton(QPushButton):
    # Signals for different actions
    start_recording = pyqtSignal(
        object
    )  # Pass enable_transcription flag (can be None or bool)
    stop_recording = pyqtSignal(
        bool
    )  # Pass boolean flag indicating if it was a long press

    def __init__(self, text, style):
        super().__init__(text)
        self.setStyleSheet(style)
        self.is_recording = False
        self.is_long_press = False
        self.press_timer = QTimer(self)
        self.press_timer.setSingleShot(True)
        self.press_timer.timeout.connect(self.on_long_press)

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_long_press = False
            self.press_timer.start(500)  # 500ms for long press

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_timer.stop()
            if self.is_long_press:
                # It was a long press, so releasing stops the recording
                self.stop_record_action()
            else:
                # It was a click, toggle recording state
                if self.is_recording:
                    self.stop_record_action()
                else:
                    self.start_record_action()

    def on_long_press(self):
        self.is_long_press = True
        if not self.is_recording:
            self.start_record_action()

    def start_record_action(self):
        self.is_recording = True
        self.setText("⏹️ Stop / 🔴 Recording...")
        self.setStyleSheet(
            self.styleSheet().replace("rgba(45, 45, 45, 180)", "rgba(178, 34, 34, 0.7)")
        )
        # Disable transcription for long press, use config for click
        enable_transcription = None if not self.is_long_press else False
        self.start_recording.emit(enable_transcription)

    def stop_record_action(self):
        self.is_recording = False
        self.setText("🎙️ Record")
        self.setStyleSheet(
            self.styleSheet().replace("rgba(178, 34, 34, 0.7)", "rgba(45, 45, 45, 180)")
        )
        self.stop_recording.emit(self.is_long_press)


class SubtitleLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.creation_time = 0

    # noinspection PyPep8Naming
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            text = self.text()
            if "text_submit" in _app_callbacks:
                try:
                    threading.Thread(
                        target=_app_callbacks["text_submit"],
                        args=(text,),
                        daemon=True,
                    ).start()
                except Exception as e:
                    print(f"Error submitting subtitle text: {e}")


class SubtitleWidget(DraggableWidgetMixin, QWidget):
    """Widget for displaying real-time transcription subtitles with fading effects."""

    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # Remove WA_TranslucentBackground to ensure proper rendering
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Use a more visible background for debugging
        self.setStyleSheet(
            "background-color: transparent; border: 1px solid rgba(255, 0, 0, 0.3);"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        # Store subtitle labels with their creation time
        self.subtitle_labels = []
        self.max_subtitles = 5  # Maximum number of subtitle lines to show
        self.fade_duration = (
            15000  # Duration for fade effect in milliseconds (15 seconds)
        )

        # Timer for updating fade effects
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self.update_fade_effects)
        self.fade_timer.start(100)  # Update every 100ms

        # Position settings
        self.target_position = None
        self.update_position()

    def update_position(self):
        """Position widget at bottom center of screen."""
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        self.setFixedWidth(w)
        self.adjustSize()
        h = self.height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

        # Debug logging
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Subtitle widget positioned at ({x}, {y}) with size ({w}, {h})")
        logger.info(f"Screen size: {screen.width()}x{screen.height()}")

    def get_subtitle_text(self, index: int) -> str:
        """Get text of a subtitle by index (1-based from bottom/newest)."""
        if not self.subtitle_labels or index < 1 or index > len(self.subtitle_labels):
            return ""
        # 1 means youngest, which is at the end of the list (-1)
        return self.subtitle_labels[-index].text()

    def add_subtitle(self, text: str):
        """Add a new subtitle line."""
        import time
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"add_subtitle called with text: {text}")
        logger.info(f"Subtitle widget visible: {self.isVisible()}")
        logger.info(f"Subtitle widget position: {self.pos()}, size: {self.size()}")

        # Update the creation time of existing subtitles so they fade out relative to the newest one
        current_time = time.time()
        for i, existing_label in enumerate(reversed(self.subtitle_labels)):
            # Give older subtitles an artificial age bump so they look older
            existing_label.creation_time = current_time - (i + 1) * 2.0

        # Create new subtitle label
        label = SubtitleLabel(text)
        label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: rgba(255, 255, 255, 1.0);
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        # Store with creation time
        label.creation_time = time.time()
        self.subtitle_labels.append(label)

        # Add to layout
        self.layout.addWidget(label)

        # Remove oldest if we have too many
        if len(self.subtitle_labels) > self.max_subtitles:
            oldest = self.subtitle_labels.pop(0)
            self.layout.removeWidget(oldest)
            oldest.deleteLater()

        # Force layout update before adjusting size
        self.layout.activate()

        # Update widget size
        self.adjustSize()
        self.update_position()

        # Ensure widget has minimum height
        if self.height() == 0:
            self.setMinimumHeight(50)
            self.adjustSize()

        # Show if hidden
        if not self.isVisible():
            logger.info("Subtitle widget was hidden, attempting to show it")
            self.show()
            self.raise_()  # Bring to front
            self.activateWindow()  # Force window activation
            self.repaint()  # Force repaint
            logger.info(
                f"After show(), widget visible: {self.isVisible()}, size: {self.size()}"
            )

    def update_last_subtitle(self, text: str, append: bool = False):
        """Update the text of the most recent subtitle instead of creating a new one."""
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"update_last_subtitle called with text: {text}, append: {append}")

        if not self.subtitle_labels:
            # No existing subtitles, create a new one
            logger.info("No existing subtitles, creating new one")
            self.add_subtitle(text)
            return

        # Update the last subtitle's text
        last_label = self.subtitle_labels[-1]

        # Reset the creation time of the active subtitle so it doesn't fade while being updated
        import time

        last_label.creation_time = time.time()

        if append:
            # Append to existing text
            current_text = last_label.text()
            new_text = current_text + " " + text
            last_label.setText(new_text)
            logger.info(f"Appended to last subtitle: {new_text}")
        else:
            # Replace existing text
            last_label.setText(text)
            logger.info(f"Updated last subtitle to: {text}")

        # Force layout update and size adjustment
        self.layout.activate()
        self.adjustSize()
        self.update_position()

        # Ensure widget is visible
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            self.repaint()

    def clear_subtitles(self):
        """Clear all subtitles."""
        for label in self.subtitle_labels:
            self.layout.removeWidget(label)
            label.deleteLater()
        self.subtitle_labels.clear()
        self.hide()

    def update_fade_effects(self):
        """Update opacity of subtitle labels based on their age."""
        import time

        current_time = time.time()

        for i, label in enumerate(self.subtitle_labels):
            # Calculate age in seconds
            age = current_time - label.creation_time

            # Calculate opacity based on position and age
            # Newer subtitles (higher index) are more opaque
            # Older subtitles fade out more gradually
            position_factor = (
                (i + 1) / len(self.subtitle_labels) if self.subtitle_labels else 1
            )

            # More gradual fading - start fading after 5 seconds, complete fade by fade_duration
            fade_start = 5.0  # Start fading after 5 seconds
            if age < fade_start:
                age_factor = 1.0  # Full opacity for first 5 seconds
            else:
                age_factor = max(
                    0.3,
                    1.0
                    - ((age - fade_start) / ((self.fade_duration / 1000) - fade_start)),
                )

            # Combine factors, but ensure minimum visibility
            opacity = min(0.95, max(0.4, position_factor * age_factor))

            # The newest subtitle should always be fully visible if it's less than fade_start old
            if i == len(self.subtitle_labels) - 1 and age < fade_start:
                opacity = 0.95

            # Update label style with new opacity
            label.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, {opacity * 0.7:.3f});
                    color: rgba(255, 255, 255, {opacity:.3f});
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 16px;
                    font-weight: bold;
                }}
            """)

        # Remove very old subtitles
        if self.subtitle_labels:
            oldest_age = current_time - self.subtitle_labels[0].creation_time
            if (
                oldest_age > (self.fade_duration / 1000) * 2
            ):  # Remove after 2x fade duration
                oldest = self.subtitle_labels.pop(0)
                self.layout.removeWidget(oldest)
                oldest.deleteLater()
                self.adjustSize()
                self.update_position()


def call_action(action, *args):
    if action in _app_callbacks:
        try:
            # Run callback in background thread so it doesn't block UI
            threading.Thread(
                target=_app_callbacks[action], args=args, daemon=True
            ).start()
        except Exception as e:
            print(f"Error calling {action}: {e}")


class PanelWidget(DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 230); border: 1px solid #444; border-radius: 8px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.is_multi_selecting = False

        # Drag Handle Bar (replaces the old close-button-only top bar)
        self.drag_handle = _DragHandleBar(self)
        self.layout.addWidget(self.drag_handle)

        # Buttons
        self.buttons = {}
        btn_style = (
            "QPushButton { background-color: rgba(45, 45, 45, 180); color: white;"
            " border: none; padding: 8px; border-radius: 4px; font-size: 14px;}"
            " QPushButton:hover { background-color: rgba(62, 62, 62, 220); }"
            " QPushButton:disabled { color: #777; }"
        )
        cancel_btn_style = (
            "QPushButton { background-color: rgba(178, 34, 34, 0.7); color: white;"
            " border: none; padding: 8px; border-radius: 4px; font-size: 14px;}"
            " QPushButton:hover { background-color: rgba(220, 20, 60, 0.8); }"
        )

        def create_btn(name, text, action, style=btn_style):
            btn = QPushButton(text)
            btn.setStyleSheet(style)
            btn.clicked.connect(lambda: call_action(action))
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            return btn

        self.btn_record = RecordButton("🎙️ Record", btn_style)
        self.btn_record.start_recording.connect(
            lambda enable_transcription: call_action(
                "start_record", enable_transcription
            )
        )
        self.btn_record.stop_recording.connect(
            lambda is_long_press: call_action("stop_record", is_long_press)
        )
        self.layout.addWidget(self.btn_record)
        self.buttons["record"] = self.btn_record

        self.btn_capture = create_btn("capture", "📸 Capture", "capture")
        self.btn_reselect = create_btn("reselect", "🎯 Reselect", "reselect")
        self.btn_multi = create_btn("multi", "➕ Multi-select", "multi_capture")
        self.btn_end_multi = create_btn(
            "end_multi", "✅ End Multi", "end_multi_capture"
        )
        self.btn_stitching = create_btn(
            "stitching", "🧵 Toggle Stitching", "toggle_stitching"
        )
        self.btn_cycle = create_btn("cycle", "🔄 Cycle Source", "cycle_source")

        self.btn_sessions = QPushButton("📋 Sessions")
        self.btn_sessions.setStyleSheet(btn_style)
        self.btn_sessions.clicked.connect(lambda: ui_signals.open_session_browser.emit())
        self.layout.addWidget(self.btn_sessions)
        self.buttons["sessions"] = self.btn_sessions

        self.btn_cancel = create_btn(
            "cancel", "❌ Cancel", "cancel", style=cancel_btn_style
        )

        # Transcription language selector (visible only in audio mode)
        from ui.config_ui import TRANSCRIPTION_LANGUAGES  # noqa: PLC0415
        lang_combo_style = (
            "QComboBox { background-color: rgba(45, 45, 45, 180); color: white;"
            " border: none; padding: 4px; border-radius: 4px; font-size: 12px;}"
            " QComboBox::drop-down { border: none; }"
            " QComboBox QAbstractItemView { background-color: #2d2d2d; color: white;"
            " selection-background-color: #3e3e3e; }"
        )
        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(lang_combo_style)
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            self.lang_combo.addItem(display_name, code)
        # Default to English
        en_idx = self.lang_combo.findData("en")
        if en_idx >= 0:
            self.lang_combo.setCurrentIndex(en_idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.layout.addWidget(self.lang_combo)
        self.lang_combo.hide()

        self.btn_end_multi.hide()
        self.btn_cancel.hide()

        self.resize(200, 340)

    def _broadcast_state(self):
        from core.remote_control_server import set_ui_state

        state = {}
        panel_visible = self.isVisible()
        for name, btn in self.buttons.items():
            state[name] = {
                "visible": bool(btn.isVisible() and panel_visible),
                "enabled": bool(btn.isEnabled()),
            }
        set_ui_state(state)

    # noinspection PyPep8Naming
    def showEvent(self, event):
        super().showEvent(event)
        self._broadcast_state()

    # noinspection PyPep8Naming
    def hideEvent(self, event):
        super().hideEvent(event)
        self._broadcast_state()

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        x = 20
        y = screen.height() - self.height() - 50
        self.move(x, y)

    def set_multi_state(self, in_progress):
        self.is_multi_selecting = in_progress
        self.btn_end_multi.setVisible(in_progress)
        self.btn_cancel.setVisible(in_progress)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def set_source(self, source_name):
        is_image = source_name == "image"
        is_audio = source_name == "audio"
        self.btn_capture.setVisible(is_image)
        self.btn_reselect.setVisible(is_image)
        self.btn_multi.setVisible(is_image)
        self.btn_record.setVisible(is_audio)
        self.lang_combo.setVisible(is_audio)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def _on_language_changed(self, _index: int):
        """Emit signal when the user changes the transcription language."""
        lang_code = self.lang_combo.currentData() or ""
        ui_signals.set_transcription_language.emit(lang_code)

    def set_transcription_language_value(self, lang_code: str):
        """Set the combo to a specific language code without triggering the signal."""
        idx = self.lang_combo.findData(lang_code)
        if idx >= 0:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

    def set_processing_state(self, is_processing):
        if not self.is_multi_selecting:
            self.btn_cancel.setVisible(is_processing)
        for name, btn in self.buttons.items():
            if name != "cancel":
                btn.setEnabled(not is_processing)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def _apply_opacity(self, opacity: float):
        """Apply opacity via RGBA backgrounds to the panel, drag handle, and all buttons."""
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(30, 30, 30, {alpha_int});"
            f" border: 1px solid #444; border-radius: 8px;"
        )
        self.drag_handle._apply_opacity(opacity)

        # Apply uniform alpha to all buttons
        btn_style = (
            f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: white;"
            f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
            f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
            f" QPushButton:disabled {{ color: #777; }}"
        )
        cancel_style = (
            f"QPushButton {{ background-color: rgba(178, 34, 34, {alpha_int}); color: white;"
            f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
            f" QPushButton:hover {{ background-color: rgba(220, 20, 60, {alpha_int}); }}"
        )
        for name, btn in self.buttons.items():
            if name == "cancel":
                btn.setStyleSheet(cancel_style)
            else:
                btn.setStyleSheet(btn_style)


class TextInputWidget(DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._bg_opacity = 0.8
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 8px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 4, 10, 10)

        # Drag Handle Bar
        self.drag_handle = _DragHandleBar(self)
        self.layout.addWidget(self.drag_handle)

        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet(
            "background-color: rgba(45, 45, 45, 180); color: white; border: none; font-size: 16px; padding: 5px;"
        )
        # Handle Enter key to submit, Shift+Enter for new line
        self.text_edit.installEventFilter(self)
        self.layout.addWidget(self.text_edit)

        self.is_processing = False

    def _apply_opacity(self, opacity: float):
        """Apply opacity via RGBA backgrounds to the widget, drag handle, and text edit."""
        self._bg_opacity = opacity
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(30, 30, 30, {alpha_int});"
            f" border: 2px solid #555; border-radius: 8px;"
        )
        self.drag_handle._apply_opacity(opacity)
        self.text_edit.setStyleSheet(
            f"background-color: rgba(45, 45, 45, {alpha_int}); color: white;"
            f" border: none; font-size: 16px; padding: 5px;"
        )

    @staticmethod
    def _is_return_key_event(event):
        """Check if event is return key event."""
        return event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter

    @staticmethod
    def _is_shift_modifier_pressed(event):
        """Check if shift modifier is pressed."""
        return event.modifiers() & Qt.KeyboardModifier.ShiftModifier

    def _handle_text_submission(self):
        """Handle text submission."""
        text = self.text_edit.toPlainText().strip()
        if text:
            self.text_edit.clear()
            if "text_submit" in _app_callbacks:
                threading.Thread(
                    target=_app_callbacks["text_submit"],
                    args=(text,),
                    daemon=True,
                ).start()

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event):
        if obj is self.text_edit and event.type() == event.Type.KeyPress:
            if self._is_return_key_event(event):
                if self._is_shift_modifier_pressed(event):
                    return False
                else:
                    if not self.is_processing:
                        self._handle_text_submission()
                    return True
        return super().eventFilter(obj, event)

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        h = 100  # Fixed initial height
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

    def set_processing_state(self, is_processing):
        self.is_processing = is_processing
        self.text_edit.setEnabled(not is_processing)
        if not is_processing:
            self.text_edit.setFocus()


class UrlInputWidget(DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._bg_opacity = 0.8
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 8px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 4, 10, 10)

        self.drag_handle = _DragHandleBar(self)
        self.layout.addWidget(self.drag_handle)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText("Enter URL to load...")
        self.line_edit.setStyleSheet(
            "background-color: rgba(45, 45, 45, 180); color: white; border: none; font-size: 16px; padding: 5px;"
        )
        self.line_edit.returnPressed.connect(self._handle_submit)
        self.layout.addWidget(self.line_edit)

    def _apply_opacity(self, opacity: float):
        self._bg_opacity = opacity
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(30, 30, 30, {alpha_int});"
            f" border: 2px solid #555; border-radius: 8px;"
        )
        self.drag_handle._apply_opacity(opacity)
        self.line_edit.setStyleSheet(
            f"background-color: rgba(45, 45, 45, {alpha_int}); color: white;"
            f" border: none; font-size: 16px; padding: 5px;"
        )

    def _handle_submit(self):
        url = self.line_edit.text().strip()
        if url:
            if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
                url = "https://" + url
            self.line_edit.clear()
            ui_signals.open_url.emit(url)
            self.hide()

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.4)
        h = 80
        x = (screen.width() - w) // 2
        y = (screen.height() - h) // 2
        self.setGeometry(x, y, w, h)


# --- UI Manager ---
def _on_request_active_source(q):
    from core.sources import get_active_source_instance

    q.put(get_active_source_instance())


class UIManager(QObject):
    def __init__(self):
        super().__init__()
        self._hide_from_capture = False
        self._global_opacity = 0.8
        self._saved_visibility: dict[str, bool] | None = None
        self.popup: PopupWidget | None = None
        self.panel: PanelWidget | None = None
        self.text_input: TextInputWidget | None = None
        self.subtitle: SubtitleWidget | None = None
        self.url_input: UrlInputWidget | None = None
        self._init_ui()
        selector_signals.request_coords.connect(_handle_request_coords)

    def _init_ui(self):
        if not QApplication.instance():
            return  # Should not happen, main.py creates it
        self.popup = PopupWidget()
        self.panel = PanelWidget()
        self.text_input = TextInputWidget()
        self.subtitle = SubtitleWidget()
        self.url_input = UrlInputWidget()

        # Install event filters so capture-hiding is applied on every show
        self.popup.installEventFilter(self)
        self.panel.installEventFilter(self)
        self.text_input.installEventFilter(self)
        self.subtitle.installEventFilter(self)
        self.url_input.installEventFilter(self)

        # Connect signals
        ui_signals.toggle_panel.connect(self._on_toggle_panel)
        ui_signals.set_multi_state.connect(self.panel.set_multi_state)
        ui_signals.set_source.connect(self._on_set_source)
        ui_signals.set_processing_state.connect(self._on_set_processing_state)
        ui_signals.show_popup.connect(self.popup.show_content)
        ui_signals.close_popup.connect(self.popup.hide)
        ui_signals.capture_popup_screenshot.connect(self.popup.capture_full_page_screenshot)
        ui_signals.request_active_source.connect(_on_request_active_source)
        ui_signals.show_subtitle.connect(self._on_show_subtitle)
        ui_signals.update_subtitle.connect(self._on_update_subtitle)
        ui_signals.clear_subtitles.connect(self._on_clear_subtitles)
        ui_signals.toggle_all_visibility.connect(self._on_toggle_all_visibility)
        ui_signals.show_url_input.connect(self._on_show_url_input)
        ui_signals.open_url.connect(self._on_open_url)
        ui_signals.open_session_browser.connect(self._on_open_session_browser)
        ui_signals.set_transcription_language.connect(self._on_set_transcription_language)

    def _on_open_url(self, url: str):
        self.popup._apply_opacity(self._global_opacity)
        self.popup.load_url(url)

    @staticmethod
    def _on_open_session_browser():
        from ui.session_browser import open_session_browser

        open_session_browser()

    def _on_show_url_input(self):
        self.url_input.update_position()
        self.url_input._apply_opacity(self._global_opacity)
        self.url_input.show()
        self.url_input.raise_()
        self.url_input.activateWindow()
        self.url_input.line_edit.setFocus()

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and self._hide_from_capture:
            _apply_display_affinity(obj, exclude=True)
        return super().eventFilter(obj, event)

    def set_hide_from_capture(self, hide: bool):
        """Enable or disable capture-hiding on all managed overlay widgets."""
        self._hide_from_capture = hide

    def _on_toggle_panel(self, show):
        assert self.panel is not None
        if show is None:
            show = not self.panel.isVisible()
        if show:
            self.panel._apply_opacity(self._global_opacity)
            self.panel.show()
            self.panel.update_position()
        else:
            self.panel.hide()

    def _on_set_source(self, source_name, opacity):
        assert self.panel is not None
        self._global_opacity = opacity

        # Apply opacity to the panel and all its children
        self.panel._apply_opacity(opacity)
        self.panel.set_source(source_name)

        # Sync the language combo from config when switching to audio
        if source_name == "audio":
            from config.settings import load_config  # noqa: PLC0415
            cfg = load_config()
            self.panel.set_transcription_language_value(
                cfg.get("transcription_language", "en")
            )

        if source_name == "text":
            self.text_input._apply_opacity(opacity)
            self.text_input.show()
            self.text_input.update_position()
            self.text_input.text_edit.setFocus()
        else:
            self.text_input.hide()

    def _on_set_transcription_language(self, lang_code: str):
        """Persist transcription language to config and save."""
        from config.settings import load_config, save_config  # noqa: PLC0415
        cfg = load_config()
        cfg["transcription_language"] = lang_code
        save_config(cfg)

    def _on_set_processing_state(self, is_processing):
        self.panel.set_processing_state(is_processing)
        self.text_input.set_processing_state(is_processing)

    def _on_show_subtitle(self, text: str):
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"_on_show_subtitle called with text: {text}")
        assert self.subtitle is not None
        self.subtitle.add_subtitle(text)
        logger.info("_on_show_subtitle completed")

    def _on_update_subtitle(self, text: str, append: bool = False):
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"_on_update_subtitle called with text: {text}, append: {append}")
        assert self.subtitle is not None
        self.subtitle.update_last_subtitle(text, append=append)
        logger.info("_on_update_subtitle completed")

    def _on_clear_subtitles(self):
        assert self.subtitle is not None
        self.subtitle.clear_subtitles()

    def _on_toggle_all_visibility(self):
        """Toggle visibility of all overlay widgets.

        First press hides everything and saves state;
        second press restores the saved state.
        """
        widgets = {
            "popup": self.popup,
            "panel": self.panel,
            "text_input": self.text_input,
            "subtitle": self.subtitle,
        }

        if self._saved_visibility is None:
            # Save current visibility and hide all
            self._saved_visibility = {
                name: w.isVisible() for name, w in widgets.items() if w is not None
            }
            any_visible = any(self._saved_visibility.values())
            if any_visible:
                for w in widgets.values():
                    if w is not None:
                        w.hide()
            else:
                # Nothing was visible – clear saved state so next press is a no-op
                self._saved_visibility = None
        else:
            # Restore saved visibility
            for name, w in widgets.items():
                if w is not None and self._saved_visibility.get(name, False):
                    w.show()
            self._saved_visibility = None

    def get_subtitle_text(self, index: int) -> str:
        if self.subtitle is not None:
            return self.subtitle.get_subtitle_text(index)
        return ""


# Global instance for UI Manager. Will be initialized in main.py after QApplication.
ui_manager: UIManager | None = None


def init_ui_manager():
    global ui_manager
    if ui_manager is None:
        ui_manager = UIManager()


def set_app_callbacks(callbacks):
    global _app_callbacks
    _app_callbacks = callbacks


def set_hide_from_capture(hide: bool):
    """Enable or disable capture-hiding globally for all overlay widgets."""
    if ui_manager is not None:
        ui_manager.set_hide_from_capture(hide)


# --- Public API called from background threads ---
def toggle_control_panel(show=None):
    ui_signals.toggle_panel.emit(show)


def toggle_all_widgets():
    """Hide or unhide all overlay widgets."""
    ui_signals.toggle_all_visibility.emit()


def update_multi_state(in_progress):
    ui_signals.set_multi_state.emit(in_progress)


def set_active_source_ui(source_name, opacity=0.8):
    ui_signals.set_source.emit(source_name, opacity)


def set_app_processing_state(is_processing):
    ui_signals.set_processing_state.emit(is_processing)


def show_popup(text, auto_close=5000, opacity=0.8, is_result=False):
    ui_signals.show_popup.emit(
        {
            "text": text,
            "auto_close": auto_close,
            "opacity": opacity,
            "is_result": is_result,
        }
    )


def close_popup():
    ui_signals.close_popup.emit()


def share_response_screenshot():
    ui_signals.capture_popup_screenshot.emit()


def show_subtitle(text: str):
    """Show a subtitle line with real-time transcription."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"show_subtitle called with text: {text}")
    ui_signals.show_subtitle.emit(text)
    logger.info("show_subtitle signal emitted")


def update_subtitle(text: str, append: bool = False):
    """Update the most recent subtitle line instead of creating a new one."""
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"update_subtitle called with text: {text}, append: {append}")
    ui_signals.update_subtitle.emit(text, append)
    logger.info("update_subtitle signal emitted")


def clear_subtitles():
    """Clear all subtitle lines."""
    ui_signals.clear_subtitles.emit()


def get_subtitle_text(index: int) -> str:
    """Get the text of a subtitle by index (1 is newest)."""
    global ui_manager
    if ui_manager is not None:
        return ui_manager.get_subtitle_text(index)
    return ""


def output_result(text, output_modes, auto_close=False, opacity=0.8):
    if not output_modes:
        output_modes = ["popup"]

    # Audio is now handled by the AudioSink in the pipeline

    if "popup" in output_modes:
        show_popup(
            text,
            auto_close=5000 if auto_close else None,
            opacity=opacity,
            is_result=True,
        )


def get_active_source():
    import queue
    import threading
    from core.sources import get_active_source_instance

    app = QApplication.instance()
    if app and app.thread() == threading.current_thread():
        return get_active_source_instance()

    q = queue.Queue()
    ui_signals.request_active_source.emit(q)
    return q.get()


def _handle_request_coords(q):
    from ui.selector import get_coordinates

    # Pass the queue's put method directly as the callback
    get_coordinates(callback=q.put)
