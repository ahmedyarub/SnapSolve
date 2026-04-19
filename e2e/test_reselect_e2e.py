import threading

import time

def run_test_reselect(app_callbacks, status_update_callback=None, cancel_event=None, completion_callback=None):
    def _run():
        if 'reselect' in app_callbacks:
            if status_update_callback:
                status_update_callback("Running Reselect Test...")
            app_callbacks['reselect']()

            # Simulated wait
            for i in range(5):
                if cancel_event and cancel_event.is_set():
                    if completion_callback:
                        completion_callback(False, "Cancelled")
                    return
                time.sleep(1)

            if completion_callback:
                completion_callback(True, "Reselect test completed")

    threading.Thread(target=_run, daemon=True).start()
