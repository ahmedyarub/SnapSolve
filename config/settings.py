import argparse
import json
import os
import pyaudio  # Import pyaudio

CONFIG_FILE = os.path.join("config", "config.json")
PROFILES_FILE = os.path.join("config", "profiles.json")
PROMPTS_FILE = os.path.join("config", "prompts.json")


def load_profiles():
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(
                f"Warning: {PROFILES_FILE} is not a valid JSON. Using default profile."
            )
    return [
        {
            "id": "prof1",
            "name": "Default Profile",
            "llm_engine": "gemini",
            "model": "gemini-2.5-flash-lite",
            "ocr_engine": "none",
            "prompt_id": "default",
            "enable_stitching": True,
        }
    ]


def save_profiles(profiles):
    with open(PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=4)


def load_prompts():
    if os.path.exists(PROMPTS_FILE):
        try:
            with open(PROMPTS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {PROMPTS_FILE} is not a valid JSON.")
    return [
        {
            "id": "default",
            "description": "Quick answer",
            "text": "answer the following question quickly and briefly",
        }
    ]


def get_audio_devices():
    """
    Lists all available audio output devices, filtering to include only "MME" devices.
    Returns their name and index.
    """
    p = pyaudio.PyAudio()

    output_devices = []

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)

        # Only consider output devices
        if info["maxOutputChannels"] > 0:
            host_api_name = p.get_host_api_info_by_index(info["hostApi"])["name"]

            # Filter for "MME" devices
            if host_api_name == "MME":
                output_devices.append(
                    {
                        "index": info["index"],
                        "name": info["name"],
                        # 'hostApiName': host_api_name # No longer storing hostApiName
                    }
                )

    p.terminate()

    # Sort devices by name for consistent ordering
    output_devices.sort(key=lambda x: x["name"].lower())

    return output_devices


def get_audio_input_devices():
    """
    Lists all available audio input devices.
    Returns their name and index.
    """
    p = pyaudio.PyAudio()

    input_devices = []

    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)

        # Only consider input devices
        if info["maxInputChannels"] > 0:
            host_api_name = p.get_host_api_info_by_index(info["hostApi"])["name"]

            # Filter for "MME" devices to match output behavior, or just MME
            if host_api_name == "MME":
                input_devices.append(
                    {
                        "index": info["index"],
                        "name": info["name"],
                    }
                )

    p.terminate()

    input_devices.sort(key=lambda x: x["name"].lower())

    return input_devices


def _get_default_config():
    return {
        "output_mode": ["popup"],
        "hotkeys": [
            {"action": "capture", "key": "ctrl+alt+shift+c"},
            {"action": "reselect", "key": "ctrl+alt+shift+s"},
            {"action": "multi_capture", "key": "ctrl+alt+shift+m"},
            {"action": "end_multi_capture", "key": "ctrl+alt+shift+n"},
            {"action": "cancel_multi_capture", "key": "ctrl+alt+t"},
            {"action": "toggle_panel", "key": "ctrl+alt+shift+p"},
            {"action": "new_chat_session", "key": "ctrl+alt+shift+h"},
            {"action": "toggle_stitching", "key": "ctrl+alt+shift+i"},
        ],
        "save_images": False, "save_transcriptions": True, "coordinates": None,
        "background": False, "piper_model": "en_US-lessac-medium.onnx",
        "active_profile_id": "prof1", "ollama_url": "http://localhost:11434",
        "google_genai_api_key": "", "auto_close_results": False,
        "popup_opacity": 0.8, "show_control_panel": False, "default_source": "text",
        "warmup_ocr": True, "warmup_llm": True, "warmup_tts": False,
        "warmup_speech_recognition": True, "warmup_realtime_transcription": False,
        "tts_output_device_name": None, "audio_input_device_name": None,
        "realtime_transcription": True, "transcription_pause_threshold": 1.0,
    }

def _merge_hotkeys(file_config):
    if "hotkey" in file_config and "hotkeys" not in file_config:
        file_config["hotkeys"] = [
            {"action": "capture", "key": file_config["hotkey"]},
            {"action": "reselect", "key": "ctrl+alt+shift+r"},
        ]
        del file_config["hotkey"]
    elif "hotkeys" in file_config:
        current_actions = {hk["action"]: hk["key"] for hk in file_config["hotkeys"]}
        defaults = {
            "capture": "ctrl+alt+shift+s", "reselect": "ctrl+alt+shift+r",
            "multi_capture": "ctrl+alt+shift+m", "end_multi_capture": "ctrl+alt+shift+n",
            "cancel_multi_capture": "ctrl+alt+t", "toggle_panel": "ctrl+alt+p"
        }
        for act, key in defaults.items():
            if act not in current_actions:
                file_config["hotkeys"].append({"action": act, "key": key})
    return file_config

def load_config():
    config = _get_default_config()
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    legacy_config = "config.json"
    if os.path.exists(legacy_config) and not os.path.exists(CONFIG_FILE):
        import shutil
        shutil.move(legacy_config, CONFIG_FILE)

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                file_config = json.load(f)
                file_config = _merge_hotkeys(file_config)
                config.update(file_config)
        except json.JSONDecodeError:
            print(f"Warning: {CONFIG_FILE} is not a valid JSON. Using default settings.")
    return config


def save_config(config):
    # Ensure backward compatibility field is removed before saving
    if "hotkey" in config:
        del config["hotkey"]

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def parse_args():
    parser = argparse.ArgumentParser(description="Screen Capture & Gemini QA")
    parser.add_argument(
        "--output-mode",
        type=str,
        nargs="+",
        choices=["popup", "audio", "both"],
        help="Output mode: popup, audio, both",
    )
    parser.add_argument(
        "--hotkey-capture",
        type=str,
        help="Keyboard shortcut to trigger capture (e.g., ctrl+alt+shift+s)",
    )
    parser.add_argument(
        "--hotkey-reselect",
        type=str,
        help="Keyboard shortcut to reselect coordinates (e.g., ctrl+alt+shift+r)",
    )
    parser.add_argument(
        "--coords",
        type=int,
        nargs=4,
        metavar=("X1", "Y1", "X2", "Y2"),
        help="Capture coordinates",
    )
    parser.add_argument(
        "--background", action="store_true", help="Run in background (system tray)"
    )
    parser.add_argument(
        "--foreground", action="store_true", help="Force run in foreground"
    )
    parser.add_argument("--piper-model", type=str, help="Path to Piper .onnx model")
    parser.add_argument("--active-profile", type=str, help="Active profile ID")
    parser.add_argument(
        "--ollama-url",
        type=str,
        help="Ollama API URL (default: http://localhost:11434)",
    )
    parser.add_argument("--google-genai-api_key", type=str, help="Google GenAI API Key")
    parser.add_argument(
        "--auto-close-results", action="store_true", help="Auto close result popups"
    )
    parser.add_argument(
        "--no-auto-close-results",
        action="store_true",
        help="Do not auto close result popups",
    )
    parser.add_argument(
        "--popup-opacity", type=float, help="Opacity of the popup (0.0 to 1.0)"
    )
    parser.add_argument(
        "--fallback-language",
        type=str,
        help="Fallback language for code blocks (default: python)",
    )
    parser.add_argument(
        "--show-control-panel",
        action="store_true",
        help="Show the control panel overlay",
    )
    parser.add_argument(
        "--hide-control-panel",
        action="store_true",
        help="Hide the control panel overlay",
    )
    parser.add_argument(
        "--continue-last", action="store_true", help="Continue the last chat session"
    )
    parser.add_argument(
        "--continue-session", type=str, help="Continue a specific chat session by ID"
    )
    parser.add_argument(
        "--default-source",
        type=str,
        choices=["text", "image", "audio"],
        help="Default source (text or image)",
    )
    parser.add_argument(
        "--disable-warmup-ocr", action="store_true", help="Disable OCR engine warmup"
    )
    parser.add_argument(
        "--disable-warmup-llm", action="store_true", help="Disable LLM engine warmup"
    )
    parser.add_argument(
        "--disable-warmup-tts", action="store_true", help="Disable TTS engine warmup"
    )
    parser.add_argument(
        "--disable-warmup-speech-recognition",
        action="store_true",
        help="Disable Speech Recognition warmup",
    )
    parser.add_argument(
        "--disable-warmup-realtime-transcription",
        action="store_true",
        help="Disable Real-time Transcription warmup",
    )
    parser.add_argument(
        "--disable-save-transcriptions",
        action="store_true",
        help="Disable saving transcriptions to files",
    )
    parser.add_argument(
        "--tts-output-device-name",
        type=str,
        help="Name of the audio device for TTS output",
    )
    parser.add_argument(
        "--audio-input-device-name",
        type=str,
        help="Name of the audio device for audio input",
    )
    parser.add_argument(
        "--disable-realtime-transcription",
        action="store_true",
        help="Disable real-time transcription during recording",
    )
    parser.add_argument(
        "--transcription-pause-threshold",
        type=float,
        help="Pause threshold in seconds for real-time transcription (default: 1.0)",
    )

    return parser.parse_args()


def _apply_hotkeys_args(config, args):
    if args.hotkey_capture or args.hotkey_reselect:
        for hk in config["hotkeys"]:
            if hk["action"] == "capture" and args.hotkey_capture: hk["key"] = args.hotkey_capture
            if hk["action"] == "reselect" and args.hotkey_reselect: hk["key"] = args.hotkey_reselect

def _apply_bool_args(config, args):
    bool_flags = [
        ("background", True, "background"), ("background", False, "foreground"),
        ("auto_close_results", True, "auto_close_results"), ("auto_close_results", False, "no_auto_close_results"),
        ("show_control_panel", True, "show_control_panel"), ("show_control_panel", False, "hide_control_panel"),
        ("warmup_ocr", False, "disable_warmup_ocr"), ("warmup_llm", False, "disable_warmup_llm"),
        ("warmup_tts", False, "disable_warmup_tts"), ("warmup_speech_recognition", False, "disable_warmup_speech_recognition"),
        ("warmup_realtime_transcription", False, "disable_warmup_realtime_transcription"),
        ("save_transcriptions", False, "disable_save_transcriptions"), ("realtime_transcription", False, "disable_realtime_transcription"),
        ("continue_last", True, "continue_last")
    ]
    for key, val, flag in bool_flags:
        if getattr(args, flag, False): config[key] = val

def _apply_str_args(config, args):
    str_flags = [
        ("coordinates", "coords"), ("piper_model", "piper_model"), ("active_profile_id", "active_profile"),
        ("ollama_url", "ollama_url"), ("google_genai_api_key", "google_genai_api_key"),
        ("popup_opacity", "popup_opacity"), ("continue_session", "continue_session"),
        ("default_source", "default_source"), ("tts_output_device_name", "tts_output_device_name"),
        ("audio_input_device_name", "audio_input_device_name"), ("transcription_pause_threshold", "transcription_pause_threshold")
    ]
    for key, flag in str_flags:
        if getattr(args, flag, None) is not None:
            config[key] = getattr(args, flag)

def _apply_cli_args(config, args):
    if args.output_mode:
        config["output_mode"] = ["popup", "audio"] if "both" in args.output_mode else args.output_mode
    _apply_hotkeys_args(config, args)
    _apply_bool_args(config, args)
    _apply_str_args(config, args)
    return config



def get_config():
    config = load_config()
    args = parse_args()
    return _apply_cli_args(config, args)
