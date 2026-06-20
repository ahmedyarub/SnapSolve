import json
import os
import platform
import sys
from pathlib import Path

# Ensure PyCharm's Stop button kills the process immediately, even when
# a modal QDialog event loop (dialog.exec()) is blocking the main thread.
# The ctypes handler runs in a dedicated OS thread, bypassing Python's
# signal-handling limitations (which only fire between bytecodes).
if platform.system() == "Windows":
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    def _config_ui_ctrl_handler(ctrl_type):
        # CTRL_C_EVENT=0, CTRL_BREAK_EVENT=1, CTRL_CLOSE_EVENT=2
        os._exit(0)
        return True  # pragma: no cover

    ctypes.windll.kernel32.SetConsoleCtrlHandler(_config_ui_ctrl_handler, True)

# FORCE PyQt6 initialization at the VERY FIRST entry point
try:
    pass
except Exception:
    pass

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
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer
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
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Italian", "it"),
    ("Portuguese", "pt"),
    ("Russian", "ru"),
    ("Chinese", "zh"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("Turkish", "tr"),
    ("Polish", "pl"),
    ("Dutch", "nl"),
    ("Swedish", "sv"),
    ("Czech", "cs"),
    ("Romanian", "ro"),
    ("Hungarian", "hu"),
    ("Ukrainian", "uk"),
    ("Greek", "el"),
    ("Hebrew", "he"),
    ("Thai", "th"),
    ("Vietnamese", "vi"),
    ("Indonesian", "id"),
    ("Malay", "ms"),
]


class RefreshableComboBox(QComboBox):
    def __init__(self, parent=None, on_show_popup=None):
        super().__init__(parent)
        self.on_show_popup = on_show_popup

    def showPopup(self):
        if self.on_show_popup:
            self.on_show_popup()
        super().showPopup()


class ConfigUI(QDialog):
    def __init__(self, config_path, models_path, profiles_path, prompts_path):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

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
        self.gemini_api_key = QLineEdit(self.config.get("gemini_api_key", ""))
        self.openai_api_key = QLineEdit(self.config.get("openai_api_key", ""))
        self.anthropic_api_key = QLineEdit(self.config.get("anthropic_api_key", ""))
        self.groq_api_key = QLineEdit(self.config.get("groq_api_key", ""))
        self.openrouter_api_key = QLineEdit(self.config.get("openrouter_api_key", ""))

        # IDE paths
        default_antigravity = str(
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "Antigravity IDE"
            / "Antigravity IDE.exe"
        )
        self.ide_pycharm_path = QLineEdit(
            self.config.get("ide_pycharm_path", "pycharm")
        )
        self.ide_antigravity_path = QLineEdit(
            self.config.get("ide_antigravity_path", default_antigravity)
        )
        self.antigravity_service_url = QLineEdit(
            self.config.get("antigravity_service_url", "http://localhost:8200")
        )
        self.profile_combo = QComboBox()
        self.profile_form = QWidget()
        self.prof_name = QLineEdit()
        self.prof_enable_chat_sessions = QCheckBox("Enable Chat Sessions")
        self.prof_llm_engine = QComboBox()
        self.prof_model = QComboBox()
        self.prof_model.setEditable(True)
        self.prof_fallback_model = QComboBox()
        self.prof_fallback_model.setEditable(True)
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
        self.tts_output_device_combo = RefreshableComboBox(
            on_show_popup=self.refresh_audio_devices
        )
        self.audio_input_device_combo = RefreshableComboBox(
            on_show_popup=self.refresh_audio_devices
        )
        self.audio_loopback_device_combo = RefreshableComboBox(
            on_show_popup=self.refresh_audio_devices
        )
        self.background_mode = QCheckBox("Run in system tray")
        self.hide_from_capture = QCheckBox("Hide windows from screen capture")
        self.realtime_transcription = QCheckBox("Enable Real-time Transcription")
        self.show_audio_volume_bar = QCheckBox("Show Audio Volume Bar")
        self.post_recording_diarization = QCheckBox(
            "Post-Recording Speaker Diarization (WhisperX)"
        )
        self.diarization_model = QComboBox()
        self.delete_wav_after_diarization = QCheckBox(
            "Delete .wav files after Diarization"
        )
        self.enable_audio_enhancement = QCheckBox("Enable Audio Enhancement Pipeline")
        self.save_transcriptions = QCheckBox("Save Transcriptions to Files")
        self.auto_summarize_transcription = QCheckBox(
            "Auto-summarize transcription on stop"
        )
        self.summarize_transcription_prompt = QLineEdit(
            self.config.get(
                "summarize_transcription_prompt",
                "Summarize the following transcribed conversation:\n",
            )
        )
        self.transcription_language = QComboBox()
        self.transcription_model = QComboBox()
        self.tts_language = QComboBox()
        self.translation_language = QComboBox()
        self.save_images = QCheckBox("Save Captured Images to Session")
        self.speaker_name = QLineEdit(self.config.get("speaker_name", "interviewer"))
        self.warmup_ocr = QCheckBox("Warmup OCR Engine")
        self.warmup_llm = QCheckBox("Warmup LLM Engine")
        self.warmup_tts = QCheckBox("Warmup TTS Engine")
        self.warmup_sr = QCheckBox("Warmup Speech Recognition")
        self.warmup_realtime_transcription = QCheckBox("Warmup Real-time Transcription")
        self._current_profile_data = None

        # Real-time Analysis widgets
        self.realtime_analysis_tab = QWidget()
        self.realtime_correction_enabled = QCheckBox("Enable Real-time Correction")
        self.realtime_correction_fact_check = QCheckBox("Fact-Checking")
        self.realtime_correction_grammar = QCheckBox("Grammar \u0026 Pronunciation")
        self.realtime_correction_content_suggestions = QCheckBox("Content Suggestions")
        self.realtime_correction_window_size = QLineEdit(
            str(self.config.get("realtime_correction_window_size", 4))
        )

        # Profile: correction model
        self.prof_correction_model = QComboBox()

        # Search UI
        self._search_index: list[dict] = []  # [{label, tab_index, widget}]
        self._search_input = QLineEdit()
        self._search_results = QListWidget()
        self._highlighted_widget: QWidget | None = None
        self._highlighted_original_style: str = ""
        self._blink_timer: QTimer | None = None
        self._blink_count: int = 0
        self._blink_on: bool = False

        # Advanced options toggle
        self._advanced_mode: bool = False
        self._advanced_rows: list[tuple] = []
        self._all_tabs: list[tuple[QWidget, str, bool]] = []
        self._search_container: QWidget | None = None
        self._advanced_toggle_btn: QPushButton | None = None

        # Opacity slider
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(int(self.config.get("opacity", 0.8) * 100))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )

        # API & Remote Control tab widgets
        self.remote_control_tab = QWidget()
        self.logging_tab = QWidget()
        self.enable_api_server = QCheckBox("Enable API & Remote Control Server")
        self.api_server_host = QLineEdit(self.config.get("api_server_host", "0.0.0.0"))
        self.api_server_port = QLineEdit(str(self.config.get("api_server_port", 3031)))
        self.api_server_key = QLineEdit(self.config.get("api_server_key", ""))
        self.api_server_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_server_key.setPlaceholderText("Optional API Key for REST endpoints")
        self.mouse_sensitivity = QLineEdit(
            str(self.config.get("mouse_sensitivity", 1.5))
        )
        self.remote_mouse_idle_timeout = QLineEdit(
            str(self.config.get("remote_mouse_idle_timeout", 3.0))
        )
        self.share_response_with_android = QCheckBox(
            "Share LLM response screenshot with Android app"
        )

        # Webhook settings
        self.webhook_url = QLineEdit(self.config.get("webhook_url", ""))
        self.webhook_trigger_on_summary = QCheckBox(
            "Trigger webhook when a session summary is generated"
        )

        # LLM Retry settings
        self.llm_max_retries = QLineEdit(str(self.config.get("llm_max_retries", 3)))
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
        self.track_active_window = QCheckBox("Track Active Window with Screenshots")

        self.embedding_engine_combo = QComboBox()
        self.embedding_engine_combo.addItem("Local (sentence-transformers)", "local")
        self.embedding_engine_combo.addItem("Remote (Gemini)", "remote")

        # Logging settings
        self.log_level_combo = QComboBox()
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            self.log_level_combo.addItem(level, level)
        self.log_file_path = QLineEdit(
            self.config.get("log_file", "logs/snapsolve.log")
        )
        self.log_rotation = QLineEdit(
            self.config.get("log_rotation", "10 MB")
        )
        self.log_retention = QLineEdit(
            self.config.get("log_retention", "7 days")
        )
        # Per-dependency log level combos
        self._dep_log_combos: dict[str, QComboBox] = {}
        dep_defaults = self.config.get("log_levels", {})
        for dep_name in ["urllib3", "PIL", "google", "httpx", "soundcard", "matplotlib"]:
            combo = QComboBox()
            for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                combo.addItem(level, level)
            dep_level = dep_defaults.get(dep_name, "WARNING")
            idx = combo.findData(dep_level.upper())
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self._dep_log_combos[dep_name] = combo

        self.setWindowTitle("Application Configuration")
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets",
            "icon.png",
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        screen = QApplication.primaryScreen()
        max_height = 500
        if screen:
            screen_geometry = screen.availableGeometry()
            max_height = int(screen_geometry.height() * 0.8)
            self.setMaximumHeight(max_height)
            
        self.resize(600, min(650, max_height))

        self.init_ui()

    def refresh_audio_devices(self):
        current_tts = self.tts_output_device_combo.currentData()
        current_input = self.audio_input_device_combo.currentData()
        current_loopback = self.audio_loopback_device_combo.currentData()

        self.tts_output_device_combo.clear()
        self.tts_output_device_combo.addItem("Default System Output", None)
        try:
            from config.settings import get_audio_devices  # noqa: PLC0415

            for device in get_audio_devices():
                self.tts_output_device_combo.addItem(device["name"], device["name"])
        except Exception:
            pass

        self.audio_input_device_combo.clear()
        self.audio_input_device_combo.addItem("Default System Input", None)
        try:
            from config.settings import get_audio_input_devices  # noqa: PLC0415

            for device in get_audio_input_devices():
                self.audio_input_device_combo.addItem(device["name"], device["name"])
        except Exception:
            pass

        self.audio_loopback_device_combo.clear()
        self.audio_loopback_device_combo.addItem("(Use input device instead)", None)
        try:
            from config.settings import get_audio_loopback_devices  # noqa: PLC0415

            for device in get_audio_loopback_devices():
                self.audio_loopback_device_combo.addItem(device["name"], device["name"])
        except Exception:
            pass

        idx = self.tts_output_device_combo.findData(current_tts)
        if idx >= 0:
            self.tts_output_device_combo.setCurrentIndex(idx)

        idx = self.audio_input_device_combo.findData(current_input)
        if idx >= 0:
            self.audio_input_device_combo.setCurrentIndex(idx)

        idx = self.audio_loopback_device_combo.findData(current_loopback)
        if idx >= 0:
            self.audio_loopback_device_combo.setCurrentIndex(idx)

    def save_json(self, path, data):
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save {path}:\n{e}")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # --- Search bar (hidden when advanced options are off) ---
        self._search_container = QWidget()
        search_inner = QHBoxLayout(self._search_container)
        search_inner.setContentsMargins(0, 0, 0, 0)
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("font-size: 16px; padding: 0 4px;")
        self._search_input.setPlaceholderText("Search settings...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.textChanged.connect(self._on_search_text_changed)
        search_inner.addWidget(search_icon)
        search_inner.addWidget(self._search_input)
        main_layout.addWidget(self._search_container)

        self._search_results.setVisible(False)
        self._search_results.setSpacing(0)
        self._search_results.setUniformItemSizes(True)
        self._search_results.setSizePolicy(
            self._search_results.sizePolicy().horizontalPolicy(),
            self._search_results.sizePolicy().verticalPolicy(),
        )
        self._search_results.setStyleSheet(
            "QListWidget { border: 1px solid #555; border-radius: 4px; "
            "background: #2b2b2b; color: #ddd; font-size: 13px; padding: 2px; }"
            "QListWidget::item { padding: 1px 6px; margin: 0px; }"
            "QListWidget::item:hover { background: #3a3a5a; }"
            "QListWidget::item:selected { background: #4a4a7a; }"
        )
        self._search_results.itemClicked.connect(self._on_search_result_clicked)
        main_layout.addWidget(self._search_results)

        layout.addWidget(self.tabs)

        # Create tabs
        self.app_tab = QWidget()
        self.profile_tab = QWidget()
        self.shortcuts_tab = QWidget()

        self._all_tabs = [
            (self.app_tab, "Application Settings", False),
            (self.audio_tab, "Audio & Speech", False),
            (self.realtime_analysis_tab, "Real-time Analysis", False),
            (self.profile_tab, "Profile Settings", False),
            (self.llm_tab, "LLM Settings", False),
            (self.warmup_tab, "Warmup Settings", True),
            (self.shortcuts_tab, "Keyboard Shortcuts", False),
            (self.remote_control_tab, "API & Remote Control", True),
            (self.logging_tab, "Logging", True),
        ]
        for tab_widget, tab_title, _ in self._all_tabs:
            self.tabs.addTab(tab_widget, tab_title)

        self.setup_app_tab()
        self.setup_audio_tab()
        self.setup_realtime_analysis_tab()
        self.setup_profile_tab()
        self.setup_llm_tab()
        self.setup_warmup_tab()
        self.setup_shortcuts_tab()
        self.setup_remote_control_tab()
        self.setup_logging_tab()

        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

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

        bottom_layout = QHBoxLayout()
        self._advanced_toggle_btn = QPushButton("⚙ Show Advanced")
        self._advanced_toggle_btn.setCheckable(True)
        self._advanced_toggle_btn.setChecked(False)
        self._advanced_toggle_btn.toggled.connect(self._set_advanced_visible)
        bottom_layout.addWidget(self._advanced_toggle_btn)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.button_box)
        main_layout.addLayout(bottom_layout)

        # Build search index after all tabs are fully populated
        QTimer.singleShot(0, self._build_search_index)

        # Start with advanced options hidden
        self._set_advanced_visible(False)

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
            self,
            "Select PyCharm Executable",
            "",
            "Executables (*.exe *.cmd *.bat);;All Files (*)",
        )
        if file_path:
            self.ide_pycharm_path.setText(file_path)

    def browse_antigravity_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Antigravity IDE Executable",
            "",
            "Executables (*.exe);;All Files (*)",
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

        self.save_images.setChecked(self.config.get("save_images", True))
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
        layout.addRow(
            "Activity Min Delay (s):", self.periodic_screenshots_activity_min_delay
        )

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

        # Semantic Search
        layout.addRow(QLabel("<b>Semantic Search</b>"))
        current_engine = self.config.get("embedding_engine", "local")
        idx = self.embedding_engine_combo.findData(current_engine)
        if idx >= 0:
            self.embedding_engine_combo.setCurrentIndex(idx)
        layout.addRow("Embedding Engine:", self.embedding_engine_combo)

        self.reindex_btn = QPushButton("Re-index All Sessions")
        self.reindex_btn.clicked.connect(self.reindex_all_sessions)
        layout.addRow("Index:", self.reindex_btn)

        # Mark advanced rows (0-indexed row numbers within this tab's QFormLayout)
        for row_idx in [2, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18]:
            self._advanced_rows.append((layout, row_idx))


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

        # --- Audio Enhancement ---
        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Audio Enhancement</b>"))

        self.enable_audio_enhancement.setChecked(
            self.config.get("enable_audio_enhancement", False)
        )
        self.enable_audio_enhancement.setToolTip(
            "Apply a 3-stage audio processing pipeline in real-time:\n"
            "High-pass filter → Noise Suppression → Loudness Normalization"
        )
        layout.addRow("Enhancement Pipeline:", self.enable_audio_enhancement)

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

        # Audio Loopback Device
        self.audio_loopback_device_combo.addItem("(Use input device instead)", None)

        try:
            from config.settings import get_audio_loopback_devices  # noqa: PLC0415

            loopback_audio_devices = get_audio_loopback_devices()
            for device in loopback_audio_devices:
                self.audio_loopback_device_combo.addItem(device["name"], device["name"])
        except Exception as e:
            print(f"Failed to load audio loopback devices: {e}")

        current_loopback_device_name = self.config.get(
            "audio_loopback_device_name", None
        )
        if current_loopback_device_name is not None:
            idx = self.audio_loopback_device_combo.findData(
                current_loopback_device_name
            )
            if idx >= 0:
                self.audio_loopback_device_combo.setCurrentIndex(idx)

        layout.addRow("System Loopback Device:", self.audio_loopback_device_combo)

        # Transcription language
        current_trans_lang = self.config.get("transcription_language", "en")
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            self.transcription_language.addItem(display_name, code)
        trans_idx = self.transcription_language.findData(current_trans_lang)
        if trans_idx >= 0:
            self.transcription_language.setCurrentIndex(trans_idx)
        layout.addRow("Transcription Language:", self.transcription_language)

        # Transcription Model
        transcription_models = [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large-v1",
            "large-v2",
            "large-v3",
            "large",
        ]
        for m in transcription_models:
            self.transcription_model.addItem(m, m)
        current_trans_model = self.config.get("transcription_model", "small")
        model_idx = self.transcription_model.findData(current_trans_model)
        if model_idx >= 0:
            self.transcription_model.setCurrentIndex(model_idx)
        layout.addRow("Transcription Model:", self.transcription_model)

        self.realtime_transcription.setChecked(
            self.config.get("realtime_transcription", True)
        )
        layout.addRow("Real-time Transcription:", self.realtime_transcription)

        self.show_audio_volume_bar.setChecked(
            self.config.get("show_audio_volume_bar", True)
        )
        layout.addRow("Volume Bar:", self.show_audio_volume_bar)

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

        self.post_recording_diarization.setChecked(
            self.config.get("post_recording_diarization", False)
        )
        layout.addRow("Offline Diarization:", self.post_recording_diarization)

        diarization_models = [
            "tiny",
            "tiny.en",
            "base",
            "base.en",
            "small",
            "small.en",
            "medium",
            "medium.en",
            "large-v1",
            "large-v2",
            "large-v3",
            "large",
        ]
        for m in diarization_models:
            self.diarization_model.addItem(m, m)
        current_diarize_model = self.config.get("diarization_model", "base")
        d_model_idx = self.diarization_model.findData(current_diarize_model)
        if d_model_idx >= 0:
            self.diarization_model.setCurrentIndex(d_model_idx)
        layout.addRow("Diarization Model:", self.diarization_model)

        self.delete_wav_after_diarization.setChecked(
            self.config.get("delete_wav_after_diarization", True)
        )
        layout.addRow("Auto-Delete Audio:", self.delete_wav_after_diarization)

        self.summarize_transcription_prompt.setPlaceholderText(
            "e.g. Summarize the following transcribed conversation:"
        )
        layout.addRow("Summary Prompt:", self.summarize_transcription_prompt)

        self.speaker_name.setPlaceholderText("e.g. interviewer")
        self.speaker_name.setToolTip(
            "Name attributed to the speaker in transcription files.\n"
            "Each transcription segment will be prefixed with [name]."
        )
        layout.addRow("Speaker Name:", self.speaker_name)

        # Mark advanced rows (0-indexed row numbers within this tab's QFormLayout)
        for row_idx in [0, 1, 2, 3, 4, 5, 12, 14, 20, 22, 23, 24, 25, 26]:
            self._advanced_rows.append((layout, row_idx))

    def setup_realtime_analysis_tab(self):
        """Build the Real-time Analysis tab.

        Contains toggles for real-time correction types and window size.
        """
        layout = QFormLayout(self.realtime_analysis_tab)

        layout.addRow(QLabel("<b>Real-time Speech Correction</b>"))

        self.realtime_correction_enabled.setChecked(
            self.config.get("realtime_correction_enabled", False)
        )
        self.realtime_correction_enabled.setToolTip(
            "When enabled, transcribed speech is analyzed in real-time\n"
            "by an LLM during recording. Corrections appear in a side panel."
        )
        layout.addRow("Enable:", self.realtime_correction_enabled)

        # Sub-toggles (indented)
        layout.addRow(QLabel("<b>Correction Types</b>"))

        self.realtime_correction_fact_check.setChecked(
            self.config.get("realtime_correction_fact_check", True)
        )
        self.realtime_correction_fact_check.setToolTip(
            "Identify and correct factual errors, wrong statistics,\n"
            "incorrect dates, and misleading claims."
        )
        layout.addRow("    Fact-Checking:", self.realtime_correction_fact_check)

        self.realtime_correction_grammar.setChecked(
            self.config.get("realtime_correction_grammar", True)
        )
        self.realtime_correction_grammar.setToolTip(
            "Flag grammatical errors, malapropisms, incorrect word\n"
            "usage, and likely transcription errors (homophones)."
        )
        layout.addRow("    Grammar:", self.realtime_correction_grammar)

        self.realtime_correction_content_suggestions.setChecked(
            self.config.get("realtime_correction_content_suggestions", False)
        )
        self.realtime_correction_content_suggestions.setToolTip(
            "Suggest stronger phrasing, more precise terminology,\n"
            "and supporting data to strengthen your speech."
        )
        layout.addRow("    Suggestions:", self.realtime_correction_content_suggestions)

        # Disable sub-toggles when master is off
        def _on_master_toggled(checked):
            self.realtime_correction_fact_check.setEnabled(checked)
            self.realtime_correction_grammar.setEnabled(checked)
            self.realtime_correction_content_suggestions.setEnabled(checked)
            self.realtime_correction_window_size.setEnabled(checked)

        self.realtime_correction_enabled.toggled.connect(_on_master_toggled)
        _on_master_toggled(self.realtime_correction_enabled.isChecked())

        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Advanced</b>"))

        self.realtime_correction_window_size.setPlaceholderText("e.g. 4")
        self.realtime_correction_window_size.setToolTip(
            "Number of finalized sentences to accumulate before\n"
            "sending them to the LLM for analysis.\n"
            "Lower = faster feedback but less context.\n"
            "Higher = more context but slower feedback."
        )
        layout.addRow("Window Size (sentences):", self.realtime_correction_window_size)

        hint = QLabel(
            "Real-time correction analyzes your speech during recording\n"
            "and displays fact-checks, grammar fixes, and suggestions\n"
            "in a side panel. Use a fast model (e.g. Flash Lite) for\n"
            "low latency. The correction model is set per-profile\n"
            "in the Profile Settings tab.\n\n"
            "Correction prompts can be customized by editing the\n"
            "correction_* entries in config/prompts.json."
        )
        hint.setWordWrap(True)
        layout.addRow(hint)

        # Mark advanced rows (0-indexed row numbers within this tab's QFormLayout)
        for row_idx in [6, 7, 8, 9]:
            self._advanced_rows.append((layout, row_idx))

    def setup_llm_tab(self):
        """Build the LLM Settings tab.

        Contains API keys/URLs for LLM providers and retry configuration.
        """
        layout = QFormLayout(self.llm_tab)

        # API Keys & URLs
        layout.addRow("Ollama URL:", self.ollama_url)

        self.gemini_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Gemini API Key:", self.gemini_api_key)

        self.openai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("OpenAI API Key:", self.openai_api_key)

        self.anthropic_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Anthropic API Key:", self.anthropic_api_key)

        self.groq_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("Groq API Key:", self.groq_api_key)

        self.openrouter_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow("OpenRouter API Key:", self.openrouter_api_key)

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

        # Mark advanced rows (0-indexed row numbers within this tab's QFormLayout)
        for row_idx in [6, 7, 8]:
            self._advanced_rows.append((layout, row_idx))

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

        self.prof_llm_engine.addItems(
            ["gemini", "ollama", "google-genai", "antigravity", "litellm"]
        )
        self.prof_llm_engine.currentTextChanged.connect(self.update_model_dropdowns)
        form_layout.addRow("LLM Engine:", self.prof_llm_engine)

        form_layout.addRow("Main Model:", self.prof_model)

        form_layout.addRow("Fallback Model:", self.prof_fallback_model)

        self.prof_ocr_engine.addItems(["none", "paddleocr", "remote_paddle"])
        form_layout.addRow("OCR Engine:", self.prof_ocr_engine)

        self.populate_prompts()
        form_layout.addRow("Prompt:", self.prof_prompt)

        form_layout.addRow("Correction Model:", self.prof_correction_model)

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

        # Populate correction model dropdown
        self.prof_correction_model.clear()
        self.prof_correction_model.addItem("None (use main model)", "None")
        for m in models:
            self.prof_correction_model.addItem(m["name"], m["id"])

        # Try to restore previous selection if valid
        if hasattr(self, "_current_profile_data"):
            model_id = self._current_profile_data.get("model")
            fallback_id = self._current_profile_data.get("fallback_model")

            idx = self.prof_model.findData(model_id)
            if idx >= 0:
                self.prof_model.setCurrentIndex(idx)
            elif model_id:
                self.prof_model.setCurrentText(model_id)

            idx2 = self.prof_fallback_model.findData(fallback_id)
            if idx2 >= 0:
                self.prof_fallback_model.setCurrentIndex(idx2)
            elif fallback_id:
                self.prof_fallback_model.setCurrentText(fallback_id)

            correction_id = self._current_profile_data.get("correction_model")
            idx3 = self.prof_correction_model.findData(correction_id)
            if idx3 >= 0:
                self.prof_correction_model.setCurrentIndex(idx3)

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

        self.prof_enable_chat_sessions.setChecked(
            profile.get("enable_chat_sessions", True)
        )

    def save_current_profile(self):
        index = self.profile_combo.currentIndex()
        if index < 0 or index >= len(self.profiles):
            return

        profile = self.profiles[index]
        profile["name"] = self.prof_name.text()
        profile["llm_engine"] = self.prof_llm_engine.currentText()
        profile["model"] = self.prof_model.currentData() or self.prof_model.currentText()
        profile["fallback_model"] = self.prof_fallback_model.currentData() or self.prof_fallback_model.currentText()
        profile["ocr_engine"] = self.prof_ocr_engine.currentText()
        profile["prompt_id"] = self.prof_prompt.currentData()
        profile["correction_model"] = self.prof_correction_model.currentData()
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
        """Build the API & Remote Control settings tab.

        Allows the user to enable the local FastAPI server, set the
        network interface it binds to, and choose the TCP port.
        Restart required for changes to take effect.
        """
        layout = QFormLayout(self.remote_control_tab)

        self.enable_api_server.setChecked(self.config.get("enable_api_server", False))
        layout.addRow("Enable Server:", self.enable_api_server)

        self.api_server_host.setPlaceholderText("e.g. 0.0.0.0 (all interfaces)")
        layout.addRow("Host / Interface:", self.api_server_host)

        self.api_server_port.setPlaceholderText("e.g. 3031")
        layout.addRow("Port:", self.api_server_port)

        layout.addRow("API Key:", self.api_server_key)

        self.mouse_sensitivity.setPlaceholderText("e.g. 1.5")
        layout.addRow("Mouse Sensitivity:", self.mouse_sensitivity)

        self.remote_mouse_idle_timeout.setPlaceholderText("e.g. 3.0")
        layout.addRow("Mouse Idle Timeout (s):", self.remote_mouse_idle_timeout)

        self.share_response_with_android.setChecked(
            self.config.get("share_response_with_android", False)
        )
        layout.addRow("Response Screenshot:", self.share_response_with_android)

        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Webhooks / Integrations</b>"))
        self.webhook_url.setPlaceholderText("e.g. https://hooks.slack.com/services/...")
        layout.addRow("Webhook URL:", self.webhook_url)
        self.webhook_trigger_on_summary.setChecked(
            self.config.get("webhook_trigger_on_summary", False)
        )
        layout.addRow("Auto-Trigger:", self.webhook_trigger_on_summary)

        hint = QLabel(
            "When enabled, SnapSolve runs a local API server on the specified port.\n"
            "This provides both REST endpoints (like Screenpipe) and WebSocket access\n"
            "for the Android remote control app.\n"
            "Make sure your firewall allows inbound TCP traffic on that port.\n"
            "If an API key is set, it must be provided in the 'Authorization' or 'x-api-key' header.\n"
            "When 'Response Screenshot' is enabled, an image is sent to the Android app.\n"
            "Webhooks allow sending session summaries to external services (Slack, Zapier, n8n).\n"
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

    # ------------------------------------------------------------------
    # Logging tab
    # ------------------------------------------------------------------

    def setup_logging_tab(self):
        """Build the Logging tab."""
        layout = QFormLayout(self.logging_tab)

        layout.addRow(QLabel("<b>Application Logging</b>"))

        current_log_level = self.config.get("log_level", "INFO").upper()
        idx = self.log_level_combo.findData(current_log_level)
        if idx >= 0:
            self.log_level_combo.setCurrentIndex(idx)
        self.log_level_combo.setToolTip(
            "Controls the minimum log level shown in the console.\n"
            "The log file always captures DEBUG level."
        )
        layout.addRow("Console Log Level:", self.log_level_combo)

        self.log_file_path.setPlaceholderText("e.g. logs/snapsolve.log")
        self.log_file_path.setToolTip(
            "Path to the log file. Leave empty to disable file logging.\n"
            "Relative paths are relative to the application directory."
        )
        layout.addRow("Log File:", self.log_file_path)

        self.log_rotation.setPlaceholderText("e.g. 10 MB")
        self.log_rotation.setToolTip(
            "Log file rotation policy.\n"
            "Examples: '10 MB', '1 day', '100 MB'"
        )
        layout.addRow("Log Rotation:", self.log_rotation)

        self.log_retention.setPlaceholderText("e.g. 7 days")
        self.log_retention.setToolTip(
            "How long to keep old log files before deletion.\n"
            "Examples: '7 days', '30 days', '1 month'"
        )
        layout.addRow("Log Retention:", self.log_retention)

        # Dependency log levels
        layout.addRow(QLabel(""))  # spacer
        layout.addRow(QLabel("<b>Dependency Log Levels</b>"))

        dep_labels = {
            "urllib3": "urllib3 (HTTP):",
            "PIL": "Pillow (Images):",
            "google": "Google SDK:",
            "httpx": "httpx (HTTP):",
            "soundcard": "SoundCard:",
            "matplotlib": "Matplotlib:",
        }
        for dep_name, combo in self._dep_log_combos.items():
            label = dep_labels.get(dep_name, f"{dep_name}:")
            combo.setToolTip(
                f"Log level for the '{dep_name}' library.\n"
                "Set to WARNING or higher to silence noisy output."
            )
            layout.addRow(label, combo)

    # ------------------------------------------------------------------
    # Search functionality
    # ------------------------------------------------------------------

    def _build_search_index(self):
        """Walk every tab recursively to find all QFormLayout label→widget pairs."""
        self._search_index.clear()
        for tab_index in range(self.tabs.count()):
            tab_widget = self.tabs.widget(tab_index)
            tab_name = self.tabs.tabText(tab_index)
            self._index_widget_tree(tab_widget, tab_index, tab_name)

    def _index_widget_tree(self, widget, tab_index: int, tab_name: str):
        """Recursively search *widget* and all its children for QFormLayouts."""
        if widget is None:
            return
        layout = widget.layout() if hasattr(widget, "layout") else None
        if isinstance(layout, QFormLayout):
            self._index_form_layout(layout, tab_index, tab_name)
        # Recurse into children (catches profile_form, scroll-area containers, etc.)
        for child in widget.findChildren(QWidget):
            child_layout = child.layout() if hasattr(child, "layout") else None
            if isinstance(child_layout, QFormLayout) and child_layout is not layout:
                self._index_form_layout(child_layout, tab_index, tab_name)

    def _index_form_layout(self, layout: QFormLayout, tab_index: int, tab_name: str):
        """Extract label→widget pairs from a single QFormLayout."""
        import re

        for row in range(layout.rowCount()):
            label_item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field_item = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if label_item is None or field_item is None:
                continue
            label_widget = label_item.widget()
            field_widget = field_item.widget()
            if label_widget is None or field_widget is None:
                continue
            label_text = label_widget.text().strip()
            # Extract text from HTML bold labels like <b>Section</b>
            if label_text.startswith("<b>"):
                match = re.search(r"<b>(.*?)</b>", label_text)
                label_text = match.group(1) if match else ""
            if not label_text:
                continue
            # Strip trailing colons for cleaner display
            display_label = label_text.rstrip(":")
            # Include tooltip for richer matching
            tooltip = field_widget.toolTip() if hasattr(field_widget, "toolTip") else ""
            self._search_index.append(
                {
                    "label": display_label,
                    "tab_index": tab_index,
                    "tab_name": tab_name,
                    "widget": field_widget,
                    "tooltip": tooltip,
                }
            )

    def _on_search_text_changed(self, text: str):
        """Filter search index and populate results list."""
        self._stop_blink()
        self._search_results.clear()

        if not text.strip():
            self._search_results.setVisible(False)
            return

        query = text.strip().lower()
        matches = []
        for entry in self._search_index:
            label_lower = entry["label"].lower()
            tooltip_lower = entry["tooltip"].lower()
            if query in label_lower or query in tooltip_lower:
                matches.append(entry)

        if not matches:
            self._search_results.setVisible(False)
            return

        for entry in matches[:15]:  # Cap at 15 results
            display = f"{entry['label']}   [{entry['tab_name']}]"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self._search_results.addItem(item)

        # Dynamically size the list to fit its content (no empty space)
        row_height = self._search_results.sizeHintForRow(0)
        if row_height < 1:
            row_height = 22  # Reasonable fallback
        count = self._search_results.count()
        # +6 accounts for border + padding on the container
        desired = row_height * count + 6
        self._search_results.setFixedHeight(min(desired, 250))
        self._search_results.setVisible(True)

    def _on_search_result_clicked(self, item: QListWidgetItem):
        """Switch to the tab and blink-highlight the target widget."""
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return

        # Switch to the correct tab
        self.tabs.setCurrentIndex(entry["tab_index"])

        # Scroll the widget into view
        target: QWidget = entry["widget"]
        target.setFocus()

        # Walk up to find any parent QScrollArea and scroll to the widget
        parent = target.parent()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(target)
                break
            parent = parent.parent() if hasattr(parent, "parent") else None

        # Start blink animation
        self._start_blink(target)

        # Hide results and clear search (block signals to avoid _stop_blink)
        self._search_results.setVisible(False)
        self._search_input.blockSignals(True)
        self._search_input.clear()
        self._search_input.blockSignals(False)

    def _start_blink(self, widget: QWidget):
        """Start a blink animation on the target widget (4 on/off cycles)."""
        from PyQt6.QtWidgets import QGraphicsColorizeEffect
        from PyQt6.QtGui import QColor

        self._stop_blink()  # Clean up any previous blink
        self._highlighted_widget = widget
        self._blink_count = 0
        self._blink_on = False

        # Create a colorize effect (golden tint)
        effect = QGraphicsColorizeEffect(widget)
        effect.setColor(QColor(255, 215, 0))  # Gold
        effect.setStrength(0.0)  # Start invisible
        widget.setGraphicsEffect(effect)

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(250)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_timer.start()

    def _blink_tick(self):
        """Toggle highlight effect for one blink cycle."""
        if self._highlighted_widget is None:
            self._stop_blink()
            return

        self._blink_on = not self._blink_on
        try:
            effect = self._highlighted_widget.graphicsEffect()
            if effect is not None:
                effect.setStrength(0.6 if self._blink_on else 0.0)
                if self._blink_on:
                    self._blink_count += 1
        except RuntimeError:
            self._stop_blink()
            return

        if self._blink_count >= 4:
            self._stop_blink()

    def _stop_blink(self):
        """Stop blinking and remove the graphics effect."""
        if hasattr(self, "_blink_timer") and self._blink_timer is not None:
            self._blink_timer.stop()
            self._blink_timer.deleteLater()
            self._blink_timer = None
        if self._highlighted_widget is not None:
            try:
                self._highlighted_widget.setGraphicsEffect(None)
            except RuntimeError:
                pass
            self._highlighted_widget = None

    # ------------------------------------------------------------------
    # Advanced options toggle
    # ------------------------------------------------------------------

    def _set_advanced_visible(self, visible: bool):
        """Toggle visibility of all advanced options, tabs, and search."""
        self._advanced_mode = visible

        # Toggle advanced rows within tabs
        for layout, row in self._advanced_rows:
            self._set_row_visible(layout, row, visible)

        # Toggle advanced tabs (rebuild tab bar preserving order)
        current_widget = self.tabs.currentWidget()
        while self.tabs.count():
            self.tabs.removeTab(0)
        for tab_widget, tab_title, is_advanced in self._all_tabs:
            if not is_advanced or visible:
                self.tabs.addTab(tab_widget, tab_title)
        idx = self.tabs.indexOf(current_widget)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

        # Toggle search bar and results
        if self._search_container is not None:
            self._search_container.setVisible(visible)
        self._search_results.setVisible(False)
        if not visible:
            self._search_input.blockSignals(True)
            self._search_input.clear()
            self._search_input.blockSignals(False)

        # Update button text
        if self._advanced_toggle_btn is not None:
            self._advanced_toggle_btn.setText(
                "⚙ Hide Advanced" if visible else "⚙ Show Advanced"
            )

    def _set_row_visible(self, layout: QFormLayout, row: int, visible: bool):
        """Show or hide a single row in a QFormLayout."""
        for role in (
            QFormLayout.ItemRole.LabelRole,
            QFormLayout.ItemRole.FieldRole,
            QFormLayout.ItemRole.SpanningRole,
        ):
            item = layout.itemAt(row, role)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(visible)
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    self._set_layout_visible(child_layout, visible)

    def _set_layout_visible(self, layout, visible: bool):
        """Recursively show/hide all widgets in a layout."""
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setVisible(visible)
                child_layout = item.layout()
                if child_layout is not None:
                    self._set_layout_visible(child_layout, visible)

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
        self.config["show_audio_volume_bar"] = self.show_audio_volume_bar.isChecked()
        self.config["transcription_language"] = (
            self.transcription_language.currentData() or "en"
        )
        self.config["transcription_model"] = (
            self.transcription_model.currentData() or "small"
        )
        self.config["tts_language"] = self.tts_language.currentData() or "en"
        self.config["translation_language"] = (
            self.translation_language.currentData() or ""
        )
        self.config["save_transcriptions"] = self.save_transcriptions.isChecked()
        self.config["auto_summarize_transcription"] = (
            self.auto_summarize_transcription.isChecked()
        )
        self.config["post_recording_diarization"] = (
            self.post_recording_diarization.isChecked()
        )
        self.config["diarization_model"] = (
            self.diarization_model.currentData() or "base"
        )
        self.config["delete_wav_after_diarization"] = (
            self.delete_wav_after_diarization.isChecked()
        )
        self.config["enable_audio_enhancement"] = (
            self.enable_audio_enhancement.isChecked()
        )
        self.config["summarize_transcription_prompt"] = (
            self.summarize_transcription_prompt.text()
        )
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
        self.config["openai_api_key"] = self.openai_api_key.text()
        self.config["anthropic_api_key"] = self.anthropic_api_key.text()
        self.config["groq_api_key"] = self.groq_api_key.text()
        self.config["openrouter_api_key"] = self.openrouter_api_key.text()
        self.config["ide_pycharm_path"] = (
            self.ide_pycharm_path.text().strip() or "pycharm"
        )

        default_antigravity = str(
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Programs"
            / "Antigravity IDE"
            / "Antigravity IDE.exe"
        )
        self.config["ide_antigravity_path"] = (
            self.ide_antigravity_path.text().strip() or default_antigravity
        )
        self.config["antigravity_service_url"] = (
            self.antigravity_service_url.text().strip() or "http://localhost:8200"
        )

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
        self.config["audio_loopback_device_name"] = (
            self.audio_loopback_device_combo.currentData()
        )

        # API & Remote Control settings
        self.config["enable_api_server"] = self.enable_api_server.isChecked()
        self.config["api_server_host"] = (
            self.api_server_host.text().strip() or "0.0.0.0"
        )
        self.config["api_server_port"] = int(
            self.api_server_port.text().strip() or "3031"
        )
        self.config["api_server_key"] = self.api_server_key.text()
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
        self.config["webhook_url"] = self.webhook_url.text().strip()
        self.config["webhook_trigger_on_summary"] = (
            self.webhook_trigger_on_summary.isChecked()
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
        self.config["embedding_engine"] = self.embedding_engine_combo.currentData()

        # Logging
        self.config["log_level"] = self.log_level_combo.currentData() or "INFO"
        self.config["log_file"] = self.log_file_path.text().strip()
        self.config["log_rotation"] = self.log_rotation.text().strip() or "10 MB"
        self.config["log_retention"] = self.log_retention.text().strip() or "7 days"
        log_levels = {}
        for dep_name, combo in self._dep_log_combos.items():
            log_levels[dep_name] = combo.currentData() or "WARNING"
        self.config["log_levels"] = log_levels

        # Real-time Correction
        self.config["realtime_correction_enabled"] = (
            self.realtime_correction_enabled.isChecked()
        )
        self.config["realtime_correction_fact_check"] = (
            self.realtime_correction_fact_check.isChecked()
        )
        self.config["realtime_correction_grammar"] = (
            self.realtime_correction_grammar.isChecked()
        )
        self.config["realtime_correction_content_suggestions"] = (
            self.realtime_correction_content_suggestions.isChecked()
        )
        try:
            self.config["realtime_correction_window_size"] = int(
                self.realtime_correction_window_size.text().strip() or "4"
            )
        except ValueError:
            self.config["realtime_correction_window_size"] = 4

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

    def reindex_all_sessions(self):
        reply = QMessageBox.question(
            self,
            "Re-index All Sessions",
            "This will re-embed all sessions. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Temporarily save engine choice
            self.config["embedding_engine"] = self.embedding_engine_combo.currentData()
            self.config["gemini_api_key"] = self.gemini_api_key.text()

            from core.session_manager import SessionManager
            from PyQt6.QtWidgets import QProgressDialog
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QApplication

            manager = SessionManager(self.config)
            sessions = manager.list_all_sessions()
            total = len(sessions)

            progress = QProgressDialog(
                "Re-indexing sessions...", "Cancel", 0, total, self
            )
            progress.setWindowTitle("Indexing")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            for i, s in enumerate(sessions):
                if progress.wasCanceled():
                    break
                progress.setValue(i)
                progress.setLabelText(f"Indexing session {i + 1} of {total}...")
                QApplication.processEvents()
                manager.index_session_sync(s["id"])

            progress.setValue(total)
            QMessageBox.information(
                self, "Indexing Complete", "Re-indexing has finished."
            )


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
