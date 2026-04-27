import json
import threading

from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel


# --- Signal Broker ---
class UISignals(QObject):
    toggle_panel = pyqtSignal(bool)
    set_multi_state = pyqtSignal(bool)
    set_source = pyqtSignal(str, float)
    set_processing_state = pyqtSignal(bool)
    show_popup = pyqtSignal(dict)
    close_popup = pyqtSignal()
    request_active_source = pyqtSignal(object)
    show_subtitle = pyqtSignal(str)
    clear_subtitles = pyqtSignal()


class SelectorSignals(QObject):
    request_coords = pyqtSignal(object)
    coords_ready = pyqtSignal(object)


ui_signals = UISignals()
selector_signals = SelectorSignals()
_app_callbacks = {}


# --- PyQt UI Components ---

class PopupWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: #1e1e1e; border: 2px solid #555; border-radius: 10px;")

        self.layout = QVBoxLayout(self)

        # Top Bar
        self.top_bar = QHBoxLayout()
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: white; border: none; font-weight: bold; } QPushButton:hover { color: red; }")
        self.close_btn.clicked.connect(self.hide)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.close_btn)
        self.layout.addLayout(self.top_bar)

        # WebEngine View for Markdown/Math
        self.web_view = QWebEngineView()
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        self.web_view.setStyleSheet("background-color: transparent; border: none;")
        self.layout.addWidget(self.web_view)

        self.auto_close_timer = QTimer(self)
        self.auto_close_timer.timeout.connect(self.hide)

        # Create base HTML template
        # Note: raw string to avoid invalid escape sequence warning with \s
        self.base_html = r"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
            <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    color: white;
                    background-color: #1e1e1e;
                    margin: 0;
                    padding: 10px;
                    font-size: 14px;
                    overflow-x: hidden;
                }
                pre { background-color: #282a36; padding: 10px; border-radius: 5px; overflow-x: auto; }
                code { font-family: Courier, monospace; background-color: #282a36; padding: 2px 4px; border-radius: 3px; }
                table { border-collapse: collapse; width: 100%; margin-bottom: 10px; }
                th, td { border: 1px solid #444; padding: 8px; text-align: left; }
                th { background-color: #333; }
                a { color: #8be9fd; }
                /* Custom scrollbar for webkit */
                ::-webkit-scrollbar { width: 8px; height: 8px; }
                ::-webkit-scrollbar-track { background: #1e1e1e; }
                ::-webkit-scrollbar-thumb { background: #555; border-radius: 4px; }
                ::-webkit-scrollbar-thumb:hover { background: #777; }
            </style>
        </head>
        <body>
            <div id="content"></div>
            <script>
                mermaid.initialize({ startOnLoad: false, theme: 'dark' });

                function updateContent(markdownText) {
                    // Temporarily replace mermaid blocks so marked doesn't touch them
                    let mermaidBlocks = [];
                    let tempText = markdownText.replace(/```mermaid([\s\S]*?)```/g, function(match, p1) {
                        mermaidBlocks.push(p1);
                        return `___MERMAID_BLOCK_${mermaidBlocks.length - 1}___`;
                    });

                    // Parse markdown
                    let html = marked.parse(tempText);

                    // Restore mermaid blocks
                    mermaidBlocks.forEach((block, index) => {
                        html = html.replace(`___MERMAID_BLOCK_${index}___`, `<div class="mermaid">${block}</div>`);
                    });

                    document.getElementById('content').innerHTML = html;

                    // Render Math
                    renderMathInElement(document.getElementById('content'), {
                        delimiters: [
                            {left: "$$", right: "$$", display: true},
                            {left: "$", right: "$", display: false},
                            {left: "\\(", right: "\\)", display: false},
                            {left: "\\[", right: "\\]", display: true}
                        ]
                    });

                    // Render Mermaid
                    mermaid.init(undefined, document.querySelectorAll('.mermaid'));

                    // Scroll to bottom smoothly
                    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                }
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(self.base_html)

    def show_content(self, data):
        text = data.get("text", "")
        auto_close = data.get("auto_close", 5000)
        opacity = data.get("opacity", 0.8)
        is_result = data.get("is_result", False)

        self.setWindowOpacity(opacity)

        # Safely serialize string for JS injection using json.dumps
        js_text = json.dumps(text)

        # Update via JS evaluation
        self.web_view.page().runJavaScript(f"updateContent({js_text});")

        # Determine size and position
        screen = QApplication.primaryScreen().size()
        max_w, max_h = int(screen.width() * 0.5), int(screen.height() * 0.5)

        word_count = len(text.split())
        is_long = is_result and word_count > 10

        if is_long:
            # Estimate sizing, max out at 50%
            self.resize(max_w, max_h)
        else:
            # Small popup
            self.resize(400, 150)

        # Position bottom right
        w, h = self.width(), self.height()
        x = screen.width() - w - 50
        y = screen.height() - h - 100
        self.move(x, y)

        if auto_close:
            self.close_btn.hide()
            self.auto_close_timer.start(auto_close)
        else:
            self.close_btn.show()
            self.auto_close_timer.stop()

        self.show()


class RecordButton(QPushButton):
    # Signals for different actions
    start_recording = pyqtSignal()
    stop_recording = pyqtSignal()

    def __init__(self, text, style):
        super().__init__(text)
        self.setStyleSheet(style)
        self.is_recording = False
        self.is_long_press = False
        self.press_timer = QTimer(self)
        self.press_timer.setSingleShot(True)
        self.press_timer.timeout.connect(self.on_long_press)

    # noinspection PyPep8Naming
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_long_press = False
            self.press_timer.start(500)  # 500ms for long press

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_timer.stop()
            if self.is_long_press:
                # It was a long press, so releasing stops the recording
                self.stop_record_action()
            else:
                # It was a click, toggle recording state
                if self.is_recording:
                    self.stop_record_action()
                else:
                    self.start_record_action()

    def on_long_press(self):
        self.is_long_press = True
        if not self.is_recording:
            self.start_record_action()

    def start_record_action(self):
        self.is_recording = True
        self.setText("⏹️ Stop / 🔴 Recording...")
        self.setStyleSheet(self.styleSheet().replace("rgba(45, 45, 45, 180)", "rgba(178, 34, 34, 0.7)"))
        self.start_recording.emit()

    def stop_record_action(self):
        self.is_recording = False
        self.setText("🎙️ Record")
        self.setStyleSheet(self.styleSheet().replace("rgba(178, 34, 34, 0.7)", "rgba(45, 45, 45, 180)"))
        self.stop_recording.emit()


class SubtitleWidget(QWidget):
    """Widget for displaying real-time transcription subtitles with fading effects."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        # Remove WA_TranslucentBackground to ensure proper rendering
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Use a more visible background for debugging
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.8); border: 2px solid red;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        # Store subtitle labels with their creation time
        self.subtitle_labels = []
        self.max_subtitles = 5  # Maximum number of subtitle lines to show
        self.fade_duration = 15000  # Duration for fade effect in milliseconds (15 seconds)

        # Timer for updating fade effects
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self.update_fade_effects)
        self.fade_timer.start(100)  # Update every 100ms

        # Position settings
        self.target_position = None
        self.update_position()

    def update_position(self):
        """Position widget at bottom center of screen."""
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        self.setFixedWidth(w)
        self.adjustSize()
        h = self.height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Subtitle widget positioned at ({x}, {y}) with size ({w}, {h})")
        logger.info(f"Screen size: {screen.width()}x{screen.height()}")

    def add_subtitle(self, text: str):
        """Add a new subtitle line."""
        import time
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"add_subtitle called with text: {text}")
        logger.info(f"Subtitle widget visible: {self.isVisible()}")
        logger.info(f"Subtitle widget position: {self.pos()}, size: {self.size()}")

        # Create new subtitle label
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: rgba(255, 255, 255, 1.0);
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        # Store with creation time
        label.creation_time = time.time()
        self.subtitle_labels.append(label)

        # Add to layout
        self.layout.addWidget(label)

        # Remove oldest if we have too many
        if len(self.subtitle_labels) > self.max_subtitles:
            oldest = self.subtitle_labels.pop(0)
            self.layout.removeWidget(oldest)
            oldest.deleteLater()

        # Force layout update before adjusting size
        self.layout.activate()

        # Update widget size
        self.adjustSize()
        self.update_position()

        # Ensure widget has minimum height
        if self.height() == 0:
            self.setMinimumHeight(50)
            self.adjustSize()

        # Show if hidden
        if not self.isVisible():
            logger.info("Subtitle widget was hidden, attempting to show it")
            self.show()
            self.raise_()  # Bring to front
            self.activateWindow()  # Force window activation
            self.repaint()  # Force repaint
            logger.info(f"After show(), widget visible: {self.isVisible()}, size: {self.size()}")

    def update_last_subtitle(self, text: str):
        """Update the text of the most recent subtitle instead of creating a new one."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"update_last_subtitle called with text: {text}")

        if not self.subtitle_labels:
            # No existing subtitles, create a new one
            logger.info("No existing subtitles, creating new one")
            self.add_subtitle(text)
            return

        # Update the last subtitle's text
        last_label = self.subtitle_labels[-1]
        last_label.setText(text)
        logger.info(f"Updated last subtitle to: {text}")

        # Force layout update and size adjustment
        self.layout.activate()
        self.adjustSize()
        self.update_position()

        # Ensure widget is visible
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            self.repaint()

    def clear_subtitles(self):
        """Clear all subtitles."""
        for label in self.subtitle_labels:
            self.layout.removeWidget(label)
            label.deleteLater()
        self.subtitle_labels.clear()
        self.hide()

    def update_fade_effects(self):
        """Update opacity of subtitle labels based on their age."""
        import time

        current_time = time.time()

        for i, label in enumerate(self.subtitle_labels):
            # Calculate age in seconds
            age = current_time - label.creation_time

            # Calculate opacity based on position and age
            # Newer subtitles (higher index) are more opaque
            # Older subtitles fade out more gradually
            position_factor = (i + 1) / len(self.subtitle_labels) if self.subtitle_labels else 1

            # More gradual fading - start fading after 5 seconds, complete fade by fade_duration
            fade_start = 5.0  # Start fading after 5 seconds
            if age < fade_start:
                age_factor = 1.0  # Full opacity for first 5 seconds
            else:
                age_factor = max(0.3, 1.0 - ((age - fade_start) / ((self.fade_duration / 1000) - fade_start)))

            # Combine factors, but ensure minimum visibility
            opacity = min(0.95, max(0.4, position_factor * age_factor))

            # Update label style with new opacity
            label.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, {opacity * 0.7:.3f});
                    color: rgba(255, 255, 255, {opacity:.3f});
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 16px;
                    font-weight: bold;
                }}
            """)

        # Remove very old subtitles
        if self.subtitle_labels:
            oldest_age = current_time - self.subtitle_labels[0].creation_time
            if oldest_age > (self.fade_duration / 1000) * 2:  # Remove after 2x fade duration
                oldest = self.subtitle_labels.pop(0)
                self.layout.removeWidget(oldest)
                oldest.deleteLater()
                self.adjustSize()
                self.update_position()


def call_action(action):
    if action in _app_callbacks:
        try:
            # Run callback in background thread so it doesn't block UI
            threading.Thread(target=_app_callbacks[action], daemon=True).start()
        except Exception as e:
            print(f"Error calling {action}: {e}")


class PanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(30, 30, 30, 230); border: 1px solid #444; border-radius: 8px;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.is_multi_selecting = False

        # Close Btn
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: gray; border: none; } QPushButton:hover { color: white; }")
        close_btn.clicked.connect(self.hide)
        top_layout.addWidget(close_btn)
        self.layout.addLayout(top_layout)

        # Buttons
        self.buttons = {}
        btn_style = "QPushButton { background-color: rgba(45, 45, 45, 180); color: white; border: none; padding: 8px; border-radius: 4px; font-size: 14px;} QPushButton:hover { background-color: rgba(62, 62, 62, 220); } QPushButton:disabled { color: #777; }"
        cancel_btn_style = "QPushButton { background-color: rgba(178, 34, 34, 0.7); color: white; border: none; padding: 8px; border-radius: 4px; font-size: 14px;} QPushButton:hover { background-color: rgba(220, 20, 60, 0.8); }"

        def create_btn(name, text, action, style=btn_style):
            btn = QPushButton(text)
            btn.setStyleSheet(style)
            btn.clicked.connect(lambda: call_action(action))
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            return btn

        self.btn_record = RecordButton("🎙️ Record", btn_style)
        self.btn_record.start_recording.connect(lambda: call_action('start_record'))
        self.btn_record.stop_recording.connect(lambda: call_action('stop_record'))
        self.layout.addWidget(self.btn_record)
        self.buttons['record'] = self.btn_record

        self.btn_capture = create_btn('capture', "📸 Capture", 'capture')
        self.btn_reselect = create_btn('reselect', "🎯 Reselect", 'reselect')
        self.btn_multi = create_btn('multi', "➕ Multi-select", 'multi_capture')
        self.btn_end_multi = create_btn('end_multi', "✅ End Multi", 'end_multi_capture')
        self.btn_stitching = create_btn('stitching', "🧵 Toggle Stitching", 'toggle_stitching')
        self.btn_cycle = create_btn('cycle', "🔄 Cycle Source", 'cycle_source')
        self.btn_cancel = create_btn('cancel', "❌ Cancel", 'cancel', style=cancel_btn_style)

        self.btn_end_multi.hide()
        self.btn_cancel.hide()

        self.resize(200, 300)

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

    def set_source(self, source_name):
        is_image = source_name == "image"
        is_audio = source_name == "audio"
        self.btn_capture.setVisible(is_image)
        self.btn_reselect.setVisible(is_image)
        self.btn_multi.setVisible(is_image)
        self.btn_record.setVisible(is_audio)
        self.adjustSize()
        self.update_position()

    def set_processing_state(self, is_processing):
        if not self.is_multi_selecting:
            self.btn_cancel.setVisible(is_processing)
        for name, btn in self.buttons.items():
            if name != 'cancel':
                btn.setEnabled(not is_processing)
        self.adjustSize()
        self.update_position()


class TextInputWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 8px;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet(
            "background-color: rgba(45, 45, 45, 180); color: white; border: none; font-size: 16px; padding: 5px;")
        # Handle Enter key to submit, Shift+Enter for new line
        self.text_edit.installEventFilter(self)
        self.layout.addWidget(self.text_edit)

        self.is_processing = False

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event):
        if obj is self.text_edit and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # Allow new line
                else:
                    if not self.is_processing:
                        text = self.text_edit.toPlainText().strip()
                        if text:
                            self.text_edit.clear()
                            if 'text_submit' in _app_callbacks:
                                threading.Thread(target=_app_callbacks['text_submit'], args=(text,),
                                                 daemon=True).start()
                    return True  # Consume event
        return super().eventFilter(obj, event)

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        h = 100  # Fixed initial height
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

    def set_processing_state(self, is_processing):
        self.is_processing = is_processing
        self.text_edit.setEnabled(not is_processing)
        if not is_processing:
            self.text_edit.setFocus()


# --- UI Manager ---
def _on_request_active_source(q):
    from core.sources import get_active_source_instance
    q.put(get_active_source_instance())


class UIManager(QObject):
    def __init__(self):
        super().__init__()
        self.popup: PopupWidget | None = None
        self.panel: PanelWidget | None = None
        self.text_input: TextInputWidget | None = None
        self.subtitle: SubtitleWidget | None = None
        self._init_ui()
        selector_signals.request_coords.connect(_handle_request_coords)

    def _init_ui(self):
        if not QApplication.instance():
            return  # Should not happen, main.py creates it
        self.popup = PopupWidget()
        self.panel = PanelWidget()
        self.text_input = TextInputWidget()
        self.subtitle = SubtitleWidget()

        # Connect signals
        ui_signals.toggle_panel.connect(self._on_toggle_panel)
        ui_signals.set_multi_state.connect(self.panel.set_multi_state)
        ui_signals.set_source.connect(self._on_set_source)
        ui_signals.set_processing_state.connect(self._on_set_processing_state)
        ui_signals.show_popup.connect(self.popup.show_content)
        ui_signals.close_popup.connect(self.popup.hide)
        ui_signals.request_active_source.connect(_on_request_active_source)
        ui_signals.show_subtitle.connect(self._on_show_subtitle)
        ui_signals.clear_subtitles.connect(self._on_clear_subtitles)

    def _on_toggle_panel(self, show):
        assert self.panel is not None
        if show:
            self.panel.show()
            self.panel.update_position()
        else:
            self.panel.hide()

    def _on_set_source(self, source_name, opacity):
        assert self.panel is not None
        self.panel.set_source(source_name)
        if source_name == "text":
            self.text_input.setWindowOpacity(opacity)
            self.text_input.show()
            self.text_input.update_position()
            self.text_input.text_edit.setFocus()
        else:
            self.text_input.hide()

    def _on_set_processing_state(self, is_processing):
        self.panel.set_processing_state(is_processing)
        self.text_input.set_processing_state(is_processing)

    def _on_show_subtitle(self, text: str):
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"_on_show_subtitle called with text: {text}")
        assert self.subtitle is not None
        self.subtitle.add_subtitle(text)
        logger.info("_on_show_subtitle completed")

    def _on_clear_subtitles(self):
        assert self.subtitle is not None
        self.subtitle.clear_subtitles()


# Global instance for UI Manager. Will be initialized in main.py after QApplication.
ui_manager: UIManager | None = None


def init_ui_manager():
    global ui_manager
    if ui_manager is None:
        ui_manager = UIManager()


def set_app_callbacks(callbacks):
    global _app_callbacks
    _app_callbacks = callbacks


# --- Public API called from background threads ---
def toggle_control_panel(show=None):
    # show is optional, but logic for toggle isn't fully robust here without checking state.
    # For now, we assume if show is not provided, it forces show=True, or we leave it.
    # The original implementation toggled if show was None.
    # We will simplify by requiring a bool or true.
    ui_signals.toggle_panel.emit(show if show is not None else True)


def update_multi_state(in_progress):
    ui_signals.set_multi_state.emit(in_progress)


def set_active_source_ui(source_name, opacity=0.8):
    ui_signals.set_source.emit(source_name, opacity)


def set_app_processing_state(is_processing):
    ui_signals.set_processing_state.emit(is_processing)


def show_popup(text, auto_close=5000, opacity=0.8, is_result=False):
    ui_signals.show_popup.emit({
        "text": text,
        "auto_close": auto_close,
        "opacity": opacity,
        "is_result": is_result
    })


def close_popup():
    ui_signals.close_popup.emit()


def show_subtitle(text: str):
    """Show a subtitle line with real-time transcription."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"show_subtitle called with text: {text}")
    ui_signals.show_subtitle.emit(text)
    logger.info("show_subtitle signal emitted")


def clear_subtitles():
    """Clear all subtitle lines."""
    ui_signals.clear_subtitles.emit()


def output_result(text, output_modes, _voice_id=None, auto_close=False, opacity=0.8):
    if not output_modes:
        output_modes = ['popup']

    # Audio is now handled by the AudioSink in the pipeline

    if 'popup' in output_modes:
        show_popup(text, auto_close=5000 if auto_close else None, opacity=opacity, is_result=True)


def get_active_source():
    import queue
    import threading
    from core.sources import get_active_source_instance

    app = QApplication.instance()
    if app and app.thread() == threading.current_thread():
        return get_active_source_instance()

    q = queue.Queue()
    ui_signals.request_active_source.emit(q)
    return q.get()


def _handle_request_coords(q):
    from ui.selector import get_coordinates
    # Pass the queue's put method directly as the callback
    get_coordinates(callback=q.put)
