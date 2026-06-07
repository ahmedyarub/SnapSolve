"""PopupWidget — rich Markdown/LaTeX/Mermaid popup overlay."""
import json
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QUrl, QTimer
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)

from core.ui.ide_integration import _PopupWebPage
from core.ui.mixins import ResizableWidgetMixin, DraggableWidgetMixin


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
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: white; border: none; font-size: 20px; font-weight: bold; } QPushButton:hover { color: red; }"
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
        _assets_dir = Path(__file__).resolve().parent.parent / "web_assets"
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
