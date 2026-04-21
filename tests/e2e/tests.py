import json
import os
import subprocess
import sys
import threading
import time
import socket

import pyautogui
import pyperclip

# --- Configuration variables ---
WORKING_DIR = r"E:\Python\SnapSolve"
CYCLE_SOURCE = 'button_cycle_source.png'
RESELECT_SOURCE = 'button_reselect.png'
CAPTURE_SOURCE = 'button_capture.png'
START_MULTISELECT_SOURCE = 'button_start_multiselect.png'
END_MULTISELECT_SOURCE = 'button_end_multiselect.png'
TARGET_WORD_BASIC = 'Brazil'
TARGET_WORD_PROGRAMMING = 'class'
PROMPT_X, PROMPT_Y = 1900, 1900
POPUP_X, POPUP_Y = 3500, 1800
BASIC_QUESTION = "What is the fifth largest country in the world?"
PROGRAMMING_QUESTION1 = "Write a Python hello world."
PROGRAMMING_QUESTION2 = "Use classes"

# --- Subprocess Configuration ---
SECOND_SCRIPT_PATH = 'main.py'
SECOND_SCRIPT_ARGS = [
    '--active-profile=quick',
    '--popup-opacity=1.0'
]
SERVICE_SCRIPT_PATH = os.path.join('services', 'ocr_service.py')


def run_tests():
    app_process, service_process = init_tests()

    if not app_process:
        cleanup(app_process, service_process)
        return

    try:
        time.sleep(3)

        test_text_source()

        # FIXME we don't need to wait that long. The buttons are disabled so we should cancel the current operation to re-enable them
        time.sleep(10)

        test_image_source()
    finally:
        cleanup(app_process, service_process)


def test_text_source():
    if not click_button(CYCLE_SOURCE):
        return

    # 2. Wait for a second
    time.sleep(1)

    # 3. Click on a specific screen position
    print(f"Clicking specific position ({PROMPT_X}, {PROMPT_Y})...")
    pyautogui.click(x=PROMPT_X, y=PROMPT_Y)

    # 4. Paste the text instead of typing
    print(f"Pasting the question...")
    pyperclip.copy(BASIC_QUESTION)  # Send the text to your clipboard
    time.sleep(0.1)  # Tiny pause to let the clipboard register
    pyautogui.hotkey('ctrl', 'v')  # Paste it (Use 'command', 'v' on Mac)

    # 5. Click enter
    pyautogui.press('enter')

    # 6. Wait
    time.sleep(2)

    if find_text(TARGET_WORD_BASIC):
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_BASIC}' was found in the text!")
    else:
        print(f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found after multiple retries.")


def poll_port(host, port, timeout=30):
    print(f"Polling for service on {host}:{port}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                print(f"Service on {host}:{port} is ready.")
                return True
        except (socket.timeout, ConnectionRefusedError, ConnectionResetError):
            time.sleep(1)
    print(f"Service on {host}:{port} did not become ready within {timeout} seconds.")
    return False


def test_image_source():
    if not poll_port("127.0.0.1", 8000):
        print("OCR service not available. Aborting image tests.")
        return

    # 1. Switch to image source
    if not click_button(CYCLE_SOURCE):
        return

    # 2. Wait for a second
    time.sleep(1)

    test_capture()

    time.sleep(1)

    test_multi_capture()


def test_capture():
    ui_process = show_test_ui(ui_data=[
        {"text": BASIC_QUESTION, "x": 500, "y": 300}
    ])

    time.sleep(2)

    if not click_button(RESELECT_SOURCE):
        return

    time.sleep(1)

    pyautogui.moveTo(x=1000, y=700)

    time.sleep(1)
    pyautogui.dragTo(x=3400, y=1100, duration=2)

    time.sleep(1)
    if not click_button(CAPTURE_SOURCE):
        return

    time.sleep(1)

    ui_process.kill()
    ui_process.wait()  # Ensure it has

    if find_text(TARGET_WORD_BASIC):
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_BASIC}' was found in the text!")
    else:
        print(f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found after multiple retries.")


def test_multi_capture():
    ui_process = show_test_ui(ui_data=[
        {"text": PROGRAMMING_QUESTION1, "x": 500, "y": 100},
        {"text": PROGRAMMING_QUESTION2, "x": 500, "y": 400}
    ])

    time.sleep(2)

    if not click_button(START_MULTISELECT_SOURCE):
        return

    # Select first text
    time.sleep(1)
    pyautogui.moveTo(x=1000, y=200)

    time.sleep(1)
    pyautogui.dragTo(x=2600, y=400, duration=1)

    if not click_button(START_MULTISELECT_SOURCE):
        return

    time.sleep(1)
    pyautogui.moveTo(x=1000, y=900)

    time.sleep(1)
    pyautogui.dragTo(x=2500, y=1200, duration=1)

    time.sleep(1)
    if not click_button(END_MULTISELECT_SOURCE):
        return

    time.sleep(1)

    ui_process.kill()
    ui_process.wait()  # Ensure it has

    if find_text(TARGET_WORD_PROGRAMMING):
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_PROGRAMMING}' was found in the text!")
    else:
        print(f"\n❌ FAILURE: The word '{TARGET_WORD_PROGRAMMING}' was NOT found after multiple retries.")


def find_text(text):
    retries = 0
    while retries < 10:
        # 7. Click on another text box
        print(f"Clicking second text box at ({POPUP_X}, {POPUP_Y})...")
        pyautogui.click(x=POPUP_X, y=POPUP_Y)

        # 8. Copy the text
        print("Selecting and copying text...")
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.5)

        copied_text = pyperclip.paste()
        print(f"\n--- Copied Text ---\n{copied_text}\n-------------------")

        # 9. Look for a specific word in its text
        if text.lower() in copied_text.lower():
            return True
        else:
            print(f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found. Retrying")
            retries += 1

    return False


def show_test_ui(ui_data):
    json_data = json.dumps(ui_data)

    print("Launching the UI script...")

    # 2. Start the UI script in a separate process
    # sys.executable ensures it uses your current Python environment
    command = [sys.executable, 'display_ui.py', '--data', json_data]
    return subprocess.Popen(command)


def init_tests():
    # 1. Minimize all windows
    minimize_all_windows()

    # 2. Start the service
    service_process = launch_service()

    # 3. Start the other script in a separate process
    app_process = launch_app()

    return app_process, service_process


def cleanup(main_app, service_process):
    if main_app is not None:
        print("\nCleaning up: Terminating the background process...")
        main_app.terminate()  # Sends a signal to the process asking it to close
        main_app.wait()  # Waits to ensure the process actually closes
        print("Background process safely closed.")

    if service_process is not None:
        print("\nCleaning up: Terminating the service process...")
        service_process.terminate()
        service_process.wait()
        print("Service process safely closed.")


def launch_service():
    print(f"Launching '{SERVICE_SCRIPT_PATH}' in the background...")
    try:
        if not os.path.exists(WORKING_DIR):
            print(f"Error: The directory '{WORKING_DIR}' does not exist.")
            return None

        command_list = [sys.executable, SERVICE_SCRIPT_PATH]

        env = os.environ.copy()
        env['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

        launched_process = subprocess.Popen(
            command_list,
            cwd=WORKING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        print("Service script launched.")

        def read_output():
            for line in iter(launched_process.stdout.readline, ''):
                print(f"[OCR Service] {line}", end='')

        threading.Thread(target=read_output, daemon=True).start()

        return launched_process
    except Exception as e:
        print(f"Failed to launch the service script: {e}")
        return None


def launch_app():
    print(f"Launching '{SECOND_SCRIPT_PATH}' in the background...")
    try:
        if not os.path.exists(WORKING_DIR):
            print(f"Error: The directory '{WORKING_DIR}' does not exist.")
            return None

        command_list = [sys.executable, SECOND_SCRIPT_PATH] + SECOND_SCRIPT_ARGS

        launched_process = subprocess.Popen(
            command_list,
            cwd=WORKING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        print("Second script launched. Waiting for initialization...")

        is_initialized = threading.Event()

        def read_output():
            for line in iter(launched_process.stdout.readline, ''):
                print(line, end='')  # Print the output in real-time
                if "Initialization done." in line:
                    is_initialized.set()

        threading.Thread(target=read_output, daemon=True).start()

        # Wait for the initialization message with a timeout
        if is_initialized.wait(timeout=30):
            print("App is fully loaded.")
            return launched_process
        else:
            print("Error: App initialization timed out.")
            launched_process.terminate()
            return None

    except Exception as e:
        print(f"Failed to launch the second script: {e}")
        return None


def click_button(image):
    try:
        button_location = pyautogui.locateCenterOnScreen(image, confidence=0.8)

        if button_location is None:
            print("Could not find the button on the screen.")
            return False

        # 4. Click on it
        print("Button found! Clicking...")
        pyautogui.click(button_location)

        return True
    except pyautogui.ImageNotFoundException:
        print("Could not find the button on the screen.")

        return False


def minimize_all_windows():
    print("Minimizing all windows...")
    pyautogui.hotkey('win', 'd')  # Use ('command', 'f3') for Mac
    time.sleep(1)


if __name__ == "__main__":
    run_tests()
