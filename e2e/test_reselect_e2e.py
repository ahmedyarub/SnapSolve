import threading

def run_test_reselect(app_callbacks, status_update_callback=None):
    if 'reselect' in app_callbacks:
        if status_update_callback:
            status_update_callback("Running Reselect Test...")
        threading.Thread(target=app_callbacks['reselect'], daemon=True).start()
