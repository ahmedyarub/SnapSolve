"""RecordButton — push-to-talk / toggle record button with long-press support."""
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QPushButton


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
