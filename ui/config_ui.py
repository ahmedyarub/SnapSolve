import json
import os
import sys
from pathlib import Path

# Add parent directory to path so imports work when running this file directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QMessageBox,
    QCheckBox,
    QFormLayout,
    QScrollArea,
    QDialogButtonBox,
    QApplication,
    QPushButton,
    QFileDialog,
    QSlider,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from config.settings import get_audio_devices


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
    return default


# Shared language list used by config UI and control panel
TRANSCRIPTION_LANGUAGES: list[tuple[str, str]] = [
    ("Auto-detect", ""),
    ("English", "en"), ("Spanish", "es"), ("French", "fr"),
    ("German", "de"), ("Italian", "it"), ("Portuguese", "pt"),
    ("Russian", "ru"), ("Chinese", "zh"), ("Japanese", "ja"),
    ("Korean", "ko"), ("Arabic", "ar"), ("Hindi", "hi"),
    ("Turkish", "tr"), ("Polish", "pl"), ("Dutch", "nl"),
    ("Swedish", "sv"), ("Czech", "cs"), ("Romanian", "ro"),
    ("Hungarian", "hu"), ("Ukrainian", "uk"), ("Greek", "el"),
    ("Hebrew", "he"), ("Thai", "th"), ("Vietnamese", "vi"),
    ("Indonesian", "id"), ("Malay", "ms"),
]


class ConfigUI(QDialog):
    def __init__(self, config_path, models_path, profiles_path, prompts_path):
        super().__init__()

        # Load configurations
        self.config_path = config_path
        self.models_path = models_path
        self.profiles_path = profiles_path
        self.prompts_path = prompts_path
        self.config = load_json(self.config_path, {})
        self.models_data = load_json(self.models_path, {})
        self.profiles = load_json(self.profiles_path, [])
        self.prompts = load_json(self.prompts_path, [])

        self.shortcut_inputs = {}
        self.shortcuts_layout = None
        self.show_control_panel = QCheckBox("Show control panel on startup")
        self.ollama_url = QLineEdit(
            self.config.get("ollama_url", "http://localhost:11434")
        )
        self.gemini_api_key = QLineEdit(
            self.config.get("gemini_api_key", "")
        )
        
        # IDE paths
        default_antigravity = str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe")
        self.ide_pycharm_path = QLineEdit(self.config.get("ide_pycharm_path", "pycharm"))
        self.ide_antigravity_path = QLineEdit(self.config.get("ide_antigravity_path", default_antigravity))
        self.antigravity_service_url = QLineEdit(self.config.get("antigravity_service_url", "http://localhost:8200"))
        self.profile_combo = QComboBox()
        self.profile_form = QWidget()
        self.prof_name = QLineEdit()
        self.prof_enable_chat_sessions = QCheckBox("Enable Chat Sessions")
        self.prof_llm_engine = QComboBox()
        self.prof_model = QComboBox()
        self.prof_fallback_model = QComboBox()
        self.prof_ocr_engine = QComboBox()
        self.prof_prompt = QComboBox()
        self.output_mode_audio = None
        self.output_mode_popup = None
        self.should_run = None
        self.btn_save_run = None
        self.button_box = None
        self.shortcuts_tab = None
        self.profile_tab = None
        self.app_tab = None
        self.audio_tab = QWidget()

        self.llm_tab = QWidget()
        self.tabs = QTabWidget()
        self.warmup_tab = QWidget()
        self.default_source_combo = QComboBox()
        self.piper_model = QLineEdit(
            self.config.get("piper_model", "en_US-lessac-medium.onnx")
        )
        self.tts_output_device_combo = QComboBox()
        self.audio_input_device_combo = QComboBox()
        self.background_mode = QCheckBox("Run in system tray")
        self.hide_from_capture = QCheckBox("Hide windows from screen capture")
        self.realtime_transcription = QCheckBox("Enable Real-time Transcription")
        self.save_transcriptions = QCheckBox("Save Transcriptions to Files")
        self.auto_summarize_transcription = QCheckBox("Auto-summarize transcription on stop")
        self.summarize_transcription_prompt = QLineEdit(
            self.config.get("summarize_transcription_prompt", "Summarize the following transcribed conversation:\n")
        )
        self.transcription_language = QComboBox()
        self.tts_language = QComboBox()
        self.translation_language = QComboBox()
        self.save_images = QCheckBox("Save Captured Images to Session")
        self.speaker_name = QLineEdit(
            self.config.get("speaker_name", "interviewer")
        )
        self.warmup_ocr = QCheckBox("Warmup OCR Engine")
        self.warmup_llm = QCheckBox("Warmup LLM Engine")
        self.warmup_tts = QCheckBox("Warmup TTS Engine")
        self.warmup_sr = QCheckBox("Warmup Speech Recognition")
        self.warmup_realtime_transcription = QCheckBox("Warmup Real-time Transcription")
        self._current_profile_data = None

        # Opacity slider
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.config.get("opacity", 0.8) * 100))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )

        # Remote Control tab widgets
        self.remote_control_tab = QWidget()
        self.enable_remote_control = QCheckBox("Enable Remote Control Server")
        self.remote_control_host = QLineEdit(
            self.config.get("remote_control_host", "0.0.0.0")
        )
        self.remote_control_port = QLineEdit(
            str(self.config.get("remote_control_port", 8080))
        )
        self.mouse_sensitivity = QLineEdit(
            str(self.config.get("mouse_sensitivity", 1.5))
        )
        self.remote_mouse_idle_timeout = QLineEdit(
            str(self.config.get("remote_mouse_idle_timeout", 3.0))
        )
        self.share_response_with_android = QCheckBox(
            "Share LLM response screenshot with Android app"
        )

        # LLM Retry settings
        self.llm_max_retries = QLineEdit(
            str(self.config.get("llm_max_retries", 3))
        )
        self.llm_retry_base_delay = QLineEdit(
            str(self.config.get("llm_retry_base_delay", 5))
        )

        # Periodic Screenshots settings
        self.periodic_screenshots_enabled = QCheckBox("Enable Periodic Screenshots")
        self.periodic_screenshots_interval = QLineEdit(
            str(self.config.get("periodic_screenshots_interval", 15))
        )
        self.periodic_screenshots_on_activity = QCheckBox(
            "Capture on Keyboard/Mouse Activity"
        )
        self.periodic_screenshots_activity_min_delay = QLineEdit(
            str(self.config.get("periodic_screenshots_activity_min_delay", 5))
        )
        self.track_active_window = QCheckBox(
            "Track Active Window with Screenshots"
        )

        self.setWindowTitle("Application Configuration")
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "icon.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(600, 500)

        self.init_ui()

    def save_json(self, path, data):
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save {path}:\n{e}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        # Create tabs
        self.app_tab = QWidget()
        self.profile_tab = QWidget()
        self.shortcuts_tab = QWidget()

        self.tabs.addTab(self.app_tab, "Application Settings")
        self.tabs.addTab(self.audio_tab, "Audio & Speech")
        self.tabs.addTab(self.profile_tab, "Profile Settings")
        self.tabs.addTab(self.llm_tab, "LLM Settings")
        self.tabs.addTab(self.warmup_tab, "Warmup Settings")
        self.tabs.addTab(self.shortcuts_tab, "Keyboard Shortcuts")
        self.tabs.addTab(self.remote_control_tab, "Remote Control")

        self.setup_app_tab()
        self.setup_audio_tab()
        self.setup_profile_tab()
        self.setup_llm_tab()
        self.setup_warmup_tab()
        self.setup_shortcuts_tab()
        self.setup_remote_control_tab()

        # Buttons
        self.button_box = QDialogButtonBox()
        self.button_box.addButton(QDialogButtonBox.StandardButton.Save)
        self.button_box.addButton(QDialogButtonBox.StandardButton.Cancel)

        self.btn_save_run = self.button_box.addButton(
            "Save and Run", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.button_box.accepted.connect(self.save_all)
        self.button_box.rejected.connect(self.reject)
        assert self.btn_save_run is not None
        self.btn_save_run.clicked.connect(self.save_and_run)
        layout.addWidget(self.button_box)

        self.should_run = False

    def save_and_run(self):
        self.should_run = True
        self.save_all()

    def browse_piper_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Piper Model", "", "ONNX Files (*.onnx);;All Files (*)"
        )
        if file_path:
            self.piper_model.setText(file_path)

    def browse_pycharm_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select PyCharm Executable", "", "Executables (*.exe *.cmd *.bat);;All Files (*)"
        )
        if file_path:
            self.ide_pycharm_path.setText(file_path)

    def browse_antigravity_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Antigravity IDE Executable", "", "Executables (*.exe);;All Files (*)"
        )
        if file_path:
            self.ide_antigravity_path.setText(file_path)


    def setup_app_tab(self):
        layout = QFormLayout(self.app_tab)

        # Default Source
        self.default_source_combo.addItem("Text", "text")
        self.default_source_combo.addItem("Image", "image")
        self.default_source_combo.addItem("Audio", "audio")

        current_source = self.config.get("default_source", "text")
        idx = self.default_source_combo.findData(current_source)
        if idx >= 0:
            self.default_source_combo.setCurrentIndex(idx)

        layout.addRow("Default Source:", self.default_source_combo)

        # Output Mode
        self.output_mode_popup = QCheckBox("Popup Notification")
        self.output_mode_audio = QCheckBox("Text-to-Speech (Audio)")

        current_modes = self.config.get("output_mode", ["popup"])
        self.output_mode_popup.setChecked("popup" in current_modes)
        self.output_mode_audio.setChecked("audio" in current_modes)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.output_mode_popup)
        mode_layout.addWidget(self.output_mode_audio)
        layout.addRow("Output Mode:", mode_layout)

        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        layout.addRow("Opacity:", opacity_layout)

        self.save_images.setChecked(
            self.config.get("save_images", True)
        )
        layout.addRow("Save Images:", self.save_images)

        # Background Mode
        self.background_mode.setChecked(self.config.get("background", False))
        layout.addRow("Background Mode:", self.background_mode)

        # Show Control Panel
        self.show_control_panel.setChecked(self.config.get("show_control_panel", False))
        layout.addRow("Control Panel:", self.show_control_panel)

        # Hide from capture
        self.hide_from_capture.setChecked(self.config.get("hide_from_capture", True))
        self.hide_from_capture.setToolTip(
            "When enabled, all overlay windows are invisible to screen sharing,\n"
            "recording, and capture tools.\n"
            "• Windows 10 2004+: SetWindowDisplayAffinity\n"
            "• macOS: NSWindow.setSharingType (requires pyobjc-framework-Cocoa)\n"
            "• Linux: not supported (no universal X11/Wayland API)"
        )
        layout.addRow("Screen Capture:", self.hide_from_capture)

        # IDE Paths
        pycharm_layout = QHBoxLayout()
        pycharm_layout.addWidget(self.ide_pycharm_path)
        browse_pycharm_btn = QPushButton("Browse...")
        browse_pycharm_btn.clicked.connect(self.browse_pycharm_path)
        pycharm_layout.addWidget(browse_pycharm_btn)
        layout.addRow("PyCharm Executable Path:", pycharm_layout)

        antigravity_layout = QHBoxLayout()
        antigravity_layout.addWidget(self.ide_antigravity_path)
        browse_antigravity_btn = QPushButton("Browse...")
        browse_antigravity_btn.clicked.connect(self.browse_antigravity_path)
        antigravity_layout.addWidget(browse_antigravity_btn)
        layout.addRow("Antigravity IDE Path:", antigravity_layout)

        layout.addRow("Antigravity Service URL:", self.antigravity_service_url)

        # Periodic Screenshots
        layout.addRow(QLabel("<b>Periodic Screenshots</b>"))

        self.periodic_screenshots_enabled.setChecked(
            self.config.get("periodic_screenshots_enabled", False)
        )
        layout.addRow("Periodic Screenshots:", self.periodic_screenshots_enabled)

        self.periodic_screenshots_interval.setPlaceholderText("e.g. 15")
        layout.addRow("Screenshot Interval (s):", self.periodic_screenshots_interval)

        self.periodic_screenshots_on_activity.setChecked(
            self.config.get("periodic_screenshots_on_activity", False)
        )
        layout.addRow("Activity Trigger:", self.periodic_screenshots_on_activity)

        self.periodic_screenshots_activity_min_delay.setPlaceholderText("e.g. 5")
        self.periodic_screenshots_activity_min_delay.setEnabled(
            self.periodic_screenshots_on_activity.isChecked()
        )
        self.periodic_screenshots_on_activity.toggled.connect(
            self.periodic_screenshots_activity_min_delay.setEnabled
        )
        layout.addRow("Activity Min Delay (s):", self.periodic_screenshots_activity_min_delay)

        self.track_active_window.setChecked(
            self.config.get("track_active_window", True)
        )
        self.track_active_window.setToolTip(
            "Record the active application name and window title\n"
            "alongside each periodic screenshot.\n"
            "Metadata is saved as a JSON sidecar file and displayed\n"
            "on the Session Timeline as coloured app spans."
        )
        layout.addRow("Window Tracking:", self.track_active_window)

    def setup_audio_tab(self):
        """Build the Audio & Speech tab.

        Contains TTS settings, audio devices, transcription/translation
        language, and speech recognition options.
        """
        layout = QFormLayout(self.audio_tab)

        # --- TTS Settings ---
        layout.addRow(QLabel("<b>Text-to-Speech</b>"))

        # TTS Piper settings
        piper_model_layout = QHBoxLayout()
        piper_model_layout.addWidget(self.piper_model)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_piper_model)
        piper_model_layout.addWidget(browse_btn)
        layout.addRow("Piper Voice Model Path:", piper_model_layout)

        self.tts_output_device_combo.addItem("Default System Output", None)

        audio_devices = get_audio_devices()
        for device in audio_devices:
            self.tts_output_device_combo.addItem(device["name"], device["name"])

        current_device_name = self.config.get("tts_output_device_name", None)

        if current_device_name is not None:
            idx = self.tts_output_device_combo.findData(current_device_name)
            if idx >= 0:
                self.tts_output_device_combo.setCurrentIndex(idx)

        layout.addRow("TTS Output Device:", self.tts_output_device_combo)

        # TTS language
        current_tts_lang = self.config.get("tts_language", "en")
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            if code:  # Skip "Auto-detect" for TTS
                self.tts_language.addItem(display_name, code)
        tts_idx = self.tts_language.findData(current_tts_lang)
        if tts_idx >= 0:
            self.tts_language.setCurrentIndex(tts_idx)
        layout.addRow("TTS Language:", self.tts_language)

        # --- Speech Recognition ---
        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Speech Recognition</b>"))

        # Audio Input Device
        self.audio_input_device_combo.addItem("Default System Input", None)

        try:
            from config.settings import get_audio_input_devices  # noqa: PLC0415

            input_audio_devices = get_audio_input_devices()
            for device in input_audio_devices:
                self.audio_input_device_combo.addItem(device["name"], device["name"])
        except Exception as e:
            print(f"Failed to load audio input devices: {e}")

        current_input_device_name = self.config.get("audio_input_device_name", None)
        if current_input_device_name is not None:
            idx = self.audio_input_device_combo.findData(current_input_device_name)
            if idx >= 0:
                self.audio_input_device_combo.setCurrentIndex(idx)

        layout.addRow("Audio Input Device:", self.audio_input_device_combo)

        # Transcription language
        current_trans_lang = self.config.get("transcription_language", "en")
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            self.transcription_language.addItem(display_name, code)
        trans_idx = self.transcription_language.findData(current_trans_lang)
        if trans_idx >= 0:
            self.transcription_language.setCurrentIndex(trans_idx)
        layout.addRow("Transcription Language:", self.transcription_language)

        self.realtime_transcription.setChecked(
            self.config.get("realtime_transcription", True)
        )
        layout.addRow("Real-time Transcription:", self.realtime_transcription)

        # --- Translation ---
        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Translation</b>"))

        # Translation language
        current_translation_lang = self.config.get("translation_language", "")
        self.translation_language.addItem("None (disabled)", "")
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            if code:  # Skip "Auto-detect" for translation
                self.translation_language.addItem(display_name, code)
        translation_idx = self.translation_language.findData(current_translation_lang)
        if translation_idx >= 0:
            self.translation_language.setCurrentIndex(translation_idx)
        self.translation_language.setToolTip(
            "When set, WhisperLive translates the transcribed audio\n"
            "into the selected language in real-time.\n"
            "Subtitles will show the translated text."
        )
        layout.addRow("Translation Language:", self.translation_language)

        # --- Session ---
        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Session</b>"))

        self.save_transcriptions.setChecked(
            self.config.get("save_transcriptions", True)
        )
        layout.addRow("Save Transcriptions:", self.save_transcriptions)

        self.auto_summarize_transcription.setChecked(
            self.config.get("auto_summarize_transcription", False)
        )
        layout.addRow("Auto-summarize:", self.auto_summarize_transcription)
        
        self.summarize_transcription_prompt.setPlaceholderText("e.g. Summarize the following transcribed conversation:")
        layout.addRow("Summary Prompt:", self.summarize_transcription_prompt)

        self.speaker_name.setPlaceholderText("e.g. interviewer")
        self.speaker_name.setToolTip(
            "Name attributed to the speaker in transcription files.\n"
            "Each transcription segment will be prefixed with [name]."
        )
        layout.addRow("Speaker Name:", self.speaker_name)

    def setup_llm_tab(self):
        """Build the LLM Settings tab.

        Contains API keys/URLs for LLM providers and retry configuration.
        """
        layout = QFormLayout(self.llm_tab)

        # API Keys & URLs
        layout.addRow("Ollama URL:", self.ollama_url)

        self.gemini_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Gemini API Key:", self.gemini_api_key)

        # LLM Retry
        self.llm_max_retries.setPlaceholderText("e.g. 3")
        self.llm_max_retries.setToolTip(
            "Maximum number of retry attempts when the LLM returns a\n"
            "transient error (503, rate limit, connection issue, etc.).\n"
            "Set to 0 to disable retries."
        )
        layout.addRow("Max Retries:", self.llm_max_retries)

        self.llm_retry_base_delay.setPlaceholderText("e.g. 5")
        self.llm_retry_base_delay.setToolTip(
            "Base delay in seconds for exponential backoff between retries.\n"
            "Actual delays: base × 2^attempt (e.g. 5s → 10s → 20s)."
        )
        layout.addRow("Retry Base Delay (s):", self.llm_retry_base_delay)

        hint = QLabel(
            "Configure LLM provider connections and retry behavior.\n"
            "Retries apply to transient errors like 503 (service unavailable),\n"
            "rate limits, and connection failures.\n"
            "Model selection is configured per-profile in the Profile Settings tab."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)

    def setup_profile_tab(self):
        layout = QVBoxLayout(self.profile_tab)

        # Profile selection
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Active Profile:"))
        self.populate_profiles()
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        h_layout.addWidget(self.profile_combo)
        layout.addLayout(h_layout)

        # Profile Form
        form_layout = QFormLayout(self.profile_form)

        form_layout.addRow("Profile Name:", self.prof_name)

        self.prof_llm_engine.addItems(["gemini", "ollama", "google-genai", "antigravity"])
        self.prof_llm_engine.currentTextChanged.connect(self.update_model_dropdowns)
        form_layout.addRow("LLM Engine:", self.prof_llm_engine)

        form_layout.addRow("Main Model:", self.prof_model)

        form_layout.addRow("Fallback Model:", self.prof_fallback_model)

        self.prof_ocr_engine.addItems(["none", "paddleocr", "remote_paddle"])
        form_layout.addRow("OCR Engine:", self.prof_ocr_engine)

        self.populate_prompts()
        form_layout.addRow("Prompt:", self.prof_prompt)

        form_layout.addRow("", self.prof_enable_chat_sessions)

        layout.addWidget(self.profile_form)
        layout.addStretch()

        if self.profiles:
            active_id = self.config.get("active_profile_id", self.profiles[0]["id"])
            index = next(
                (i for i, p in enumerate(self.profiles) if p["id"] == active_id), 0
            )
            self.profile_combo.setCurrentIndex(index)
            self.on_profile_changed(index)

    def populate_profiles(self):
        self.profile_combo.clear()
        for p in self.profiles:
            self.profile_combo.addItem(p["name"], p["id"])

    def populate_prompts(self):
        self.prof_prompt.clear()
        for p in self.prompts:
            self.prof_prompt.addItem(
                p.get("description", p.get("id", "Unknown")), p["id"]
            )

    def update_model_dropdowns(self, engine):
        self.prof_model.clear()
        self.prof_fallback_model.clear()
        self.prof_fallback_model.addItem("None", "None")

        models = self.models_data.get(engine, [])
        for m in models:
            self.prof_model.addItem(m["name"], m["id"])
            self.prof_fallback_model.addItem(m["name"], m["id"])

        # Try to restore previous selection if valid
        if hasattr(self, "_current_profile_data"):
            model_id = self._current_profile_data.get("model")
            fallback_id = self._current_profile_data.get("fallback_model")

            idx = self.prof_model.findData(model_id)
            if idx >= 0:
                self.prof_model.setCurrentIndex(idx)

            idx2 = self.prof_fallback_model.findData(fallback_id)
            if idx2 >= 0:
                self.prof_fallback_model.setCurrentIndex(idx2)

    def on_profile_changed(self, index):
        if index < 0 or index >= len(self.profiles):
            return
        profile = self.profiles[index]
        self._current_profile_data = profile

        self.prof_name.setText(profile.get("name", ""))

        engine = profile.get("llm_engine", "gemini")
        self.prof_llm_engine.setCurrentText(engine)
        self.update_model_dropdowns(engine)

        self.prof_ocr_engine.setCurrentText(profile.get("ocr_engine", "none"))

        prompt_id = profile.get("prompt_id", "default")
        idx = self.prof_prompt.findData(prompt_id)
        if idx >= 0:
            self.prof_prompt.setCurrentIndex(idx)
            
        self.prof_enable_chat_sessions.setChecked(profile.get("enable_chat_sessions", True))

    def save_current_profile(self):
        index = self.profile_combo.currentIndex()
        if index < 0 or index >= len(self.profiles):
            return

        profile = self.profiles[index]
        profile["name"] = self.prof_name.text()
        profile["llm_engine"] = self.prof_llm_engine.currentText()
        profile["model"] = self.prof_model.currentData()
        profile["fallback_model"] = self.prof_fallback_model.currentData()
        profile["ocr_engine"] = self.prof_ocr_engine.currentText()
        profile["prompt_id"] = self.prof_prompt.currentData()
        profile["enable_chat_sessions"] = self.prof_enable_chat_sessions.isChecked()

        # Update combo box text
        self.profile_combo.setItemText(index, profile["name"])

    def setup_warmup_tab(self):
        layout = QFormLayout(self.warmup_tab)

        self.warmup_ocr.setChecked(self.config.get("warmup_ocr", True))
        self.warmup_llm.setChecked(self.config.get("warmup_llm", True))
        self.warmup_tts.setChecked(self.config.get("warmup_tts", False))
        self.warmup_sr.setChecked(self.config.get("warmup_speech_recognition", True))
        self.warmup_realtime_transcription.setChecked(
            self.config.get("warmup_realtime_transcription", False)
        )

        layout.addRow("OCR:", self.warmup_ocr)
        layout.addRow("LLM:", self.warmup_llm)
        layout.addRow("TTS:", self.warmup_tts)
        layout.addRow("Speech Recognition:", self.warmup_sr)
        layout.addRow("Real-time Transcription:", self.warmup_realtime_transcription)

    def setup_remote_control_tab(self):
        """Build the Remote Control settings tab.

        Allows the user to enable the Android remote control server, set the
        network interface it binds to, and choose the TCP port.
        Restart required for changes to take effect.
        """
        layout = QFormLayout(self.remote_control_tab)

        self.enable_remote_control.setChecked(
            self.config.get("enable_remote_control", False)
        )
        layout.addRow("Enable Remote Control:", self.enable_remote_control)

        self.remote_control_host.setPlaceholderText("e.g. 0.0.0.0 (all interfaces)")
        layout.addRow("Host / Interface:", self.remote_control_host)

        self.remote_control_port.setPlaceholderText("e.g. 8080")
        layout.addRow("Port:", self.remote_control_port)

        self.mouse_sensitivity.setPlaceholderText("e.g. 1.5")
        layout.addRow("Mouse Sensitivity:", self.mouse_sensitivity)

        self.remote_mouse_idle_timeout.setPlaceholderText("e.g. 3.0")
        layout.addRow("Mouse Idle Timeout (s):", self.remote_mouse_idle_timeout)

        self.share_response_with_android.setChecked(
            self.config.get("share_response_with_android", False)
        )
        layout.addRow("Response Screenshot:", self.share_response_with_android)

        hint = QLabel(
            "When enabled, SnapSolve listens for connections from the Android remote "
            "control app on the specified port.\n"
            "Make sure your firewall allows inbound TCP traffic on that port.\n"
            "When 'Share LLM response screenshot' is enabled, a full-page screenshot\n"
            "of each response is sent to the connected Android app for viewing.\n"
            "A restart is required for changes to take effect."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)

    def setup_shortcuts_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.shortcuts_layout = QFormLayout(container)

        # Default actions
        default_actions = [
            "capture",
            "reselect",
            "multi_capture",
            "end_multi_capture",
            "cancel_multi_capture",
            "toggle_panel",
            "toggle_all_widgets",
            "new_chat_session",
            "toggle_stitching",
            "cycle_source",
            "open_session_browser",
            "quit_app",
        ]

        hotkeys_config = self.config.get("hotkeys", [])
        hotkey_dict = {hk["action"]: hk["key"] for hk in hotkeys_config}

        for action in default_actions:
            inp = QLineEdit(hotkey_dict.get(action, ""))
            self.shortcuts_layout.addRow(f"{action.replace('_', ' ').title()}:", inp)
            self.shortcut_inputs[action] = inp

        scroll.setWidget(container)

        layout = QVBoxLayout(self.shortcuts_tab)
        layout.addWidget(scroll)

    def save_all(self):
        # Save App Settings
        self.config["default_source"] = self.default_source_combo.currentData()

        modes = []
        if self.output_mode_popup.isChecked():
            modes.append("popup")
        if self.output_mode_audio.isChecked():
            modes.append("audio")
        self.config["output_mode"] = modes

        self.config["piper_model"] = (
            self.piper_model.text() or "en_US-lessac-medium.onnx"
        )
        self.config["background"] = self.background_mode.isChecked()
        self.config["show_control_panel"] = self.show_control_panel.isChecked()
        self.config["hide_from_capture"] = self.hide_from_capture.isChecked()
        self.config["realtime_transcription"] = self.realtime_transcription.isChecked()
        self.config["transcription_language"] = (
            self.transcription_language.currentData() or "en"
        )
        self.config["tts_language"] = (
            self.tts_language.currentData() or "en"
        )
        self.config["translation_language"] = (
            self.translation_language.currentData() or ""
        )
        self.config["save_transcriptions"] = self.save_transcriptions.isChecked()
        self.config["auto_summarize_transcription"] = self.auto_summarize_transcription.isChecked()
        self.config["summarize_transcription_prompt"] = self.summarize_transcription_prompt.text()
        self.config["save_images"] = self.save_images.isChecked()
        self.config["speaker_name"] = self.speaker_name.text().strip() or "interviewer"
        self.config["warmup_ocr"] = self.warmup_ocr.isChecked()
        self.config["warmup_llm"] = self.warmup_llm.isChecked()
        self.config["warmup_tts"] = self.warmup_tts.isChecked()
        self.config["warmup_speech_recognition"] = self.warmup_sr.isChecked()
        self.config["warmup_realtime_transcription"] = (
            self.warmup_realtime_transcription.isChecked()
        )
        self.config["ollama_url"] = self.ollama_url.text()
        self.config["gemini_api_key"] = self.gemini_api_key.text()
        self.config["ide_pycharm_path"] = self.ide_pycharm_path.text().strip() or "pycharm"
        
        default_antigravity = str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE" / "Antigravity IDE.exe")
        self.config["ide_antigravity_path"] = self.ide_antigravity_path.text().strip() or default_antigravity
        self.config["antigravity_service_url"] = self.antigravity_service_url.text().strip() or "http://localhost:8200"
        
        self.config["opacity"] = self.opacity_slider.value() / 100.0

        # LLM Retry
        try:
            self.config["llm_max_retries"] = int(
                self.llm_max_retries.text().strip() or "3"
            )
        except ValueError:
            self.config["llm_max_retries"] = 3

        try:
            self.config["llm_retry_base_delay"] = float(
                self.llm_retry_base_delay.text().strip() or "5"
            )
        except ValueError:
            self.config["llm_retry_base_delay"] = 5

        self.config["tts_output_device_name"] = (
            self.tts_output_device_combo.currentData()
        )
        self.config["audio_input_device_name"] = (
            self.audio_input_device_combo.currentData()
        )

        # Remote Control settings
        self.config["enable_remote_control"] = self.enable_remote_control.isChecked()
        self.config["remote_control_host"] = (
            self.remote_control_host.text().strip() or "0.0.0.0"
        )
        self.config["remote_control_port"] = int(
            self.remote_control_port.text().strip() or "8080"
        )
        try:
            self.config["mouse_sensitivity"] = float(
                self.mouse_sensitivity.text().strip() or "1.5"
            )
        except ValueError:
            self.config["mouse_sensitivity"] = 1.5

        try:
            self.config["remote_mouse_idle_timeout"] = float(
                self.remote_mouse_idle_timeout.text().strip() or "3.0"
            )
        except ValueError:
            self.config["remote_mouse_idle_timeout"] = 3.0

        self.config["share_response_with_android"] = (
            self.share_response_with_android.isChecked()
        )

        # Clean up legacy piper path if it exists
        if "piper_path" in self.config:
            del self.config["piper_path"]

        # Periodic Screenshots
        self.config["periodic_screenshots_enabled"] = (
            self.periodic_screenshots_enabled.isChecked()
        )
        try:
            self.config["periodic_screenshots_interval"] = int(
                self.periodic_screenshots_interval.text().strip() or "15"
            )
        except ValueError:
            self.config["periodic_screenshots_interval"] = 15

        self.config["periodic_screenshots_on_activity"] = (
            self.periodic_screenshots_on_activity.isChecked()
        )
        try:
            self.config["periodic_screenshots_activity_min_delay"] = int(
                self.periodic_screenshots_activity_min_delay.text().strip() or "5"
            )
        except ValueError:
            self.config["periodic_screenshots_activity_min_delay"] = 5

        self.config["track_active_window"] = self.track_active_window.isChecked()

        # Save Profile Settings
        self.save_current_profile()
        index = self.profile_combo.currentIndex()
        if index >= 0:
            self.config["active_profile_id"] = self.profiles[index]["id"]

        # Save Shortcuts
        hotkeys = []
        for action, inp in self.shortcut_inputs.items():
            key = inp.text().strip()
            if key:
                hotkeys.append({"action": action, "key": key})
        self.config["hotkeys"] = hotkeys

        self.save_json(self.config_path, self.config)
        self.save_json(self.profiles_path, self.profiles)

        QMessageBox.information(
            self,
            "Success",
            "Configuration saved successfully!\nPlease restart the application for some changes to take effect.",
        )
        self.accept()


def open_config_ui(config_path, models_path, profiles_path, prompts_path):
    existing_app = QApplication.instance()
    is_temp_app = False
    if not existing_app:
        existing_app = QApplication(sys.argv)
        is_temp_app = True

    dialog = ConfigUI(config_path, models_path, profiles_path, prompts_path)
    dialog.exec()
    result_should_run = dialog.should_run

    if is_temp_app:
        existing_app.quit()

    return result_should_run


if __name__ == "__main__":
    # Temporarily create app for the config UI if run directly
    # Only create if it doesn't exist
    if not QApplication.instance():
        app = QApplication(sys.argv)

    should_run = open_config_ui(
        "config/config.json",
        "config/llm_models.json",
        "config/profiles.json",
        "config/prompts.json",
    )

    if should_run:
        print("Launching application...")
        # Since we are executing as a script, we can run main.py via subprocess or import it.
        # It's cleaner to exec into main.py
        import subprocess

        subprocess.Popen([sys.executable, "main.py"])
        sys.exit(0)
