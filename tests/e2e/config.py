# --- Configuration variables ---
WORKING_DIR = r"../../"
CANCEL_SOURCE = "images/button_cancel.png"
CYCLE_SOURCE = "images/button_cycle_source.png"
RESELECT_SOURCE = "images/button_reselect.png"
CAPTURE_BUTTON = "images/button_capture.png"
START_MULTISELECT_SOURCE = "images/button_start_multiselect.png"
END_MULTISELECT_SOURCE = "images/button_end_multiselect.png"
RECORD_BUTTON = "images/button_record.png"
STOP_RECORD_BUTTON = "images/button_record_stop.png"
TARGET_WORD_BASIC = "Brazil"
TARGET_WORD_PROGRAMMING = "class"
PROMPT_X, PROMPT_Y = 1900, 1900
POPUP_X, POPUP_Y = 3500, 1800
BASIC_QUESTION = "What is the fifth largest country in the world?"
PROGRAMMING_QUESTION1 = "Write a Python hello world."
PROGRAMMING_QUESTION2 = "Use classes"
TTS_INPUT_DEVICE_NAME = "CABLE Output (VB-Audio Virtual "
TTS_OUTPUT_DEVICE_NAME = "CABLE Input (VB-Audio Virtual C"

# --- Subprocess Configuration ---
MAIN_SCRIPT_PATH = "main.py"
MAIN_SCRIPT_ARGS = [
    "--active-profile=quick",
    "--popup-opacity=1.0",
    f"--tts-output-device-name={TTS_OUTPUT_DEVICE_NAME}",
    f"--audio-input-device-name={TTS_INPUT_DEVICE_NAME}",
    "--default-source=text",
]
SERVICE_SCRIPT_PATH = "services/ocr_service.py"
ERROR_RESPONSES = ["No speech recognized."]
