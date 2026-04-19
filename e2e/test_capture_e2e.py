import time
import threading

def run_test_capture(app_callbacks, status_update_callback=None):
    import main
    from core.sources import ScreenshotSource
    def _run():
        original_get_text = main.active_source_instance.get_text
        def mocked_get_text(*args, **kwargs):
            return "What is the fifth largest country in the world?"

        # Switch to image source if needed
        if 'cycle_source' in app_callbacks and not isinstance(main.active_source_instance, ScreenshotSource):
            app_callbacks['cycle_source']()
            time.sleep(0.5)

        main.active_source_instance.get_text = mocked_get_text

        if 'capture' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Capture Test...")
            app_callbacks['capture']()

        time.sleep(3)
        main.active_source_instance.get_text = original_get_text

    threading.Thread(target=_run, daemon=True).start()
