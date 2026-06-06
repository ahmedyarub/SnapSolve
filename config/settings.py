import argparse
import json
import os
from pathlib import Path

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
            "enable_chat_sessions": True,
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
    """Get default configuration."""
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
            {"action": "toggle_chat_sessions", "key": "ctrl+alt+shift+i"},
            {"action": "toggle_all_widgets", "key": "ctrl+alt+shift+v"},
            {"action": "open_url", "key": "ctrl+alt+u"},
            {"action": "open_session_browser", "key": "ctrl+alt+shift+b"},
            {"action": "quit_app", "key": "ctrl+alt+shift+q"},
        ],
        "save_images": True,
        "save_transcriptions": True,
        "speaker_name": "interviewer",
        "coordinates": None,
        "background": False,
        "piper_model": "en_US-lessac-medium.onnx",
        "active_profile_id": "prof1",
        "ollama_url": "http://localhost:11434",
        "gemini_api_key": "",
        "auto_close_results": False,
        "opacity": 0.8,
        "show_control_panel": False,
        "default_source": "text",
        "warmup_ocr": True,
        "warmup_llm": True,
        "warmup_tts": False,
        "warmup_speech_recognition": True,
        "warmup_realtime_transcription": False,
        "tts_output_device_name": None,
        "audio_input_device_name": None,
        "realtime_transcription": True,
        "transcription_pause_threshold": 1.0,
        "transcription_language": "en",
        "tts_language": "en",
        "translation_language": "",
        # Remote control server (Android app integration)
        "enable_remote_control": False,
        "remote_control_host": "0.0.0.0",
        "remote_control_port": 8080,
        "remote_mouse_idle_timeout": 3.0,
        "share_response_with_android": False,
        "ide_pycharm_path": "pycharm",
        "ide_antigravity_path": str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe"),
        # LLM retry on transient errors (503, rate limits, etc.)
        "llm_max_retries": 3,
        "llm_retry_base_delay": 5,
        # Maximum number of prompts to keep in text input history
        "max_prompt_history": 100,
        # Periodic screenshots
        "periodic_screenshots_enabled": False,
        "periodic_screenshots_interval": 15,
        "periodic_screenshots_on_activity": False,
        "periodic_screenshots_activity_min_delay": 5,
    }


def _migrate_legacy_config():
    """Migrate legacy config if it exists."""
    legacy_config = "config.json"
    if os.path.exists(legacy_config) and not os.path.exists(CONFIG_FILE):
        import shutil

        shutil.move(legacy_config, CONFIG_FILE)


def _migrate_hotkey_format(file_config):
    """Migrate old hotkey format to new format."""
    if "hotkey" in file_config and "hotkeys" not in file_config:
        file_config["hotkeys"] = [
            {"action": "capture", "key": file_config["hotkey"]},
            {"action": "reselect", "key": "ctrl+alt+shift+r"},
        ]
        del file_config["hotkey"]


def _ensure_hotkey_actions(file_config):
    """Ensure all required hotkey actions exist."""
    if "hotkeys" not in file_config:
        return

    current_actions = {hk["action"]: hk["key"] for hk in file_config["hotkeys"]}

    required_actions = {
        "capture": "ctrl+alt+shift+s",
        "reselect": "ctrl+alt+shift+r",
        "multi_capture": "ctrl+alt+shift+m",
        "end_multi_capture": "ctrl+alt+shift+n",
        "cancel_multi_capture": "ctrl+alt+t",
        "toggle_panel": "ctrl+alt+p",
        "toggle_all_widgets": "ctrl+alt+shift+v",
        "open_url": "ctrl+alt+u",
        "open_session_browser": "ctrl+alt+shift+b",
        "quit_app": "ctrl+alt+shift+q",
    }

    for action, default_key in required_actions.items():
        if action not in current_actions:
            file_config["hotkeys"].append({"action": action, "key": default_key})


def _load_config_from_file():
    """Load config from file."""
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r") as f:
            file_config = json.load(f)

        _migrate_hotkey_format(file_config)
        _ensure_hotkey_actions(file_config)

        return file_config
    except json.JSONDecodeError:
        print(f"Warning: {CONFIG_FILE} is not a valid JSON. Using default settings.")
        return {}


def load_config():
    config = _get_default_config()

    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    _migrate_legacy_config()

    file_config = _load_config_from_file()

    # Migrate renamed key
    if "popup_opacity" in file_config and "opacity" not in file_config:
        file_config["opacity"] = file_config.pop("popup_opacity")
    elif "popup_opacity" in file_config:
        del file_config["popup_opacity"]

    config.update(file_config)

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
    parser.add_argument("--gemini-api-key", type=str, help="Gemini API Key")
    parser.add_argument(
        "--auto-close-results", action="store_true", help="Auto close result popups"
    )
    parser.add_argument(
        "--no-auto-close-results",
        action="store_true",
        help="Do not auto close result popups",
    )
    parser.add_argument(
        "--popup-opacity", type=float, help="Opacity of all overlay windows (0.0 to 1.0)"
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
    parser.add_argument(
        "--transcription-language",
        type=str,
        help="Language code for speech recognition / transcription (e.g., en, es, fr)",
    )
    parser.add_argument(
        "--tts-language",
        type=str,
        help="Language code for text-to-speech (e.g., en, es, fr)",
    )
    parser.add_argument(
        "--translation-language",
        type=str,
        help="Target language code for real-time translation (e.g., en, es, fr). Empty to disable.",
    )
    parser.add_argument(
        "--enable-chat-sessions",
        action="store_true",
        help="Enable chat sessions",
    )
    parser.add_argument(
        "--disable-chat-sessions",
        action="store_true",
        help="Disable chat sessions",
    )
    parser.add_argument(
        "--no-hide-from-capture",
        action="store_true",
        help="Disable hiding windows from screen capture (useful for e2e tests)",
    )
    parser.add_argument(
        "--enable-periodic-screenshots",
        action="store_true",
        help="Enable periodic screenshots during sessions",
    )
    parser.add_argument(
        "--disable-periodic-screenshots",
        action="store_true",
        help="Disable periodic screenshots during sessions",
    )
    parser.add_argument(
        "--periodic-screenshots-interval",
        type=int,
        help="Seconds between periodic screenshot captures (default: 15)",
    )
    parser.add_argument(
        "--enable-periodic-screenshots-on-activity",
        action="store_true",
        help="Enable screenshot capture on keyboard/mouse activity",
    )
    parser.add_argument(
        "--disable-periodic-screenshots-on-activity",
        action="store_true",
        help="Disable screenshot capture on keyboard/mouse activity",
    )
    parser.add_argument(
        "--periodic-screenshots-activity-min-delay",
        type=int,
        help="Minimum seconds between activity-triggered screenshots (default: 5)",
    )

    return parser.parse_args()


def _apply_output_mode_config(config, args):
    """Apply output mode configuration from command line args."""
    if args.output_mode:
        if "both" in args.output_mode:
            config["output_mode"] = ["popup", "audio"]
        else:
            config["output_mode"] = args.output_mode


def _apply_hotkey_config(config, args):
    """Apply hotkey configuration from command line args."""
    if args.hotkey_capture or args.hotkey_reselect:
        for hk in config["hotkeys"]:
            if hk["action"] == "capture" and args.hotkey_capture:
                hk["key"] = args.hotkey_capture
            if hk["action"] == "reselect" and args.hotkey_reselect:
                hk["key"] = args.hotkey_reselect


def _apply_basic_config(config, args):
    """Apply basic configuration options from command line args."""
    if args.coords:
        config["coordinates"] = args.coords

    if args.background:
        config["background"] = True
    elif args.foreground:
        config["background"] = False

    if args.piper_model:
        config["piper_model"] = args.piper_model

    if args.active_profile:
        config["active_profile_id"] = args.active_profile

    if args.ollama_url:
        config["ollama_url"] = args.ollama_url

    if args.gemini_api_key:
        config["gemini_api_key"] = args.gemini_api_key

    if args.auto_close_results:
        config["auto_close_results"] = True
    elif args.no_auto_close_results:
        config["auto_close_results"] = False

    if args.popup_opacity is not None:
        config["opacity"] = args.popup_opacity

    if args.show_control_panel:
        config["show_control_panel"] = True
    elif args.hide_control_panel:
        config["show_control_panel"] = False

    if args.continue_last:
        config["continue_last"] = True

    if args.continue_session:
        config["continue_session"] = args.continue_session

    if args.default_source:
        config["default_source"] = args.default_source

    if args.enable_chat_sessions:
        config["enable_chat_sessions"] = True
    elif args.disable_chat_sessions:
        config["enable_chat_sessions"] = False

    if args.no_hide_from_capture:
        config["hide_from_capture"] = False


def _apply_warmup_config(config, args):
    """Apply warmup configuration options from command line args."""
    if args.disable_warmup_ocr:
        config["warmup_ocr"] = False

    if args.disable_warmup_llm:
        config["warmup_llm"] = False

    if args.disable_warmup_tts:
        config["warmup_tts"] = False

    if args.disable_warmup_speech_recognition:
        config["warmup_speech_recognition"] = False

    if args.disable_warmup_realtime_transcription:
        config["warmup_realtime_transcription"] = False


def _apply_audio_config(config, args):
    """Apply audio configuration options from command line args."""
    if args.tts_output_device_name is not None:
        config["tts_output_device_name"] = args.tts_output_device_name

    if args.audio_input_device_name is not None:
        config["audio_input_device_name"] = args.audio_input_device_name


def _apply_transcription_config(config, args):
    """Apply transcription configuration options from command line args."""
    if args.disable_save_transcriptions:
        config["save_transcriptions"] = False

    if args.disable_realtime_transcription:
        config["realtime_transcription"] = False

    if args.transcription_pause_threshold is not None:
        config["transcription_pause_threshold"] = args.transcription_pause_threshold

    if args.transcription_language is not None:
        config["transcription_language"] = args.transcription_language

    if args.tts_language is not None:
        config["tts_language"] = args.tts_language

    if args.translation_language is not None:
        config["translation_language"] = args.translation_language


def _apply_periodic_screenshots_config(config, args):
    """Apply periodic screenshots configuration options from command line args."""
    if args.enable_periodic_screenshots:
        config["periodic_screenshots_enabled"] = True
    elif args.disable_periodic_screenshots:
        config["periodic_screenshots_enabled"] = False

    if args.periodic_screenshots_interval is not None:
        config["periodic_screenshots_interval"] = args.periodic_screenshots_interval

    if args.enable_periodic_screenshots_on_activity:
        config["periodic_screenshots_on_activity"] = True
    elif args.disable_periodic_screenshots_on_activity:
        config["periodic_screenshots_on_activity"] = False

    if args.periodic_screenshots_activity_min_delay is not None:
        config["periodic_screenshots_activity_min_delay"] = args.periodic_screenshots_activity_min_delay


def get_config():
    config = load_config()
    args = parse_args()

    _apply_output_mode_config(config, args)
    _apply_hotkey_config(config, args)
    _apply_basic_config(config, args)
    _apply_warmup_config(config, args)
    _apply_audio_config(config, args)
    _apply_transcription_config(config, args)
    _apply_periodic_screenshots_config(config, args)

    return config
