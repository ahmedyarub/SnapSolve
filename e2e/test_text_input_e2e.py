import threading

def run_test_text_input(app_callbacks, status_update_callback=None):
    def _run():
        if 'text_submit' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Text Input Test...")
            app_callbacks['text_submit']("What is the fifth largest country in the world?")

    threading.Thread(target=_run, daemon=True).start()
