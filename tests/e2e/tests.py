import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time

import keyboard
import pyautogui
import pyperclip
import speech_recognition as sr

# --- Configuration variables ---
WORKING_DIR = r"../../"
CANCEL_SOURCE = 'images/button_cancel.png'
CYCLE_SOURCE = 'images/button_cycle_source.png'
RESELECT_SOURCE = 'images/button_reselect.png'
CAPTURE_SOURCE = 'images/button_capture.png'
START_MULTISELECT_SOURCE = 'images/button_start_multiselect.png'
END_MULTISELECT_SOURCE = 'images/button_end_multiselect.png'
TARGET_WORD_BASIC = 'Brazil'
TARGET_WORD_PROGRAMMING = 'class'
PROMPT_X, PROMPT_Y = 1900, 1900
POPUP_X, POPUP_Y = 3500, 1800
BASIC_QUESTION = "What is the fifth largest country in the world? Answer with one word only."
PROGRAMMING_QUESTION1 = "Write a Python hello world."
PROGRAMMING_QUESTION2 = "Use classes"
TTS_INPUT_DEVICE_NAME = "CABLE Output (VB-Audio Virtual"
TTS_OUTPUT_DEVICE_NAME = "CABLE Input (VB-Audio Virtual C"

# --- Subprocess Configuration ---
MAIN_SCRIPT_PATH = 'main.py'
MAIN_SCRIPT_ARGS = [
    '--active-profile=quick',
    '--popup-opacity=1.0',
    f'--tts-output-device-name={TTS_OUTPUT_DEVICE_NAME}',
    '--default-source=text'
]
SERVICE_SCRIPT_PATH = os.path.join('services', 'ocr_service.py')

# --- Global variables for background recording ---
_stop_recording_event = threading.Event()
_recorded_audio_queue = queue.Queue()  # To pass the AudioData object from recording thread to main thread
_recording_thread: threading.Thread | None = None  # To hold the reference to the recording thread


def get_microphone_index(target_name: str) -> int | None:
    """
    Searches available microphones for a given name and returns its index.
    """
    # Fetch the list of all available audio devices recognized by PyAudio/SpeechRecognition
    mic_list = sr.Microphone.list_microphone_names()

    for index, name in enumerate(mic_list):
        # Case-insensitive partial match
        if target_name.lower() in name.lower():
            print(f"Matched: [{index}] {name}")
            return index

    print(f"Error: No device matching '{target_name}' was found.")
    print("Available devices:", mic_list)
    return None


def _record_audio_in_background(stop_event, audio_queue, device_index):
    """Records audio continuously in the background."""

    frames = []
    try:
        print("[Recorder] Background audio recording started.")
        # Instantiate Microphone inside the thread's context for proper resource management
        with sr.Microphone(device_index=device_index) as source:
            # Access the underlying PyAudio stream from the source object
            stream = source.stream

            if stream is None:
                print("[Recorder] No audio stream found.")
                return

            while not stop_event.is_set():
                try:
                    # Read directly from the stream provided by sr.Microphone
                    data = stream.read(source.CHUNK)
                    frames.append(data)
                except Exception as e:
                    print(f"[Recorder] Error reading audio stream: {e}")
                    break

            # The stream will be closed by the 'with sr.Microphone() as source:' context manager
            # when the loop exits and the 'with' block finishes.

            if frames:
                audio_data = sr.AudioData(b''.join(frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                audio_queue.put(audio_data)
            print("[Recorder] Background audio recording stopped.")
    except Exception as e:
        print(f"[Recorder] Error during background recording setup or execution: {e}")


def run_tests():
    def exit_tests():
        print("\nExit shortcut pressed. Cleaning up and exiting...")
        # Ensure recording is stopped if tests are exited prematurely
        _stop_recording_event.set()
        if _recording_thread and _recording_thread.is_alive():
            _recording_thread.join(timeout=2)
        cleanup(app_process, service_process)
        os._exit(0)

    keyboard.add_hotkey('ctrl+shift+alt+q', exit_tests)

    app_process, service_process = init_tests()

    if not app_process:
        cleanup(app_process, service_process)
        return

    poll_button(CYCLE_SOURCE)

    try:
        test_text_source()
        test_image_source()
    finally:
        # Ensure recording is stopped even if test_text_source fails
        _stop_recording_event.set()
        if _recording_thread and _recording_thread.is_alive():
            _recording_thread.join(timeout=2)
        cleanup(app_process, service_process)


def test_text_source():
    global _stop_recording_event, _recorded_audio_queue, _recording_thread

    # --- Start Background Recording ---
    _stop_recording_event.clear()
    # Clear the queue for a new recording session
    while not _recorded_audio_queue.empty():
        try:
            _recorded_audio_queue.get_nowait()
        except queue.Empty:
            pass

    r: sr.Recognizer = sr.Recognizer()  # Recognizer can be created once and passed

    mic_index = get_microphone_index(TTS_INPUT_DEVICE_NAME)

    _recording_thread = threading.Thread(target=_record_audio_in_background,
                                         args=(_stop_recording_event, _recorded_audio_queue, mic_index))
    _recording_thread.daemon = True  # Allow main program to exit even if thread is still running
    _recording_thread.start()
    print("Started background recording thread for TTS test.")
    # --- End Start Background Recording ---

    # 3. Click on a specific screen position
    print(f"Clicking specific position ({PROMPT_X}, {PROMPT_Y})...")
    pyautogui.click(x=PROMPT_X, y=PROMPT_Y)

    # 4. Paste the text instead of typing
    print(f"Pasting the question...")
    pyperclip.copy(BASIC_QUESTION)
    time.sleep(0.1)
    pyautogui.hotkey('ctrl', 'v')

    # 5. Click enter
    pyautogui.press('enter')

    # 6. Wait
    time.sleep(2)

    found_target_word = find_text(TARGET_WORD_BASIC)

    # Wait for 3 seconds before stopping the recording
    time.sleep(3)

    # --- Stop Background Recording ---
    _stop_recording_event.set()  # Signal the recording thread to stop
    if _recording_thread and _recording_thread.is_alive():
        print("Waiting for background recording thread to finish...")
        _recording_thread.join(timeout=5)  # Wait for the thread to finish, with a timeout
        if _recording_thread.is_alive():
            print("Warning: Background recording thread did not terminate in time.")
    print("Signaled background recording thread to stop.")
    # --- End Stop Background Recording ---

    if found_target_word:
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_BASIC}' was found in the text!")
    else:
        print(f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found after multiple retries.")
        return  # End test prematurely if target word not found

    # --- TTS Recognition Test (Process recorded audio) ---
    print("\n--- Starting TTS Recognition Test (Processing recorded audio) ---")
    audio_filename = "recorded_tts_output.wav"

    try:
        if not _recorded_audio_queue.empty():
            audio = _recorded_audio_queue.get(timeout=5)  # Get the recorded AudioData object, with a timeout

            with open(audio_filename, "wb") as f:
                f.write(audio.get_wav_data())
            print(f"Audio recorded to {audio_filename}")

            # Now, recognize the speech
            # Use the AudioData object directly with the recognizer
            recognized_text = r.recognize_google(audio)
            print(f"Recognized text: '{recognized_text}'")

            if TARGET_WORD_BASIC.lower() in recognized_text.lower():
                print(f"\n✅ SUCCESS (TTS): The word '{TARGET_WORD_BASIC}' was found in the spoken audio!")
            else:
                print(f"\n❌ FAILURE (TTS): The word '{TARGET_WORD_BASIC}' was NOT found in the spoken audio.")
        else:
            print("\n❌ FAILURE (TTS): No audio data was recorded by the background thread.")

    except queue.Empty:
        print("\n❌ FAILURE (TTS): Timed out waiting for recorded audio data from the queue.")
    except sr.UnknownValueError:
        print("\n❌ FAILURE (TTS): Speech Recognition could not understand audio.")
    except sr.RequestError as e:
        print(f"\n❌ FAILURE (TTS): Could not request results from Google Speech Recognition service; {e}")
    except Exception as e:
        print(f"\n❌ FAILURE (TTS): An error occurred during speech recognition: {e}")
    # finally:
    #     if os.path.exists(audio_filename):
    #         os.remove(audio_filename)
    # --- End of TTS Recognition Test ---

    click_button(CANCEL_SOURCE, True)
    poll_button(CANCEL_SOURCE, visible=False)
    time.sleep(1)


def test_image_source():
    if not poll_port("127.0.0.1", 8000):
        print("OCR service not available. Aborting image tests.")
        return

    # 1. Switch to image source
    cycle_until(CAPTURE_SOURCE)

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
    pyautogui.dragTo(x=3400, y=1100, duration=1)

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

    click_button(CANCEL_SOURCE, True)

    poll_button(CANCEL_SOURCE, visible=False)

    time.sleep(1)


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

    find_text("Captured")

    if not click_button(START_MULTISELECT_SOURCE):
        return

    time.sleep(1)
    pyautogui.moveTo(x=1000, y=900)

    time.sleep(1)
    pyautogui.dragTo(x=2500, y=1200, duration=1)

    find_text("Captured")

    if not click_button(END_MULTISELECT_SOURCE):
        return

    time.sleep(1)

    ui_process.kill()
    ui_process.wait()  # Ensure it has

    if find_text(TARGET_WORD_PROGRAMMING):
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_PROGRAMMING}' was found in the text!")
    else:
        print(f"\n❌ FAILURE: The word '{TARGET_WORD_PROGRAMMING}' was NOT found after multiple retries.")

    click_button(CANCEL_SOURCE, True)

    poll_button(CANCEL_SOURCE, visible=False)

    time.sleep(1)


def cycle_until(target_button):
    while True:
        try:
            if pyautogui.locateCenterOnScreen(target_button, confidence=0.8) is not None:
                return
        except pyautogui.ImageNotFoundException:
            pass

        click_button(CYCLE_SOURCE)
        time.sleep(1)


def check_port_in_use(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError, ConnectionResetError, OSError):
        return False


def poll_port(host, port, timeout=30):
    print(f"Polling for service on {host}:{port}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_port_in_use(host, port):
            print(f"Service on {host}:{port} is ready.")
            return True
        time.sleep(1)
    print(f"Service on {host}:{port} did not become ready within {timeout} seconds.")
    return False


def poll_button(image_path, visible=True, timeout=10, interval=0.5):
    """
    Polls until an image appears or disappears from the screen.
    
    Args:
        image_path: Path to the image to search for.
        visible: If True, polls until the image is found. If False, polls until the image is NOT found.
        timeout: Maximum time to wait in seconds.
        interval: Time to wait between checks.
    
    Returns:
        The (x,y) coordinates of the image if found (and visible=True), or True if visible=False and image disappeared.
        Returns None or False if the condition is not met within the timeout.
    """
    print(f"Polling for image '{image_path}' to be {'visible' if visible else 'hidden'}...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=0.8)
            if visible and location is not None:
                print(f"Image '{image_path}' found at {location}.")
                return location
            elif not visible and location is None:
                print(f"Image '{image_path}' is no longer visible.")
                return True
        except pyautogui.ImageNotFoundException:
            if not visible:
                print(f"Image '{image_path}' is no longer visible.")
                return True

        time.sleep(interval)

    print(f"Timeout reached while waiting for '{image_path}' to be {'visible' if visible else 'hidden'}.")
    return None if visible else False


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
    if check_port_in_use("127.0.0.1", 8000):
        print("OCR service is already running. Using existing instance.")
        service_process = None
    else:
        service_process = launch_service()

    # 3. Start the other script in a separate process
    app_process = launch_app()

    return app_process, service_process


def cleanup(main_app, service_process):
    if main_app is not None:
        print("\nCleaning up: Terminating the background process...")
        main_app.kill()  # Sends a signal to the process asking it to close
        main_app.wait()  # Waits to ensure the process actually closes
        print("Background process safely closed.")

    if service_process is not None:
        print("\nCleaning up: Terminating the service process...")
        service_process.kill()
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
            encoding='utf-8',
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
    print(f"Launching '{MAIN_SCRIPT_PATH}' in the background...")
    try:
        if not os.path.exists(WORKING_DIR):
            print(f"Error: The directory '{WORKING_DIR}' does not exist.")
            return None

        command_list = [sys.executable, MAIN_SCRIPT_PATH] + MAIN_SCRIPT_ARGS

        launched_process = subprocess.Popen(
            command_list,
            cwd=WORKING_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
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
            launched_process.kill()
            return None

    except Exception as e:
        print(f"Failed to launch the second script: {e}")
        return None


def click_button(image, timeout=10, check_once=False):
    if check_once:
        try:
            button_location = pyautogui.locateCenterOnScreen(image, confidence=0.8)
            if button_location is None:
                print(f"Could not find the button '{image}' on the screen (checked once).")
                return True
        except pyautogui.ImageNotFoundException:
            print(f"Could not find the button '{image}' on the screen (checked once).")
            return True
    else:
        button_location = poll_button(image, visible=True, timeout=timeout)

        if button_location is None:
            print(f"Could not find the button '{image}' on the screen.")
            return False

    # 4. Click on it
    print("Button found! Clicking...")
    pyautogui.click(button_location)

    return True


def minimize_all_windows():
    print("Minimizing all windows...")
    pyautogui.hotkey('win', 'd')  # Use ('command', 'f3') for Mac
    time.sleep(1)


if __name__ == "__main__":
    run_tests()
