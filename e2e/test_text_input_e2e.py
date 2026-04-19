import threading
import time
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

def run_test_text_input(app_callbacks, status_update_callback=None):
    def _run():
        if status_update_callback:
            status_update_callback("Running Text Input Test via UI interaction...")

        import main
        from core.sources import TextSource
        from core.output import set_active_source_ui, ui_manager

        # Switch source to text to ensure the text panel is visible
        if 'cycle_source' in app_callbacks and not isinstance(main.active_source_instance, TextSource):
            app_callbacks['cycle_source']()
            time.sleep(0.5)

        # Ensure UI Manager text_input is visible
        if ui_manager and ui_manager.text_input:
            text_input_widget = ui_manager.text_input

            # Type text
            text_edit = text_input_widget.text_edit
            # Send text to QTextEdit via PyQt methods in the main thread (thread-safe way or signal)
            # Since we're in a thread we'll use QMetaObject.invokeMethod, but direct setText is simpler
            # However, for pure e2e, we should simulate key events, but Qt allows thread-safe string appending
            # Wait, Qt widgets must be modified from main thread. We use app.postEvent or simple signal.

            # We can use QTimer to trigger it safely on the main thread
            from PyQt6.QtCore import QTimer
            def interact_with_ui():
                text_edit.setPlainText("What is the fifth largest country in the world?")
                text_edit.setFocus()

                # Simulate pressing Enter
                enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
                text_input_widget.eventFilter(text_edit, enter_event)

            QTimer.singleShot(0, interact_with_ui)

    threading.Thread(target=_run, daemon=True).start()
