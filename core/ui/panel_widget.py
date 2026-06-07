"""PanelWidget — floating control panel with action buttons."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QCheckBox,
    QComboBox,
    QLabel,
    QProgressBar,
)

from core.ui.mixins import DraggableWidgetMixin, _DragHandleBar
from core.ui.record_button import RecordButton
from core.ui.signals import call_action, ui_signals


class PanelWidget(DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 230); border: 1px solid #444; border-radius: 8px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.is_multi_selecting = False

        # Drag Handle Bar (replaces the old close-button-only top bar)
        self.drag_handle = _DragHandleBar(self)
        self.layout.addWidget(self.drag_handle)

        # Buttons
        self.buttons = {}
        btn_style = (
            "QPushButton { background-color: rgba(45, 45, 45, 180); color: white;"
            " border: none; padding: 8px; border-radius: 4px; font-size: 14px;}"
            " QPushButton:hover { background-color: rgba(62, 62, 62, 220); }"
            " QPushButton:disabled { color: #777; }"
        )
        cancel_btn_style = (
            "QPushButton { background-color: rgba(178, 34, 34, 0.7); color: white;"
            " border: none; padding: 8px; border-radius: 4px; font-size: 14px;}"
            " QPushButton:hover { background-color: rgba(220, 20, 60, 0.8); }"
        )

        def create_btn(name, text, action, style=btn_style):
            btn = QPushButton(text)
            btn.setStyleSheet(style)
            btn.clicked.connect(lambda: call_action(action))
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            return btn

        self.btn_record = RecordButton("🎙️ Record", btn_style)
        self.btn_record.start_recording.connect(
            lambda enable_transcription: call_action(
                "start_record", enable_transcription
            )
        )
        self.btn_record.stop_recording.connect(
            lambda is_long_press: call_action("stop_record", is_long_press)
        )
        self.layout.addWidget(self.btn_record)
        self.buttons["record"] = self.btn_record

        self.btn_capture = create_btn("capture", "📸 Capture", "capture")
        self.btn_reselect = create_btn("reselect", "🎯 Reselect", "reselect")
        self.btn_multi = create_btn("multi", "➕ Multi-select", "multi_capture")

        # Autosubmit checkbox — when unchecked, OCR text goes to text box for review
        chk_style = (
            "QCheckBox { background-color: transparent; color: white;"
            " padding: 4px; font-size: 13px; }"
            " QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        self.chk_autosubmit = QCheckBox("Autosubmit")
        self.chk_autosubmit.setStyleSheet(chk_style)
        self.chk_autosubmit.setChecked(True)
        self.layout.addWidget(self.chk_autosubmit)

        self.btn_end_multi = create_btn(
            "end_multi", "✅ End Multi", "end_multi_capture"
        )
        self.btn_chat_sessions = create_btn(
            "chat_sessions", "💬 Chat Sessions: ON", "toggle_chat_sessions"
        )
        self.chat_sessions_enabled = True
        self.btn_cycle = create_btn("cycle", "🔄 Cycle Source", "cycle_source")

        self.btn_sessions = QPushButton("📋 Sessions")
        self.btn_sessions.setStyleSheet(btn_style)
        self.btn_sessions.clicked.connect(lambda: ui_signals.open_session_browser.emit())
        self.layout.addWidget(self.btn_sessions)
        self.buttons["sessions"] = self.btn_sessions

        self.btn_context = QPushButton("🧠 Context")
        self.btn_context.setStyleSheet(btn_style)
        self.btn_context.clicked.connect(lambda: ui_signals.open_context_manager.emit())
        self.layout.addWidget(self.btn_context)
        self.buttons["context"] = self.btn_context

        self.btn_periodic_screenshots = create_btn(
            "periodic_screenshots", "📷 Screenshots: OFF", "toggle_periodic_screenshots"
        )
        self.periodic_screenshots_enabled = False

        self.btn_cancel = create_btn(
            "cancel", "❌ Cancel", "cancel", style=cancel_btn_style
        )

        # Transcription language selector (visible only in audio mode)
        from ui.config_ui import TRANSCRIPTION_LANGUAGES  # noqa: PLC0415
        lang_combo_style = (
            "QComboBox { background-color: rgba(45, 45, 45, 180); color: white;"
            " border: none; padding: 4px; border-radius: 4px; font-size: 12px;}"
            " QComboBox::drop-down { border: none; }"
            " QComboBox QAbstractItemView { background-color: #2d2d2d; color: white;"
            " selection-background-color: #3e3e3e; }"
        )
        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(lang_combo_style)
        for display_name, code in TRANSCRIPTION_LANGUAGES:
            self.lang_combo.addItem(display_name, code)
        # Default to English
        en_idx = self.lang_combo.findData("en")
        if en_idx >= 0:
            self.lang_combo.setCurrentIndex(en_idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.layout.addWidget(self.lang_combo)
        self.lang_combo.hide()

        # Translation status label (visible only in audio mode)
        self.translation_label = QLabel("")
        self.translation_label.setStyleSheet(
            "QLabel { background-color: rgba(45, 45, 45, 180); color: #aaa;"
            " border: none; padding: 4px; border-radius: 4px; font-size: 11px;}"
        )
        self.translation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.translation_label)
        self.translation_label.hide()

        # Volume Progress Bar
        self.volume_bar = QProgressBar()
        self.volume_bar.setTextVisible(False)
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        self.volume_bar.setStyleSheet(
            """
            QProgressBar {
                min-height: 6px;
                max-height: 6px;
                border-radius: 3px;
                background-color: rgba(45, 45, 45, 180);
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
            """
        )
        self.layout.addWidget(self.volume_bar)
        self.volume_bar.hide()
        self.show_audio_volume_bar_setting = True
        ui_signals.update_volume.connect(self.volume_bar.setValue)

        self.btn_end_multi.hide()
        self.btn_cancel.hide()

        self.resize(200, 340)

    def _broadcast_state(self):
        from core.remote_control_server import set_ui_state

        state = {}
        panel_visible = self.isVisible()
        for name, btn in self.buttons.items():
            state[name] = {
                "visible": bool(btn.isVisible() and panel_visible),
                "enabled": bool(btn.isEnabled()),
            }
        set_ui_state(state)

    # noinspection PyPep8Naming
    def showEvent(self, event):
        super().showEvent(event)
        self._broadcast_state()

    # noinspection PyPep8Naming
    def hideEvent(self, event):
        super().hideEvent(event)
        self._broadcast_state()

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        x = 20
        y = screen.height() - self.height() - 50
        self.move(x, y)

    def set_multi_state(self, in_progress):
        self.is_multi_selecting = in_progress
        self.btn_end_multi.setVisible(in_progress)
        self.btn_cancel.setVisible(in_progress)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def set_source(self, source_name):
        is_image = source_name == "image"
        is_audio = source_name == "audio"
        self.btn_capture.setVisible(is_image)
        self.btn_reselect.setVisible(is_image)
        self.btn_multi.setVisible(is_image)
        self.chk_autosubmit.setVisible(is_image)
        self.btn_record.setVisible(is_audio)
        self.lang_combo.setVisible(is_audio)
        self.translation_label.setVisible(is_audio)
        self.volume_bar.setVisible(is_audio and self.show_audio_volume_bar_setting)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def _on_language_changed(self, _index: int):
        """Emit signal when the user changes the transcription language."""
        lang_code = self.lang_combo.currentData() or ""
        ui_signals.set_transcription_language.emit(lang_code)

    def set_transcription_language_value(self, lang_code: str):
        """Set the combo to a specific language code without triggering the signal."""
        idx = self.lang_combo.findData(lang_code)
        if idx >= 0:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

    def set_audio_volume_bar_setting(self, show: bool):
        self.show_audio_volume_bar_setting = show
        if self.btn_record.isVisible():
            self.volume_bar.setVisible(show)
            self.adjustSize()
            self.update_position()
            self._broadcast_state()

    def update_translation_label(self, lang_code: str):
        """Update the translation status label to reflect the current setting."""
        if lang_code:
            from ui.config_ui import TRANSCRIPTION_LANGUAGES  # noqa: PLC0415
            # Look up the display name
            display = lang_code
            for display_name, code in TRANSCRIPTION_LANGUAGES:
                if code == lang_code:
                    display = display_name
                    break
            self.translation_label.setText(f"🌐 Translating → {display}")
            self.translation_label.setStyleSheet(
                "QLabel { background-color: rgba(45, 45, 45, 180); color: #7fdbca;"
                " border: none; padding: 4px; border-radius: 4px; font-size: 11px;}"
            )
        else:
            self.translation_label.setText("")
            self.translation_label.setStyleSheet(
                "QLabel { background-color: rgba(45, 45, 45, 180); color: #aaa;"
                " border: none; padding: 4px; border-radius: 4px; font-size: 11px;}"
            )

    def set_processing_state(self, is_processing):
        if not self.is_multi_selecting:
            self.btn_cancel.setVisible(is_processing)
        for name, btn in self.buttons.items():
            if name != "cancel":
                btn.setEnabled(not is_processing)
        self.adjustSize()
        self.update_position()
        self._broadcast_state()

    def _apply_opacity(self, opacity: float):
        """Apply opacity via RGBA backgrounds to the panel, drag handle, and all buttons."""
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(30, 30, 30, {alpha_int});"
            f" border: 1px solid #444; border-radius: 8px;"
        )
        self.drag_handle._apply_opacity(opacity)

        # Apply uniform alpha to all buttons
        btn_style = (
            f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: white;"
            f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
            f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
            f" QPushButton:disabled {{ color: #777; }}"
        )
        cancel_style = (
            f"QPushButton {{ background-color: rgba(178, 34, 34, {alpha_int}); color: white;"
            f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
            f" QPushButton:hover {{ background-color: rgba(220, 20, 60, {alpha_int}); }}"
        )
        chk_style = (
            f"QCheckBox {{ background-color: transparent; color: white;"
            f" padding: 4px; font-size: 13px; }}"
            f" QCheckBox::indicator {{ width: 16px; height: 16px; }}"
        )
        self.chk_autosubmit.setStyleSheet(chk_style)
        for name, btn in self.buttons.items():
            if name == "cancel":
                btn.setStyleSheet(cancel_style)
            elif name == "chat_sessions":
                if getattr(self, "chat_sessions_enabled", True):
                    btn.setStyleSheet(
                        f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: #7fdbca;"
                        f" border: 1px solid #7fdbca; padding: 8px; border-radius: 4px; font-size: 14px;}}"
                        f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
                        f" QPushButton:disabled {{ color: #777; }}"
                    )
                else:
                    btn.setStyleSheet(
                        f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: gray;"
                        f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
                        f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
                        f" QPushButton:disabled {{ color: #777; }}"
                    )
            elif name == "periodic_screenshots":
                if getattr(self, "periodic_screenshots_enabled", False):
                    btn.setStyleSheet(
                        f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: #7fdbca;"
                        f" border: 1px solid #7fdbca; padding: 8px; border-radius: 4px; font-size: 14px;}}"
                        f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
                        f" QPushButton:disabled {{ color: #777; }}"
                    )
                else:
                    btn.setStyleSheet(
                        f"QPushButton {{ background-color: rgba(45, 45, 45, {alpha_int}); color: gray;"
                        f" border: none; padding: 8px; border-radius: 4px; font-size: 14px;}}"
                        f" QPushButton:hover {{ background-color: rgba(62, 62, 62, {alpha_int}); }}"
                        f" QPushButton:disabled {{ color: #777; }}"
                    )
            else:
                btn.setStyleSheet(btn_style)

        self.volume_bar.setStyleSheet(
            f"""
            QProgressBar {{
                min-height: 6px;
                max-height: 6px;
                border-radius: 3px;
                background-color: rgba(45, 45, 45, {alpha_int});
            }}
            QProgressBar::chunk {{
                background-color: rgba(76, 175, 80, {alpha_int});
                border-radius: 3px;
            }}
            """
        )
