import json
import os
import sys

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
)

from config.settings import get_audio_devices


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
    return default


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
        self.google_genai_api_key = QLineEdit(
            self.config.get("google_genai_api_key", "")
        )
        self.profile_combo = QComboBox()
        self.profile_form = QWidget()
        self.prof_name = QLineEdit()
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

        self.tabs = QTabWidget()
        self.warmup_tab = QWidget()
        self.default_source_combo = QComboBox()
        self.piper_model = QLineEdit(
            self.config.get("piper_model", "en_US-lessac-medium.onnx")
        )
        self.tts_output_device_combo = QComboBox()
        self.audio_input_device_combo = QComboBox()
        self.background_mode = QCheckBox("Run in system tray")
        self.realtime_transcription = QCheckBox("Enable Real-time Transcription")
        self.save_transcriptions = QCheckBox("Save Transcriptions to Files")
        self.warmup_ocr = QCheckBox("Warmup OCR Engine")
        self.warmup_llm = QCheckBox("Warmup LLM Engine")
        self.warmup_tts = QCheckBox("Warmup TTS Engine")
        self.warmup_sr = QCheckBox("Warmup Speech Recognition")
        self.warmup_realtime_transcription = QCheckBox("Warmup Real-time Transcription")
        self._current_profile_data = None

        # Remote Control tab widgets
        self.remote_control_tab = QWidget()
        self.enable_remote_control = QCheckBox("Enable Remote Control Server")
        self.remote_control_host = QLineEdit(
            self.config.get("remote_control_host", "0.0.0.0")
        )
        self.remote_control_port = QLineEdit(
            str(self.config.get("remote_control_port", 8080))
        )

        self.setWindowTitle("Application Configuration")
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
        self.tabs.addTab(self.profile_tab, "Profile Settings")
        self.tabs.addTab(self.warmup_tab, "Warmup Settings")
        self.tabs.addTab(self.shortcuts_tab, "Keyboard Shortcuts")
        self.tabs.addTab(self.remote_control_tab, "Remote Control")

        self.setup_app_tab()
        self.setup_profile_tab()
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

        # Audio Input Device
        self.audio_input_device_combo.addItem("Default System Input", None)

        try:
            from config.settings import get_audio_input_devices

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

        self.realtime_transcription.setChecked(
            self.config.get("realtime_transcription", True)
        )
        layout.addRow("Real-time Transcription:", self.realtime_transcription)

        self.save_transcriptions.setChecked(
            self.config.get("save_transcriptions", True)
        )
        layout.addRow("Save Transcriptions:", self.save_transcriptions)

        # Background Mode
        self.background_mode.setChecked(self.config.get("background", False))
        layout.addRow("Background Mode:", self.background_mode)

        # Show Control Panel
        self.show_control_panel.setChecked(self.config.get("show_control_panel", False))
        layout.addRow("Control Panel:", self.show_control_panel)

        # API Keys & URLs
        layout.addRow("Ollama URL:", self.ollama_url)

        self.google_genai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Google GenAI API Key:", self.google_genai_api_key)

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

        self.prof_llm_engine.addItems(["gemini", "ollama", "google-genai"])
        self.prof_llm_engine.currentTextChanged.connect(self.update_model_dropdowns)
        form_layout.addRow("LLM Engine:", self.prof_llm_engine)

        form_layout.addRow("Main Model:", self.prof_model)

        form_layout.addRow("Fallback Model:", self.prof_fallback_model)

        self.prof_ocr_engine.addItems(["none", "paddleocr", "remote_paddle"])
        form_layout.addRow("OCR Engine:", self.prof_ocr_engine)

        self.populate_prompts()
        form_layout.addRow("Prompt:", self.prof_prompt)

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

        hint = QLabel(
            "When enabled, SnapSolve listens for connections from the Android remote "
            "control app on the specified port.\n"
            "Make sure your firewall allows inbound TCP traffic on that port.\n"
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
            "new_chat_session",
            "toggle_stitching",
            "cycle_source",
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
        self.config["realtime_transcription"] = self.realtime_transcription.isChecked()
        self.config["save_transcriptions"] = self.save_transcriptions.isChecked()
        self.config["warmup_ocr"] = self.warmup_ocr.isChecked()
        self.config["warmup_llm"] = self.warmup_llm.isChecked()
        self.config["warmup_tts"] = self.warmup_tts.isChecked()
        self.config["warmup_speech_recognition"] = self.warmup_sr.isChecked()
        self.config["warmup_realtime_transcription"] = (
            self.warmup_realtime_transcription.isChecked()
        )
        self.config["ollama_url"] = self.ollama_url.text()
        self.config["google_genai_api_key"] = self.google_genai_api_key.text()

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

        # Clean up legacy piper path if it exists
        if "piper_path" in self.config:
            del self.config["piper_path"]

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
