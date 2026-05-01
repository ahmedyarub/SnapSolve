import os
import queue
import threading
import time

import keyboard
import pyautogui
import pyperclip
import speech_recognition as sr

from audio_utils import get_microphone_index, record_audio_in_background, speak
from config import (
    BASIC_QUESTION,
    CANCEL_SOURCE,
    CAPTURE_BUTTON,
    CYCLE_SOURCE,
    END_MULTISELECT_SOURCE,
    MAIN_SCRIPT_ARGS,
    MAIN_SCRIPT_PATH,
    POPUP_X,
    POPUP_Y,
    PROGRAMMING_QUESTION1,
    PROGRAMMING_QUESTION2,
    PROMPT_X,
    PROMPT_Y,
    RESELECT_SOURCE,
    SERVICE_SCRIPT_PATH,
    START_MULTISELECT_SOURCE,
    TARGET_WORD_BASIC,
    TARGET_WORD_PROGRAMMING,
    TTS_INPUT_DEVICE_NAME,
    WORKING_DIR,
    RECORD_BUTTON,
    STOP_RECORD_BUTTON,
    TTS_OUTPUT_DEVICE_NAME,
)
from network_utils import check_port_in_use, poll_port
from process_utils import cleanup, init_tests, launch_app, launch_service, show_test_ui
from ui_utils import (
    click_button,
    cycle_until,
    find_text,
    minimize_all_windows,
    poll_button,
)

# --- Global variables for background recording ---
_stop_recording_event = threading.Event()
_recorded_audio_queue = queue.Queue()
_recording_thread: threading.Thread | None = None

# --- Test result tracking ---
test_results = {
    "test_text_source": "NOT_RUN",  # Text prompt test
    "test_tts": "NOT_RUN",  # TTS test (part of test_text_source)
    "test_capture": "NOT_RUN",  # Single image capture test
    "test_multi_capture": "NOT_RUN",  # Multi-select image capture test
    "test_audio_source": "NOT_RUN",  # Audio input test
}


def show_test_summary():
    """Display a summary of all test results."""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, result in test_results.items():
        if result == "NOT_RUN":
            status_symbol = "❓"
        elif result == "PASSED":
            status_symbol = "✅"
        else:
            status_symbol = "❌"
        print(f"{status_symbol} {test_name}: {result}")

    print("=" * 60)

    passed_count = sum(1 for result in test_results.values() if result == "PASSED")
    failed_count = sum(1 for result in test_results.values() if result == "FAILED")
    not_run_count = sum(1 for result in test_results.values() if result == "NOT_RUN")

    print(f"Total: {len(test_results)} tests")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print(f"Not Run: {not_run_count}")
    print("=" * 60)


def run_tests():
    def exit_tests():
        print("\nExit shortcut pressed. Cleaning up and exiting...")
        _stop_recording_event.set()
        if _recording_thread and _recording_thread.is_alive():
            _recording_thread.join(timeout=2)
        cleanup(app_process, service_process)
        os._exit(0)

    keyboard.add_hotkey("ctrl+shift+alt+q", exit_tests)

    app_process, service_process = init_tests(
        lambda: launch_service(SERVICE_SCRIPT_PATH, WORKING_DIR),
        lambda: launch_app(MAIN_SCRIPT_PATH, MAIN_SCRIPT_ARGS, WORKING_DIR),
        minimize_all_windows,
        check_port_in_use,
    )

    if not app_process:
        cleanup(app_process, service_process)
        return

    poll_button(CYCLE_SOURCE)

    try:
        test_text_source()
        test_image_source()
        test_audio_source()
    finally:
        show_test_summary()
        _stop_recording_event.set()
        if _recording_thread and _recording_thread.is_alive():
            _recording_thread.join(timeout=2)
        cleanup(app_process, service_process)


def test_text_source():
    global _stop_recording_event, _recorded_audio_queue, _recording_thread
    test_results["test_text_source"] = "FAILED"
    test_results["test_tts"] = "FAILED"

    _stop_recording_event.clear()
    while not _recorded_audio_queue.empty():
        try:
            _recorded_audio_queue.get_nowait()
        except queue.Empty:
            pass

    r: sr.Recognizer = sr.Recognizer()

    mic_index = get_microphone_index(TTS_INPUT_DEVICE_NAME)

    _recording_thread = threading.Thread(
        target=record_audio_in_background,
        args=(_stop_recording_event, _recorded_audio_queue, mic_index),
    )
    _recording_thread.daemon = True

    assert _recording_thread is not None
    _recording_thread.start()
    print("Started background recording thread for TTS test.")

    print(f"Clicking specific position ({PROMPT_X}, {PROMPT_Y})...")
    pyautogui.click(x=PROMPT_X, y=PROMPT_Y)

    print("Pasting the question...")
    pyperclip.copy(BASIC_QUESTION + " Answer with one word only.")
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")

    pyautogui.press("enter")

    time.sleep(2)

    found_target_word = find_text(TARGET_WORD_BASIC, POPUP_X, POPUP_Y)

    time.sleep(3)

    _stop_recording_event.set()
    if _recording_thread and _recording_thread.is_alive():
        print("Waiting for background recording thread to finish...")
        _recording_thread.join(timeout=5)
        if _recording_thread.is_alive():
            print("Warning: Background recording thread did not terminate in time.")
    print("Signaled background recording thread to stop.")

    if found_target_word:
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_BASIC}' was found in the text!")
        test_results["test_text_source"] = "PASSED"
    else:
        print(
            f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found after multiple retries."
        )
        return

    print("\n--- Starting TTS Recognition Test (Processing recorded audio) ---")
    audio_filename = "recorded_tts_output.wav"

    try:
        if not _recorded_audio_queue.empty():
            audio = _recorded_audio_queue.get(timeout=5)

            with open(audio_filename, "wb") as f:
                f.write(audio.get_wav_data())
            print(f"Audio recorded to {audio_filename}")

            recognized_text = r.recognize_google(audio)  # type: ignore[attr-defined]
            print(f"Recognized text: '{recognized_text}'")

            if TARGET_WORD_BASIC.lower() in recognized_text.lower():
                print(
                    f"\n✅ SUCCESS (TTS): The word '{TARGET_WORD_BASIC}' was found in the spoken audio!"
                )
                test_results["test_tts"] = "PASSED"
            else:
                print(
                    f"\n❌ FAILURE (TTS): The word '{TARGET_WORD_BASIC}' was NOT found in the spoken audio."
                )
        else:
            print(
                "\n❌ FAILURE (TTS): No audio data was recorded by the background thread."
            )

    except queue.Empty:
        print(
            "\n❌ FAILURE (TTS): Timed out waiting for recorded audio data from the queue."
        )
    except sr.UnknownValueError:
        print("\n❌ FAILURE (TTS): Speech Recognition could not understand audio.")
    except sr.RequestError as e:
        print(
            f"\n❌ FAILURE (TTS): Could not request results from Google Speech Recognition service; {e}"
        )
    except Exception as e:
        print(f"\n❌ FAILURE (TTS): An error occurred during speech recognition: {e}")

    click_button(CANCEL_SOURCE, True)
    poll_button(CANCEL_SOURCE, visible=False)
    time.sleep(1)


def test_image_source():
    if not poll_port("127.0.0.1", 8000):
        print("OCR service not available. Aborting image tests.")
        return

    cycle_until(CAPTURE_BUTTON)

    time.sleep(1)

    test_capture()

    time.sleep(1)

    test_multi_capture()


def test_audio_source():
    test_results["test_audio_source"] = "FAILED"

    cycle_until(RECORD_BUTTON)

    click_button(RECORD_BUTTON)

    time.sleep(1)

    speak(BASIC_QUESTION, TTS_OUTPUT_DEVICE_NAME)

    click_button(STOP_RECORD_BUTTON)

    time.sleep(1)

    if find_text(TARGET_WORD_BASIC, POPUP_X, POPUP_Y):
        print(f"\n✅ SUCCESS: The word '{TARGET_WORD_BASIC}' was found in the audio!")
        test_results["test_audio_source"] = "PASSED"
    else:
        print(
            f"\n❌ FAILURE: The word '{TARGET_WORD_BASIC}' was NOT found after multiple retries."
        )


def finalize_image_test(capture_button, target_word, ui_process):
    test_results["test_capture_temp"] = "FAILED"

    if not click_button(capture_button):
        return

    time.sleep(1)

    ui_process.kill()
    ui_process.wait()

    if find_text(target_word, POPUP_X, POPUP_Y):
        print(f"\n✅ SUCCESS: The word '{target_word}' was found in the text!")
        test_results["test_capture_temp"] = "PASSED"
    else:
        print(
            f"\n❌ FAILURE: The word '{target_word}' was NOT found after multiple retries."
        )

    click_button(CANCEL_SOURCE, True)

    poll_button(CANCEL_SOURCE, visible=False)

    time.sleep(1)


def test_capture():
    test_results["test_capture"] = "FAILED"

    ui_process = show_test_ui(ui_data=[{"text": BASIC_QUESTION, "x": 500, "y": 300}])

    time.sleep(2)

    if not click_button(RESELECT_SOURCE):
        return

    time.sleep(1)

    pyautogui.moveTo(x=1000, y=700)

    time.sleep(1)
    pyautogui.dragTo(x=3400, y=1100, duration=1)

    time.sleep(1)

    finalize_image_test(CAPTURE_BUTTON, TARGET_WORD_BASIC, ui_process)

    # Update result based on whether the test passed
    if test_results.get("test_capture_temp") == "PASSED":
        test_results["test_capture"] = "PASSED"
    # Clean up temp result
    test_results.pop("test_capture_temp", None)


def test_multi_capture():
    test_results["test_multi_capture"] = "FAILED"

    ui_process = show_test_ui(
        ui_data=[
            {"text": PROGRAMMING_QUESTION1, "x": 500, "y": 100},
            {"text": PROGRAMMING_QUESTION2, "x": 500, "y": 400},
        ]
    )

    time.sleep(2)

    if not click_button(START_MULTISELECT_SOURCE):
        return

    time.sleep(1)
    pyautogui.moveTo(x=1000, y=200)

    time.sleep(1)
    pyautogui.dragTo(x=2600, y=400, duration=1)

    find_text("Captured", POPUP_X, POPUP_Y)

    if not click_button(START_MULTISELECT_SOURCE):
        return

    time.sleep(1)
    pyautogui.moveTo(x=1000, y=900)

    time.sleep(1)
    pyautogui.dragTo(x=2500, y=1200, duration=1)

    find_text("Captured", POPUP_X, POPUP_Y)

    finalize_image_test(END_MULTISELECT_SOURCE, TARGET_WORD_PROGRAMMING, ui_process)

    # Update result based on whether the test passed
    if test_results.get("test_capture_temp") == "PASSED":
        test_results["test_multi_capture"] = "PASSED"
    # Clean up temp result
    test_results.pop("test_capture_temp", None)


if __name__ == "__main__":
    run_tests()
