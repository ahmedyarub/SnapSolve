with open('ui/config_ui.py', 'r') as f:
    content = f.read()

# 1. Update Tabs setup
find_str = """        # Create tabs
        self.app_tab = QWidget()
        self.profile_tab = QWidget()
        self.shortcuts_tab = QWidget()

        self.tabs.addTab(self.app_tab, "Application Settings")
        self.tabs.addTab(self.profile_tab, "Profile Settings")
        self.tabs.addTab(self.shortcuts_tab, "Keyboard Shortcuts")

        self.setup_app_tab()
        self.setup_profile_tab()
        self.setup_shortcuts_tab()"""

replace_str = """        # Create tabs
        self.app_tab = QWidget()
        self.profile_tab = QWidget()
        self.warmup_tab = QWidget()
        self.shortcuts_tab = QWidget()

        self.tabs.addTab(self.app_tab, "Application Settings")
        self.tabs.addTab(self.profile_tab, "Profile Settings")
        self.tabs.addTab(self.warmup_tab, "Warmup Settings")
        self.tabs.addTab(self.shortcuts_tab, "Keyboard Shortcuts")

        self.setup_app_tab()
        self.setup_profile_tab()
        self.setup_warmup_tab()
        self.setup_shortcuts_tab()"""

content = content.replace(find_str, replace_str)

# 2. Add setup_warmup_tab
warmup_func = """
    def setup_warmup_tab(self):
        layout = QFormLayout(self.warmup_tab)

        self.warmup_ocr = QCheckBox("Warmup OCR Engine")
        self.warmup_ocr.setChecked(self.config.get('warmup_ocr', True))

        self.warmup_llm = QCheckBox("Warmup LLM Engine")
        self.warmup_llm.setChecked(self.config.get('warmup_llm', True))

        self.warmup_tts = QCheckBox("Warmup TTS Engine")
        self.warmup_tts.setChecked(self.config.get('warmup_tts', False))

        self.warmup_sr = QCheckBox("Warmup Speech Recognition")
        self.warmup_sr.setChecked(self.config.get('warmup_speech_recognition', True))

        layout.addRow("OCR:", self.warmup_ocr)
        layout.addRow("LLM:", self.warmup_llm)
        layout.addRow("TTS:", self.warmup_tts)
        layout.addRow("Speech Recognition:", self.warmup_sr)
"""

content = content.replace("    def setup_shortcuts_tab(self):", warmup_func + "\n    def setup_shortcuts_tab(self):")

# 3. Double check save method
if "self.config['warmup_speech_recognition'] = self.warmup_sr.isChecked()" not in content:
    find_str_save = """        self.config['warmup_ocr'] = self.warmup_ocr.isChecked()
        self.config['warmup_llm'] = self.warmup_llm.isChecked()
        self.config['warmup_tts'] = self.warmup_tts.isChecked()"""

    replace_str_save = """        self.config['warmup_ocr'] = self.warmup_ocr.isChecked()
        self.config['warmup_llm'] = self.warmup_llm.isChecked()
        self.config['warmup_tts'] = self.warmup_tts.isChecked()
        self.config['warmup_speech_recognition'] = self.warmup_sr.isChecked()"""

    content = content.replace(find_str_save, replace_str_save)

with open('ui/config_ui.py', 'w') as f:
    f.write(content)
