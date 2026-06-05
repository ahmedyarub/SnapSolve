"""Mixins for frameless window interaction — drag-to-move, resize handles, and drag handle bar."""
from PyQt6.QtCore import Qt, QPoint, QSize, QRect
from PyQt6.QtGui import QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QLabel,
)


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
