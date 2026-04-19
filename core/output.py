import pyttsx3
import threading
import json
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit, QScrollArea
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QColor

# --- Signal Broker ---
class UISignals(QObject):
    toggle_panel = pyqtSignal(bool)
    set_multi_state = pyqtSignal(bool)
    set_source = pyqtSignal(str, float)
    set_processing_state = pyqtSignal(bool)
    show_popup = pyqtSignal(dict)
    close_popup = pyqtSignal()
    request_active_source = pyqtSignal(object)

class SelectorSignals(QObject):
    request_coords = pyqtSignal(object)
    coords_ready = pyqtSignal(object)

ui_signals = UISignals()
selector_signals = SelectorSignals()
_app_callbacks = {}


# --- Audio TTS ---
def speak(text, voice_id=None):
    def _speak():
        try:
            engine = pyttsx3.init()
            rate = engine.getProperty('rate')
            engine.setProperty('rate', rate + 25)
            if voice_id:
                engine.setProperty('voice', voice_id)
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"TTS Error: {e}")
    threading.Thread(target=_speak, daemon=True).start()

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
        self.close_btn.setStyleSheet("QPushButton { background-color: transparent; color: white; border: none; font-weight: bold; } QPushButton:hover { color: red; }")
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

class PanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(30, 30, 30, 230); border: 1px solid #444; border-radius: 8px;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # Close Btn
        top_layout = QHBoxLayout()
        top_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { background-color: transparent; color: gray; border: none; } QPushButton:hover { color: white; }")
        close_btn.clicked.connect(self.hide)
        top_layout.addWidget(close_btn)
        self.layout.addLayout(top_layout)

        # Buttons
        self.buttons = {}
        btn_style = "QPushButton { background-color: rgba(45, 45, 45, 180); color: white; border: none; padding: 8px; border-radius: 4px; font-size: 14px;} QPushButton:hover { background-color: rgba(62, 62, 62, 220); } QPushButton:disabled { color: #777; }"

        def create_btn(name, text, action):
            btn = QPushButton(text)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda: self.call_action(action))
            self.layout.addWidget(btn)
            self.buttons[name] = btn
            return btn

        self.btn_capture = create_btn('capture', "📸 Capture", 'capture')
        self.btn_reselect = create_btn('reselect', "🎯 Reselect", 'reselect')
        self.btn_multi = create_btn('multi', "➕ Multi-select", 'multi_capture')
        self.btn_end_multi = create_btn('end_multi', "✅ End Multi", 'end_multi_capture')
        self.btn_cancel_multi = create_btn('cancel_multi', "❌ Cancel Multi", 'cancel_multi_capture')
        self.btn_stitching = create_btn('stitching', "🧵 Toggle Stitching", 'toggle_stitching')
        self.btn_cycle = create_btn('cycle', "🔄 Cycle Source", 'cycle_source')

        self.btn_end_multi.hide()
        self.btn_cancel_multi.hide()

        self.resize(200, 300)

    def call_action(self, action):
        if action in _app_callbacks:
            try:
                # Run callback in background thread so it doesn't block UI
                threading.Thread(target=_app_callbacks[action], daemon=True).start()
            except Exception as e:
                print(f"Error calling {action}: {e}")

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        x = 20
        y = screen.height() - self.height() - 50
        self.move(x, y)

    def set_multi_state(self, in_progress):
        self.btn_end_multi.setVisible(in_progress)
        self.btn_cancel_multi.setVisible(in_progress)
        self.adjustSize()
        self.update_position()

    def set_source(self, source_name):
        is_image = source_name != "text"
        self.btn_capture.setVisible(is_image)
        self.btn_reselect.setVisible(is_image)
        self.btn_multi.setVisible(is_image)
        self.adjustSize()
        self.update_position()

    def set_processing_state(self, is_processing):
        for btn in self.buttons.values():
            btn.setEnabled(not is_processing)

class TextInputWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 8px;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet("background-color: rgba(45, 45, 45, 180); color: white; border: none; font-size: 16px; padding: 5px;")
        # Handle Enter key to submit, Shift+Enter for new line
        self.text_edit.installEventFilter(self)
        self.layout.addWidget(self.text_edit)

        self.is_processing = False

    def eventFilter(self, obj, event):
        if obj is self.text_edit and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False # Allow new line
                else:
                    if not self.is_processing:
                        text = self.text_edit.toPlainText().strip()
                        if text:
                            self.text_edit.clear()
                            if 'text_submit' in _app_callbacks:
                                threading.Thread(target=_app_callbacks['text_submit'], args=(text,), daemon=True).start()
                    return True # Consume event
        return super().eventFilter(obj, event)

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        h = 100 # Fixed initial height
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

    def set_processing_state(self, is_processing):
        self.is_processing = is_processing
        self.text_edit.setEnabled(not is_processing)
        if not is_processing:
            self.text_edit.setFocus()


# --- UI Manager ---
class UIManager(QObject):
    def __init__(self):
        super().__init__()
        self.popup: PopupWidget | None = None
        self.panel: PanelWidget | None = None
        self.text_input: TextInputWidget | None = None
        self._init_ui()
        selector_signals.request_coords.connect(_handle_request_coords)


    def _init_ui(self):
        if not QApplication.instance():
            return # Should not happen, main.py creates it
        self.popup = PopupWidget()
        self.panel = PanelWidget()
        self.text_input = TextInputWidget()

        # Connect signals
        ui_signals.toggle_panel.connect(self._on_toggle_panel)
        ui_signals.set_multi_state.connect(self.panel.set_multi_state)
        ui_signals.set_source.connect(self._on_set_source)
        ui_signals.set_processing_state.connect(self._on_set_processing_state)
        ui_signals.show_popup.connect(self.popup.show_content)
        ui_signals.close_popup.connect(self.popup.hide)
        ui_signals.request_active_source.connect(self._on_request_active_source)

    def _on_request_active_source(self, q):
        import main
        # Sometimes when importing or accessing across modules in PyQt the global var isn't correctly resolved,
        # so let's import it directly instead of through the module object if needed. But accessing main.active_source_instance should work
        # unless it hasn't been set yet. Let's make sure it's valid.
        q.put(getattr(main, 'active_source_instance', None))

    def _on_toggle_panel(self, show):
        if show:
            self.panel.show()
            self.panel.update_position()
        else:
            self.panel.hide()

    def _on_set_source(self, source_name, opacity):
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
    # For now, we assume if show is not provided, it forces show=True or we leave it.
    # The original implementation toggled if show was None.
    # We will simplify by requiring a bool or true.
    ui_signals.toggle_panel.emit(show if show is not None else True)

def update_multi_state(in_progress):
    ui_signals.set_multi_state.emit(in_progress)

def set_active_source_ui(source_name, opacity=0.8):
    ui_signals.set_source.emit(source_name, opacity)

def set_app_processing_state(is_processing):
    ui_signals.set_processing_state.emit(is_processing)

def show_popup(text, auto_close=5000, opacity=0.8, is_result=False, fallback_language="python"):
    ui_signals.show_popup.emit({
        "text": text,
        "auto_close": auto_close,
        "opacity": opacity,
        "is_result": is_result
    })

def output_result(text, output_modes, voice_id=None, auto_close=False, opacity=0.8, fallback_language="python"):
    if not output_modes:
        output_modes = ['popup']

    if 'audio' in output_modes:
        speak(text, voice_id)

    if 'popup' in output_modes:
        show_popup(text, auto_close=5000 if auto_close else None, opacity=opacity, is_result=True, fallback_language=fallback_language)

def get_active_source():
    import queue
    import threading
    import main

    app = QApplication.instance()
    if app and app.thread() == threading.current_thread():
        return getattr(main, 'active_source_instance', None)

    q = queue.Queue()
    ui_signals.request_active_source.emit(q)
    return q.get()

def _handle_request_coords(q):
    from ui.selector import _get_coordinates_impl
    # Pass the queue's put method directly as the callback
    _get_coordinates_impl(callback=q.put)
