import json
import os
import sys
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox,
    QCheckBox, QGroupBox, QFormLayout, QScrollArea, QDialogButtonBox, QSpinBox
)
from PyQt6.QtCore import Qt

class ConfigUI(QDialog):
    def __init__(self, config_path, models_path, profiles_path, prompts_path):
        super().__init__()
        self.config_path = config_path
        self.models_path = models_path
        self.profiles_path = profiles_path
        self.prompts_path = prompts_path

        self.setWindowTitle("Application Configuration")
        self.resize(600, 500)

        # Load configurations
        self.config = self.load_json(self.config_path, {})
        self.models_data = self.load_json(self.models_path, {})
        self.profiles = self.load_json(self.profiles_path, [])
        self.prompts = self.load_json(self.prompts_path, [])

        self.init_ui()

    def load_json(self, path, default):
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
        return default

    def save_json(self, path, data):
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save {path}:\n{e}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.app_tab = QWidget()
        self.profile_tab = QWidget()
        self.shortcuts_tab = QWidget()

        self.tabs.addTab(self.app_tab, "Application Settings")
        self.tabs.addTab(self.profile_tab, "Profile Settings")
        self.tabs.addTab(self.shortcuts_tab, "Keyboard Shortcuts")

        self.setup_app_tab()
        self.setup_profile_tab()
        self.setup_shortcuts_tab()

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.save_all)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def setup_app_tab(self):
        layout = QFormLayout(self.app_tab)

        # Output Mode
        self.output_mode_popup = QCheckBox("Popup Notification")
        self.output_mode_audio = QCheckBox("Text-to-Speech (Audio)")

        current_modes = self.config.get('output_mode', ['popup'])
        self.output_mode_popup.setChecked('popup' in current_modes)
        self.output_mode_audio.setChecked('audio' in current_modes)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self.output_mode_popup)
        mode_layout.addWidget(self.output_mode_audio)
        layout.addRow("Output Mode:", mode_layout)

        # Fallback Language
        self.fallback_language = QLineEdit(self.config.get('fallback_language', 'python'))
        layout.addRow("Fallback Lexer Language:", self.fallback_language)

        # Voice ID
        self.voice_id = QLineEdit(self.config.get('voice_id', ''))
        layout.addRow("Voice ID (Optional):", self.voice_id)

        # Background Mode
        self.background_mode = QCheckBox("Run in system tray")
        self.background_mode.setChecked(self.config.get('background', False))
        layout.addRow("Background Mode:", self.background_mode)

        # Show Control Panel
        self.show_control_panel = QCheckBox("Show control panel on startup")
        self.show_control_panel.setChecked(self.config.get('show_control_panel', False))
        layout.addRow("Control Panel:", self.show_control_panel)

        # API Keys & URLs
        self.ollama_url = QLineEdit(self.config.get('ollama_url', 'http://localhost:11434'))
        layout.addRow("Ollama URL:", self.ollama_url)

        self.google_genai_api_key = QLineEdit(self.config.get('google_genai_api_key', ''))
        self.google_genai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Google GenAI API Key:", self.google_genai_api_key)

    def setup_profile_tab(self):
        layout = QVBoxLayout(self.profile_tab)

        # Profile selection
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Active Profile:"))
        self.profile_combo = QComboBox()
        self.populate_profiles()
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        h_layout.addWidget(self.profile_combo)
        layout.addLayout(h_layout)

        # Profile Form
        self.profile_form = QWidget()
        form_layout = QFormLayout(self.profile_form)

        self.prof_name = QLineEdit()
        form_layout.addRow("Profile Name:", self.prof_name)

        self.prof_llm_engine = QComboBox()
        self.prof_llm_engine.addItems(["gemini", "ollama", "google-genai"])
        self.prof_llm_engine.currentTextChanged.connect(self.update_model_dropdowns)
        form_layout.addRow("LLM Engine:", self.prof_llm_engine)

        self.prof_model = QComboBox()
        form_layout.addRow("Main Model:", self.prof_model)

        self.prof_fallback_model = QComboBox()
        form_layout.addRow("Fallback Model:", self.prof_fallback_model)

        self.prof_ocr_engine = QComboBox()
        self.prof_ocr_engine.addItems(["none", "paddleocr"])
        form_layout.addRow("OCR Engine:", self.prof_ocr_engine)

        self.prof_prompt = QComboBox()
        self.populate_prompts()
        form_layout.addRow("Prompt:", self.prof_prompt)

        layout.addWidget(self.profile_form)
        layout.addStretch()

        if self.profiles:
            active_id = self.config.get('active_profile_id', self.profiles[0]['id'])
            index = next((i for i, p in enumerate(self.profiles) if p['id'] == active_id), 0)
            self.profile_combo.setCurrentIndex(index)
            self.on_profile_changed(index)

    def populate_profiles(self):
        self.profile_combo.clear()
        for p in self.profiles:
            self.profile_combo.addItem(p['name'], p['id'])

    def populate_prompts(self):
        self.prof_prompt.clear()
        for p in self.prompts:
            self.prof_prompt.addItem(p.get('description', p.get('id', 'Unknown')), p['id'])

    def update_model_dropdowns(self, engine):
        self.prof_model.clear()
        self.prof_fallback_model.clear()
        self.prof_fallback_model.addItem("None", "None")

        models = self.models_data.get(engine, [])
        for m in models:
            self.prof_model.addItem(m['name'], m['id'])
            self.prof_fallback_model.addItem(m['name'], m['id'])

        # Try to restore previous selection if valid
        if hasattr(self, '_current_profile_data'):
            model_id = self._current_profile_data.get('model')
            fallback_id = self._current_profile_data.get('fallback_model')

            idx = self.prof_model.findData(model_id)
            if idx >= 0: self.prof_model.setCurrentIndex(idx)

            idx2 = self.prof_fallback_model.findData(fallback_id)
            if idx2 >= 0: self.prof_fallback_model.setCurrentIndex(idx2)

    def on_profile_changed(self, index):
        if index < 0 or index >= len(self.profiles): return
        profile = self.profiles[index]
        self._current_profile_data = profile

        self.prof_name.setText(profile.get('name', ''))

        engine = profile.get('llm_engine', 'gemini')
        self.prof_llm_engine.setCurrentText(engine)
        self.update_model_dropdowns(engine)

        self.prof_ocr_engine.setCurrentText(profile.get('ocr_engine', 'none'))

        prompt_id = profile.get('prompt_id', 'default')
        idx = self.prof_prompt.findData(prompt_id)
        if idx >= 0: self.prof_prompt.setCurrentIndex(idx)

    def save_current_profile(self):
        index = self.profile_combo.currentIndex()
        if index < 0 or index >= len(self.profiles): return

        profile = self.profiles[index]
        profile['name'] = self.prof_name.text()
        profile['llm_engine'] = self.prof_llm_engine.currentText()
        profile['model'] = self.prof_model.currentData()
        profile['fallback_model'] = self.prof_fallback_model.currentData()
        profile['ocr_engine'] = self.prof_ocr_engine.currentText()
        profile['prompt_id'] = self.prof_prompt.currentData()

        # Update combo box text
        self.profile_combo.setItemText(index, profile['name'])

    def setup_shortcuts_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.shortcuts_layout = QFormLayout(container)

        self.shortcut_inputs = {}

        # Default actions
        default_actions = [
            'capture', 'reselect', 'multi_capture', 'end_multi_capture',
            'cancel_multi_capture', 'toggle_panel', 'new_chat_session',
            'toggle_stitching', 'cycle_source'
        ]

        hotkeys_config = self.config.get('hotkeys', [])
        hotkey_dict = {hk['action']: hk['key'] for hk in hotkeys_config}

        for action in default_actions:
            inp = QLineEdit(hotkey_dict.get(action, ''))
            self.shortcuts_layout.addRow(f"{action.replace('_', ' ').title()}:", inp)
            self.shortcut_inputs[action] = inp

        scroll.setWidget(container)

        layout = QVBoxLayout(self.shortcuts_tab)
        layout.addWidget(scroll)

    def save_all(self):
        # Save App Settings
        modes = []
        if self.output_mode_popup.isChecked(): modes.append('popup')
        if self.output_mode_audio.isChecked(): modes.append('audio')
        self.config['output_mode'] = modes

        self.config['fallback_language'] = self.fallback_language.text()
        self.config['voice_id'] = self.voice_id.text() or None
        self.config['background'] = self.background_mode.isChecked()
        self.config['show_control_panel'] = self.show_control_panel.isChecked()
        self.config['ollama_url'] = self.ollama_url.text()
        self.config['google_genai_api_key'] = self.google_genai_api_key.text()

        # Save Profile Settings
        self.save_current_profile()
        index = self.profile_combo.currentIndex()
        if index >= 0:
            self.config['active_profile_id'] = self.profiles[index]['id']

        # Save Shortcuts
        hotkeys = []
        for action, inp in self.shortcut_inputs.items():
            key = inp.text().strip()
            if key:
                hotkeys.append({"action": action, "key": key})
        self.config['hotkeys'] = hotkeys

        self.save_json(self.config_path, self.config)
        self.save_json(self.profiles_path, self.profiles)

        QMessageBox.information(self, "Success", "Configuration saved successfully!\nPlease restart the application for some changes to take effect.")
        self.accept()

def open_config_ui(config_path, models_path, profiles_path, prompts_path):
    app = QApplication.instance()
    is_temp_app = False
    if not app:
        app = QApplication(sys.argv)
        is_temp_app = True

    dialog = ConfigUI(config_path, models_path, profiles_path, prompts_path)
    dialog.exec()

    if is_temp_app:
        app.quit()

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    open_config_ui("config/config.json", "config/llm_models.json", "config/profiles.json", "config/prompts.json")
