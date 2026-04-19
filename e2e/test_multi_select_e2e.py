import time
import threading

def run_test_multi_select(app_callbacks, status_update_callback=None):
    import main
    from core.sources import ScreenshotSource
    def _run():
        from core.output import get_active_source
        active_src = get_active_source()

        # Switch to image source if needed
        if 'cycle_source' in app_callbacks and active_src and active_src.name != "image":
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

    threading.Thread(target=_run, daemon=True).start()
