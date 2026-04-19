import time
import threading

def run_test_multi_select(app_callbacks, status_update_callback=None, cancel_event=None, completion_callback=None):
    import main
    from core.sources import ScreenshotSource
    def _run():
        from core.output import get_active_source
        active_src = get_active_source()

        # Switch to image source if needed
        if 'cycle_source' in app_callbacks and active_src is not None and active_src.name != "image":
            app_callbacks['cycle_source']()
            time.sleep(0.5)

        if not main.is_multi_capturing:
            main.is_multi_capturing = True
            main.multi_capture_texts = []
            from core.output import update_multi_state
            update_multi_state(True)

        main.multi_capture_texts.append("Write a Python hello world")
        main.multi_capture_texts.append("Use classes")

        if 'end_multi_capture' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Multi-Select Test...")
            app_callbacks['end_multi_capture']()

        for i in range(30):
            if cancel_event and cancel_event.is_set():
                if completion_callback:
                    completion_callback(False, "Cancelled")
                return

            from core.output import ui_manager

            if ui_manager and ui_manager.popup and not ui_manager.popup.isHidden():
                if not main.is_processing:
                    from PyQt6.QtCore import QTimer
                    def check_and_hide():
                        def cb(html):
                            if "class " in html:
                                if status_update_callback:
                                    status_update_callback("Multi-Select Test Success.")
                                if completion_callback:
                                    completion_callback(True, "Multi-Select test success: found python 'class'")
                            else:
                                if status_update_callback:
                                    status_update_callback("Multi-Select Test Failed: Did not find 'class'.")
                                if completion_callback:
                                    completion_callback(False, "Response missing expected word 'class'")
                            ui_manager.popup.hide()

                        ui_manager.popup.web_view.page().toHtml(cb)

                    QTimer.singleShot(0, check_and_hide)
                    return
            time.sleep(1)

        if completion_callback:
            completion_callback(False, "Multi-select test timed out")

    threading.Thread(target=_run, daemon=True).start()
