from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor
import sys

class CoordinateSelector(QWidget):
    def __init__(self, callback=None, loop=None):
        super().__init__()
        self.callback = callback
        self.loop = loop

        # Frameless and Always on Top
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self.is_drawing = False
        self.coordinates = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_x = int(event.position().x())
            self.start_y = int(event.position().y())
            self.end_x = self.start_x
            self.end_y = self.start_y
            self.is_drawing = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_drawing:
            self.end_x = int(event.position().x())
            self.end_y = int(event.position().y())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.end_x = int(event.position().x())
            self.end_y = int(event.position().y())
            self.is_drawing = False

            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            x2 = max(self.start_x, self.end_x)
            y2 = max(self.start_y, self.end_y)

            if x2 - x1 > 10 and y2 - y1 > 10:
                # Apply DPI scaling back to physical pixels for PIL.ImageGrab
                ratio = self.window().windowHandle().screen().devicePixelRatio() if self.window().windowHandle() else QApplication.primaryScreen().devicePixelRatio()
                self.coordinates = [int(x1 * ratio), int(y1 * ratio), int(x2 * ratio), int(y2 * ratio)]

            self.finish()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.coordinates = None
            self.finish()

    def finish(self):
        if self.callback:
            self.callback(self.coordinates)
        if self.loop:
            self.loop.quit()
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Fill the entire screen with a semi-transparent dark gray mask
        painter.fillRect(self.rect(), QColor(50, 50, 50, 76))

        if self.is_drawing and self.start_x is not None and self.end_x is not None:
            # Draw the red selection rectangle outline
            pen = QPen(QColor('red'))
            pen.setWidth(3)
            painter.setPen(pen)

            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            width = abs(self.end_x - self.start_x)
            height = abs(self.end_y - self.start_y)

            # To clear the mask inside the selection box, we can change composition mode
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(x1, y1, width, height, Qt.GlobalColor.transparent)

            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawRect(x1, y1, width, height)

_active_selector = None

def _get_coordinates_impl(callback=None):
    global _active_selector
    app = QApplication.instance()
    is_temp_app = False
    if not app:
        app = QApplication(sys.argv)
        is_temp_app = True

    if callback:
        # Async mode
        def on_close(coords):
            global _active_selector
            callback(coords)
            _active_selector = None
            if is_temp_app:
                app.quit()

        selector = CoordinateSelector(callback=on_close)
        _active_selector = selector
        screen_rect = app.primaryScreen().virtualGeometry()
        selector.setGeometry(screen_rect)
        selector.showFullScreen()
        selector.raise_()
        selector.activateWindow()
        selector.setFocus()
    else:
        # Blocking mode for first run
        from PyQt6.QtCore import QEventLoop
        loop = QEventLoop()
        selector = CoordinateSelector(loop=loop)
        screen_rect = app.primaryScreen().virtualGeometry()
        selector.setGeometry(screen_rect)
        selector.showFullScreen()
        selector.raise_()
        selector.activateWindow()
        selector.setFocus()
        loop.exec()

        coords = selector.coordinates
        if is_temp_app:
            app.quit()
        return coords

def get_coordinates(callback=None):
    from core.output import selector_signals
    import queue
    import threading
    from PyQt6.QtWidgets import QApplication

    # Check if we are already in the main Qt thread. If so, use blocking loop.
    app = QApplication.instance()
    if app and app.thread() == threading.current_thread():
        coords = _get_coordinates_impl()
        if callback:
            callback(coords)
        return coords

    q = queue.Queue()

    # Send the queue itself to the main thread via the signal
    selector_signals.request_coords.emit(q)

    # Wait for the main thread to put the result in the queue
    coords = q.get()

    if callback:
        callback(coords)

    return coords
