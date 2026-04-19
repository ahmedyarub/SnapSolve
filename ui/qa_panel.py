import threading
import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
from PyQt6.QtCore import Qt

class QAPanelWidget(QWidget):
    def __init__(self, app_callbacks):
        super().__init__()
        self.app_callbacks = app_callbacks
        self.active_test: str | None = None
        self.cancel_event: threading.Event | None = None
        self.original_button_texts = {}

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
            btn.clicked.connect(lambda _, n=name, f=action_func: self.handle_button_click(n, f))
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            self.original_button_texts[name] = text
            return btn

        from e2e.test_reselect_e2e import run_test_reselect
        from e2e.test_capture_e2e import run_test_capture
        from e2e.test_multi_select_e2e import run_test_multi_select
        from e2e.test_text_input_e2e import run_test_text_input

        self.btn_reselect = create_btn('reselect', "Test: Reselect", run_test_reselect)
        self.btn_capture = create_btn('capture', "Test: Capture", run_test_capture)
        self.btn_multi = create_btn('multi', "Test: Multi-select", run_test_multi_select)
        self.btn_text = create_btn('text', "Test: Text Input", run_test_text_input)
        self.btn_all = create_btn('all', "Test: Run All", self.run_test_all)

        self.resize(200, 300)
        self.update_position()

    def update_position(self):
        # Position at top left
        self.move(20, 20)

    def set_test_btn_text(self, name, text):
        if name in self.buttons:
            self.buttons[name].setText(text)

    def handle_button_click(self, name, action_func):
        if self.active_test == name:
            # Cancel the active test
            if self.cancel_event:
                self.cancel_event.set()
            return

        if self.active_test is not None:
            # Another test is already running
            return

        # Start new test
        self.active_test = name
        self.cancel_event = threading.Event()

        # Update UI: active button to "Cancel", others disabled
        for btn_name, btn in self.buttons.items():
            if btn_name == name:
                btn.setText("Cancel Test")
            else:
                btn.setEnabled(False)

        def completion_callback(success, msg):
            from core.output import show_popup
            # Re-enable all buttons and restore names on the main thread via post or a signal.
            # Easiest way in PyQt safely from thread is to use QTimer
            from PyQt6.QtCore import QTimer
            def restore_ui():
                self.active_test = None
                self.cancel_event = None
                for btn_name, btn in self.buttons.items():
                    btn.setText(self.original_button_texts[btn_name])
                    btn.setEnabled(True)
                show_popup(f"Test '{name}' finished:\n{msg}", auto_close=4000)

            QTimer.singleShot(0, restore_ui)

        # Call the test function
        action_func(
            self.app_callbacks,
            lambda msg: self.set_test_btn_text(name, f"Cancel ({msg})"),
            self.cancel_event,
            completion_callback
        )

    def run_test_all(self, app_callbacks, status_update, cancel_event, completion_callback):
        from e2e.test_reselect_e2e import run_test_reselect
        from e2e.test_capture_e2e import run_test_capture
        from e2e.test_multi_select_e2e import run_test_multi_select
        from e2e.test_text_input_e2e import run_test_text_input

        def _run_all():
            tests = [
                ("Text Input", run_test_text_input),
                ("Capture", run_test_capture),
                ("Reselect", run_test_reselect),
                ("Multi Select", run_test_multi_select)
            ]

            for test_name, test_func in tests:
                if cancel_event.is_set():
                    completion_callback(False, "Run All cancelled")
                    return

                status_update(f"Running: {test_name}")

                # Create a local sub-event for this test so we can wait for it
                test_done = threading.Event()
                test_success = [False]
                test_msg = [""]

                def sub_completion(s, m):
                    test_success[0] = s
                    test_msg[0] = m
                    test_done.set()

                test_func(app_callbacks, lambda msg: None, cancel_event, sub_completion)
                test_done.wait()

                if not test_success[0] and not cancel_event.is_set():
                    completion_callback(False, f"Test {test_name} failed: {test_msg[0]}")
                    return

                time.sleep(2)

            if cancel_event.is_set():
                completion_callback(False, "Cancelled during Run All")
            else:
                completion_callback(True, "All tests passed successfully.")

        threading.Thread(target=_run_all, daemon=True).start()
