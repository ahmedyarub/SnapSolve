"""UrlInputWidget — quick URL entry overlay."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLineEdit,
)

from core.ui.mixins import DraggableWidgetMixin, _DragHandleBar
from core.ui.signals import ui_signals


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
