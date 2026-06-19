"""UIManager — central orchestrator that creates, wires, and manages all overlay widgets."""
import logging

from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtWidgets import QApplication

from core.capture_hiding import apply_display_affinity
from core.ui.panel_widget import PanelWidget
from core.ui.popup_widget import PopupWidget
from core.ui.signals import ui_signals, selector_signals, _app_callbacks
from core.ui.subtitle_widget import SubtitleWidget
from core.ui.text_input_widget import TextInputWidget
from core.ui.url_input_widget import UrlInputWidget
from core.ui.correction_panel_widget import CorrectionPanelWidget


def _on_request_active_source(q):
    from core.sources import get_active_source_instance

    q.put(get_active_source_instance())


def _handle_request_coords(q):
    from ui.selector import get_coordinates

    # Pass the queue's put method directly as the callback
    get_coordinates(callback=q.put)


class UIManager(QObject):
    def __init__(self):
        super().__init__()
        self._hide_from_capture = False
        self._global_opacity = 0.8
        self._saved_visibility: dict[str, bool] | None = None
        self.popup: PopupWidget | None = None
        self.panel: PanelWidget | None = None
        self.text_input: TextInputWidget | None = None
        self.subtitle: SubtitleWidget | None = None
        self.url_input: UrlInputWidget | None = None
        self.correction_panel: CorrectionPanelWidget | None = None
        self._init_ui()
        selector_signals.request_coords.connect(_handle_request_coords)

    def _init_ui(self):
        if not QApplication.instance():
            return  # Should not happen, main.py creates it
        self.popup = PopupWidget()
        self.panel = PanelWidget()
        self.text_input = TextInputWidget()
        self.subtitle = SubtitleWidget()
        self.url_input = UrlInputWidget()
        self.correction_panel = CorrectionPanelWidget()

        # Install event filters so capture-hiding is applied on every show
        self.popup.installEventFilter(self)
        self.panel.installEventFilter(self)
        self.text_input.installEventFilter(self)
        self.subtitle.installEventFilter(self)
        self.url_input.installEventFilter(self)
        self.correction_panel.installEventFilter(self)

        # Connect signals
        ui_signals.toggle_panel.connect(self._on_toggle_panel)
        ui_signals.set_multi_state.connect(self.panel.set_multi_state)
        ui_signals.set_source.connect(self._on_set_source)
        ui_signals.set_processing_state.connect(self._on_set_processing_state)
        ui_signals.show_popup.connect(self.popup.show_content)
        ui_signals.close_popup.connect(self.popup.hide)
        ui_signals.capture_popup_screenshot.connect(self.popup.capture_full_page_screenshot)
        ui_signals.request_active_source.connect(_on_request_active_source)
        ui_signals.show_subtitle.connect(self._on_show_subtitle)
        ui_signals.update_subtitle.connect(self._on_update_subtitle)
        ui_signals.clear_subtitles.connect(self._on_clear_subtitles)
        ui_signals.toggle_all_visibility.connect(self._on_toggle_all_visibility)
        ui_signals.show_url_input.connect(self._on_show_url_input)
        ui_signals.open_url.connect(self._on_open_url)
        ui_signals.open_session_browser.connect(self._on_open_session_browser)
        ui_signals.open_context_manager.connect(self._on_open_context_manager)
        ui_signals.set_transcription_language.connect(self._on_set_transcription_language)
        ui_signals.update_chat_sessions_btn.connect(self._on_update_chat_sessions_btn)
        ui_signals.update_periodic_screenshots_btn.connect(self._on_update_periodic_screenshots_btn)
        ui_signals.ocr_text_to_input.connect(self._on_ocr_text_to_input)

    def _on_update_chat_sessions_btn(self, enabled: bool):
        self.panel.chat_sessions_enabled = enabled
        if enabled:
            self.panel.btn_chat_sessions.setText("💬 Chat Sessions: ON")
        else:
            self.panel.btn_chat_sessions.setText("💬 Chat Sessions: OFF")
        self.panel._apply_opacity(self._global_opacity)

    def _on_update_periodic_screenshots_btn(self, enabled: bool):
        self.panel.periodic_screenshots_enabled = enabled
        if enabled:
            self.panel.btn_periodic_screenshots.setText("📷 Screenshots: ON")
        else:
            self.panel.btn_periodic_screenshots.setText("📷 Screenshots: OFF")
        self.panel._apply_opacity(self._global_opacity)

    def _on_open_url(self, url: str):
        self.popup._apply_opacity(self._global_opacity)
        self.popup.load_url(url)

    @staticmethod
    def _on_open_session_browser():
        from ui.session_browser import open_session_browser

        open_session_browser()

    @staticmethod
    def _on_open_context_manager():
        if "open_context_manager" in _app_callbacks:
            _app_callbacks["open_context_manager"]()

    def _on_show_url_input(self):
        self.url_input.update_position()
        self.url_input._apply_opacity(self._global_opacity)
        self.url_input.show()
        self.url_input.raise_()
        self.url_input.activateWindow()
        self.url_input.line_edit.setFocus()

    def _on_ocr_text_to_input(self, text: str):
        """Populate the text input widget with OCR'd text and show it."""
        assert self.text_input is not None
        self.text_input._apply_opacity(self._global_opacity)
        self.text_input.set_ocr_text(text)
        if not self.text_input.isVisible():
            self.text_input.update_position()
            self.text_input.show()
        self.text_input.raise_()
        self.text_input.activateWindow()
        self.text_input.text_edit.setFocus()

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and self._hide_from_capture:
            apply_display_affinity(obj, exclude=True)
        return super().eventFilter(obj, event)

    def set_hide_from_capture(self, hide: bool):
        """Enable or disable capture-hiding on all managed overlay widgets."""
        self._hide_from_capture = hide

    def _on_toggle_panel(self, show):
        assert self.panel is not None
        if show is None:
            show = not self.panel.isVisible()
        if show:
            self.panel._apply_opacity(self._global_opacity)
            self.panel.show()
            self.panel.update_position()
        else:
            self.panel.hide()

    def _on_set_source(self, source_name, opacity):
        assert self.panel is not None
        self._global_opacity = opacity

        # Apply opacity to the panel and all its children
        self.panel._apply_opacity(opacity)
        self.panel.set_source(source_name)

        # Sync the language combos from config when switching to audio
        if source_name == "audio":
            from config.settings import load_config  # noqa: PLC0415
            cfg = load_config()
            self.panel.set_transcription_language_value(
                cfg.get("transcription_language", "en")
            )
            self.panel.update_translation_label(
                cfg.get("translation_language", "")
            )
            self.panel.set_audio_volume_bar_setting(
                cfg.get("show_audio_volume_bar", True)
            )

        if source_name == "text":
            self.text_input._apply_opacity(opacity)
            self.text_input.show()
            self.text_input.update_position()
            self.text_input.text_edit.setFocus()
        else:
            # In image mode the text input is shown on-demand by OCR-to-text-box;
            # for audio/other modes it is also hidden.
            self.text_input.hide()

    def _on_set_transcription_language(self, lang_code: str):
        """Persist transcription language to config and save."""
        from config.settings import load_config, save_config  # noqa: PLC0415
        cfg = load_config()
        cfg["transcription_language"] = lang_code
        save_config(cfg)

    def _on_set_processing_state(self, is_processing):
        self.panel.set_processing_state(is_processing)
        self.text_input.set_processing_state(is_processing)

    def _on_show_subtitle(self, text: str):
        logger = logging.getLogger(__name__)
        logger.info(f"_on_show_subtitle called with text: {text}")
        assert self.subtitle is not None
        self.subtitle.add_subtitle(text)
        logger.info("_on_show_subtitle completed")

    def _on_update_subtitle(self, text: str, append: bool = False):
        logger = logging.getLogger(__name__)
        logger.info(f"_on_update_subtitle called with text: {text}, append: {append}")
        assert self.subtitle is not None
        self.subtitle.update_last_subtitle(text, append=append)
        logger.info("_on_update_subtitle completed")

    def _on_clear_subtitles(self):
        assert self.subtitle is not None
        self.subtitle.clear_subtitles()

    def _on_toggle_all_visibility(self):
        """Toggle visibility of all overlay widgets.

        First press hides everything and saves state;
        second press restores the saved state.
        """
        widgets = {
            "popup": self.popup,
            "panel": self.panel,
            "text_input": self.text_input,
            "subtitle": self.subtitle,
            "correction_panel": self.correction_panel,
        }

        if self._saved_visibility is None:
            # Save current visibility and hide all
            self._saved_visibility = {
                name: w.isVisible() for name, w in widgets.items() if w is not None
            }
            any_visible = any(self._saved_visibility.values())
            if any_visible:
                for w in widgets.values():
                    if w is not None:
                        w.hide()
            else:
                # Nothing was visible – clear saved state so next press is a no-op
                self._saved_visibility = None
        else:
            # Restore saved visibility
            for name, w in widgets.items():
                if w is not None and self._saved_visibility.get(name, False):
                    w.show()
            self._saved_visibility = None

    def get_subtitle_text(self, index: int) -> str:
        if self.subtitle is not None:
            return self.subtitle.get_subtitle_text(index)
        return ""


# Global instance for UI Manager. Will be initialized in main.py after QApplication.
ui_manager: UIManager | None = None


def init_ui_manager():
    global ui_manager
    if ui_manager is None:
        ui_manager = UIManager()
