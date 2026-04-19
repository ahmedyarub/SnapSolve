import time
import threading

def run_test_capture(app_callbacks, status_update_callback=None):
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
            return

        original_get_text = active_src.get_text
        def mocked_get_text(*args, **kwargs):
            return "What is the fifth largest country in the world?"

        active_src.get_text = mocked_get_text

        if 'capture' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Capture Test...")
            app_callbacks['capture']()

        time.sleep(3)
        active_src.get_text = original_get_text

    threading.Thread(target=_run, daemon=True).start()
