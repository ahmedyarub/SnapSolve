from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QCursor
import sys

class CoordinateSelector(QWidget):
    def __init__(self):
        super().__init__()
        # Translucent background
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(128, 128, 128, 76);") # ~0.3 alpha (255 * 0.3)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

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
                self.coordinates = [x1, y1, x2, y2]

            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.coordinates = None
            self.close()

    def paintEvent(self, event):
        if self.is_drawing and self.start_x is not None and self.end_x is not None:
            painter = QPainter(self)
            pen = QPen(QColor('red'))
            pen.setWidth(3)
            painter.setPen(pen)
            # Draw the interior (transparent since the widget is translucent)
            # The widget itself is styled, but paintEvent draws over it.
            # QWidget with WA_TranslucentBackground allows the stylesheet to act as background.
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            width = abs(self.end_x - self.start_x)
            height = abs(self.end_y - self.start_y)
            painter.drawRect(x1, y1, width, height)

def _get_coordinates_impl():
    # If QApplication is not already created, create a temporary one
    # Note: when integrated in main.py, QApplication will already exist.
    app = QApplication.instance()
    is_temp_app = False
    if not app:
        app = QApplication(sys.argv)
        is_temp_app = True

    selector = CoordinateSelector()
    # To cover multiple screens, we can get the virtual geometry
    screen_rect = app.primaryScreen().virtualGeometry()
    selector.setGeometry(screen_rect)
    selector.showFullScreen()

    # We must start a local event loop if we want this to block like Tkinter's mainloop() did
    from PyQt6.QtCore import QEventLoop
    loop = QEventLoop()
    selector.destroyed.connect(loop.quit)
    # also handle close event
    selector.closeEvent = lambda e: loop.quit()

    selector.show()
    loop.exec()

    coords = selector.coordinates

    if is_temp_app:
        app.quit()

    return coords

def get_coordinates():
    from core.output import selector_signals
    import queue
    q = queue.Queue()

    def on_ready(coords):
        q.put(coords)

    selector_signals.coords_ready.connect(on_ready)
    selector_signals.request_coords.emit()

    # Wait for the main thread to finish and emit the signal
    coords = q.get()
    selector_signals.coords_ready.disconnect(on_ready)
    return coords
