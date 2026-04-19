import threading
import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
from PyQt6.QtCore import Qt

class QAPanelWidget(QWidget):
    def __init__(self, app_callbacks):
        super().__init__()
        self.app_callbacks = app_callbacks

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(50, 20, 20, 230); border: 1px solid #744; border-radius: 8px;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # Close Btn
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { background-color: transparent; color: gray; border: none; } QPushButton:hover { color: white; }")
        close_btn.clicked.connect(self.hide)
        top_layout.addWidget(close_btn)
        self.layout.addLayout(top_layout)

        # Buttons
        self.buttons = {}
        btn_style = "QPushButton { background-color: rgba(80, 40, 40, 180); color: white; border: none; padding: 8px; border-radius: 4px; font-size: 14px; font-weight: bold;} QPushButton:hover { background-color: rgba(100, 50, 50, 220); } QPushButton:disabled { color: #777; }"

        def create_btn(name, text, action_func):
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(action_func)
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            return btn

        self.btn_reselect = create_btn('reselect', "Test: Reselect", self.run_test_reselect)
        self.btn_capture = create_btn('capture', "Test: Capture", self.run_test_capture)
        self.btn_multi = create_btn('multi', "Test: Multi-select", self.run_test_multi_select)
        self.btn_text = create_btn('text', "Test: Text Input", self.run_test_text_input)
        self.btn_all = create_btn('all', "Test: Run All", self.run_test_all)

        self.resize(200, 300)
        self.update_position()

    def update_position(self):
        # Position at top left
        self.move(20, 20)

    def run_test_reselect(self):
        from e2e.test_reselect_e2e import run_test_reselect
        run_test_reselect(self.app_callbacks)

    def run_test_capture(self):
        from e2e.test_capture_e2e import run_test_capture
        run_test_capture(self.app_callbacks)

    def run_test_multi_select(self):
        from e2e.test_multi_select_e2e import run_test_multi_select
        run_test_multi_select(self.app_callbacks)

    def run_test_text_input(self):
        from e2e.test_text_input_e2e import run_test_text_input
        run_test_text_input(self.app_callbacks)

    def run_test_all(self):
        def _run_all():
            self.run_test_text_input()
            time.sleep(10)
            self.run_test_capture()
            time.sleep(10)
            self.run_test_reselect()
            time.sleep(5)
            self.run_test_multi_select()
        threading.Thread(target=_run_all, daemon=True).start()
