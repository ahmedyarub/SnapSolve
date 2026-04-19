import time
import threading

def run_test_capture(app_callbacks, status_update_callback=None, cancel_event=None, completion_callback=None):
    import main
    from core.sources import ScreenshotSource
    def _run():
        from core.output import get_active_source
        active_src = get_active_source()

        # Switch to image source if needed
        if 'cycle_source' in app_callbacks and active_src is not None and active_src.name != "image":
            app_callbacks['cycle_source']()
            time.sleep(0.5)
            active_src = get_active_source()

        if active_src is None:
            if completion_callback:
                completion_callback(False, "Could not get active source")
            return

        original_get_text = active_src.get_text
        def mocked_get_text(*args, **kwargs):
            return "What is the fifth largest country in the world?"

        active_src.get_text = mocked_get_text

        if 'capture' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Capture Test...")
            app_callbacks['capture']()

        # Wait logic (could be improved to check UI state)
        for i in range(30):
            if cancel_event and cancel_event.is_set():
                active_src.get_text = original_get_text
                if completion_callback:
                    completion_callback(False, "Cancelled")
                return

            import main
            from core.output import ui_manager

            if ui_manager and ui_manager.popup and not ui_manager.popup.isHidden():
                if not main.is_processing:
                    active_src.get_text = original_get_text

                    from PyQt6.QtCore import QTimer
                    def check_and_hide():
                        def cb(html):
                            if "Brazil" in html or "brazil" in html.lower():
                                if status_update_callback:
                                    status_update_callback("Capture Test Success.")
                                if completion_callback:
                                    completion_callback(True, "Capture test success: found 'Brazil'")
                            else:
                                if status_update_callback:
                                    status_update_callback("Capture Test Failed: Did not find 'Brazil'.")
                                if completion_callback:
                                    completion_callback(False, "Response missing expected word 'Brazil'")
                            ui_manager.popup.hide()

                        ui_manager.popup.web_view.page().toHtml(cb)

                    QTimer.singleShot(0, check_and_hide)
                    return
            time.sleep(1)

        active_src.get_text = original_get_text
        if completion_callback:
            completion_callback(False, "Capture test timed out")

    threading.Thread(target=_run, daemon=True).start()
