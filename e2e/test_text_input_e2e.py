import threading
import time
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

def run_test_text_input(app_callbacks, status_update_callback=None, cancel_event=None, completion_callback=None):
    def _run():
        if status_update_callback:
            status_update_callback("Running Text Input Test via UI interaction...")

        import main
        from core.sources import TextSource
        from core.output import set_active_source_ui, ui_manager, get_active_source

        # Switch source to text to ensure the text panel is visible
        # We need to cycle source if we are NOT using TextSource currently.
        active_src = get_active_source()
        if 'cycle_source' in app_callbacks and active_src is not None and active_src.name != "text":
            app_callbacks['cycle_source']()
            time.sleep(1)

        if cancel_event and cancel_event.is_set():
            if completion_callback:
                completion_callback(False, "Cancelled")
            return

        # Ensure UI Manager text_input is visible
        assert ui_manager is not None, "UI Manager must be initialized before running e2e tests"
        if ui_manager.text_input:
            text_input_widget = ui_manager.text_input

            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication

            def interact_with_ui():
                if cancel_event and cancel_event.is_set():
                    return
                text_edit = text_input_widget.text_edit
                text_edit.setFocus()

                # QTest requires events to be pumped. During a real execution without returning to the event loop,
                # QTest might hang or drop. It's safer to post events manually or ensure the window is active.
                # Here we use setPlainText as a more robust fallback if QtTest fails.
                try:
                    from PyQt6.QtTest import QTest
                    QTest.keyClicks(text_edit.viewport(), "What is the fifth largest country in the world?", delay=10)
                except Exception:
                    text_edit.setPlainText("What is the fifth largest country in the world?")

                # Wait 1 second before submitting
                # We can't use time.sleep in the UI thread, so we schedule the submit
                def _submit():
                    if cancel_event and cancel_event.is_set():
                        if completion_callback:
                            completion_callback(False, "Cancelled")
                        return

                    # Alternatively we can simulate return
                    # enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
                    # text_input_widget.eventFilter(text_edit, enter_event)
                    # Or just call the callback directly if simulating key events is flaky.
                    # Since Qt event simulation can be flaky in background E2E runs:
                    if 'text_submit' in app_callbacks:
                        app_callbacks['text_submit'](text_edit.toPlainText().strip())
                        text_edit.clear()

                QTimer.singleShot(1000, _submit)

            # We need to wait a second before typing as requested
            time.sleep(1)

            if cancel_event and cancel_event.is_set():
                if completion_callback:
                    completion_callback(False, "Cancelled")
                return

            # The QTimer.singleShot doesn't work well without a running event loop in testing environments
            # Or if called directly from a background thread.
            # We use invokeMethod to guarantee it executes in the main thread correctly.
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(text_input_widget, "setFocus", Qt.ConnectionType.QueuedConnection)
            # It's better to encapsulate this all into a safe GUI call
            QTimer.singleShot(0, interact_with_ui)

            def wait_for_response():
                assert ui_manager is not None
                timeout = 30
                start_time = time.time()
                # Initial wait to let processing flag be set
                time.sleep(1)
                while time.time() - start_time < timeout:
                    if cancel_event and cancel_event.is_set():
                        if completion_callback:
                            completion_callback(False, "Cancelled")
                        return

                    if ui_manager.popup and not ui_manager.popup.isHidden():
                        # We wait for processing to finish, processing is handled by set_processing state
                        if not main.is_processing:
                            # It's a UI element so must be interacted with in main thread
                            from PyQt6.QtCore import QTimer

                            def check_and_hide():
                                # Evaluate popup contents via JavaScript to find "Brazil"
                                def cb(html):
                                    if "Brazil" in html or "brazil" in html.lower():
                                        if status_update_callback:
                                            status_update_callback("Text Input Test Success.")
                                        if completion_callback:
                                            completion_callback(True, "Text input success: found 'Brazil'")
                                    else:
                                        if status_update_callback:
                                            status_update_callback("Text Input Test Failed: Did not find 'Brazil'.")
                                        if completion_callback:
                                            completion_callback(False, "Response missing expected word 'Brazil'")
                                    ui_manager.popup.hide()

                                ui_manager.popup.web_view.page().toHtml(cb)

                            QTimer.singleShot(0, check_and_hide)
                            return
                    time.sleep(0.5)
                # If we get here, it timed out
                if status_update_callback:
                    status_update_callback("Text Input Test Failed (Timeout).")
                from core.output import show_popup
                show_popup("Error: Text input test timed out waiting for response.", auto_close=3000)
                if completion_callback:
                    completion_callback(False, "Timeout")

            threading.Thread(target=wait_for_response, daemon=True).start()

    threading.Thread(target=_run, daemon=True).start()
