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
        from core.output import set_active_source_ui, ui_manager, get_active_source

        # Switch source to text to ensure the text panel is visible
        # We need to cycle source if we are NOT using TextSource currently.
        active_src = get_active_source()
        if 'cycle_source' in app_callbacks and active_src and active_src.name != "text":
            app_callbacks['cycle_source']()
            time.sleep(0.5)

        # Ensure UI Manager text_input is visible
        if ui_manager and ui_manager.text_input:
            text_input_widget = ui_manager.text_input

            from PyQt6.QtCore import QTimer
            def interact_with_ui():
                text_edit = text_input_widget.text_edit
                text_edit.setPlainText("What is the fifth largest country in the world?")
                text_edit.setFocus()

                # We can post an event or call the callback directly
                # However, eventFilter checks event type so let's properly post an event or invoke the callback
                if 'text_submit' in app_callbacks:
                    app_callbacks['text_submit'](text_edit.toPlainText().strip())
                    text_edit.clear()

            QTimer.singleShot(0, interact_with_ui)

            def wait_for_response():
                timeout = 10
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if ui_manager.popup and not ui_manager.popup.isHidden():
                        # We wait for processing to finish, processing is handled by set_processing state
                        if not main.is_processing:
                            ui_manager.popup.hide()
                            return
                    time.sleep(0.5)
                # If we get here, it timed out
                from core.output import show_popup
                show_popup("Error: Text input test timed out waiting for response.", auto_close=3000)

            threading.Thread(target=wait_for_response, daemon=True).start()

    threading.Thread(target=_run, daemon=True).start()
