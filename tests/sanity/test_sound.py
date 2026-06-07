import difflib
import json
import logging
import os
import string
import subprocess
import threading
import wave

import numpy as np
import pyaudio
import resampy
import speech_recognition as sr
import sys
import time

# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)

from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QTextEdit,
    QPushButton,
    QProgressBar,
)
from PyQt6.QtCore import pyqtSignal, QObject  # noqa: E402

# Add WhisperLive to path
whisperlive_path = os.path.join(
    str(os.path.dirname(os.path.dirname(str(os.path.dirname(__file__))))),
    "services",
    "whisperlive",
)
if whisperlive_path not in sys.path:
    sys.path.insert(0, whisperlive_path)

from whisper_live.client import TranscriptionClient as WhisperLiveTranscriptionClient  # noqa: E402

# --- Language data (self-contained, no imports from main app) ---
# (display_name, whisper_code, google_locale, piper_model_basename)
_LANGUAGES = [
    ("English", "en", "en-US", "en_US-lessac-high.onnx"),
    ("Spanish", "es", "es-ES", "es_ES-davefx-medium.onnx"),
    ("French", "fr", "fr-FR", "fr_FR-upmc-medium.onnx"),
    ("German", "de", "de-DE", "de_DE-thorsten-high.onnx"),
    ("Italian", "it", "it-IT", "it_IT-riccardo-x_low.onnx"),
    ("Portuguese", "pt", "pt-BR", "pt_BR-faber-medium.onnx"),
    ("Russian", "ru", "ru-RU", "ru_RU-irina-medium.onnx"),
    ("Chinese", "zh", "zh-CN", "zh_CN-huayan-medium.onnx"),
    ("Japanese", "ja", "ja-JP", ""),
    ("Korean", "ko", "ko-KR", ""),
    ("Arabic", "ar", "ar-SA", "ar_JO-kareem-medium.onnx"),
    ("Hindi", "hi", "hi-IN", ""),
    ("Turkish", "tr", "tr-TR", "tr_TR-dfki-medium.onnx"),
    ("Polish", "pl", "pl-PL", "pl_PL-darkman-medium.onnx"),
    ("Dutch", "nl", "nl-NL", "nl_NL-mls-medium.onnx"),
    ("Swedish", "sv", "sv-SE", "sv_SE-nst-medium.onnx"),
]


def is_whisperlive_service_online(host="localhost", port=9090):
    """Check if WhisperLive service is online by checking if port is open."""
    try:
        import socket

        # Simply check if the port is open - don't make a full WebSocket connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            logging.debug(f"Port {port} is open - service appears to be running")
            return True
        else:
            logging.debug(f"Port {port} is not open")
            return False
    except Exception as e:
        logging.debug(f"Service health check failed: {e}")
        return False


def start_whisperlive_service():
    """Start WhisperLive service if not already running."""
    whisperlive_path = os.path.join(
        str(os.path.dirname(str(os.path.dirname(str(os.path.dirname(__file__)))))),
        "services",
        "whisperlive",
    )

    server_script = os.path.join(whisperlive_path, "run_server.py")

    if not os.path.exists(server_script):
        print(f"Error: WhisperLive server script not found at {server_script}")
        return None

    try:
        # Check if the service is already running by checking the port
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 9090))
        sock.close()

        if result == 0:
            print("WhisperLive service is already running on port 9090")
            return None  # Service is already running, don't start a new one

        venv_python = (
            os.path.join(whisperlive_path, ".venv", "Scripts", "python.exe")
            if os.name == "nt"
            else os.path.join(whisperlive_path, ".venv", "bin", "python")
        )
        python_exec = venv_python if os.path.exists(venv_python) else sys.executable

        # Start the server in a subprocess with extended connection time
        process = subprocess.Popen(
            [
                python_exec,
                server_script,
                "--port",
                "9090",
                "--backend",
                "faster_whisper",
                "--max_clients",
                "4",
                "--max_connection_time",
                "60",  # 1 minute
                "--no_single_model",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait a bit for the server to start
        time.sleep(5)

        # Check if it's running
        if process.poll() is None:
            print(f"WhisperLive service started (PID: {process.pid})")
            return process
        else:
            stdout, stderr = process.communicate()
            print("Failed to start WhisperLive service")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return None

    except Exception as e:
        print(f"Error starting WhisperLive service: {e}")
        return None


class WorkerSignals(QObject):
    update_volume = pyqtSignal(int)
    update_heard = pyqtSignal(str)
    append_heard = pyqtSignal(str)
    playback_started = pyqtSignal()
    playback_finished = pyqtSignal()
    record_finished = pyqtSignal()
    transcription_finished = pyqtSignal()
    log_message = pyqtSignal(str)


class SoundTestApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sound Test")
        self.resize(600, 500)

        self.p = pyaudio.PyAudio()
        self.signals = WorkerSignals()
        self.signals.update_volume.connect(self.update_volume_bar)
        self.signals.update_heard.connect(self.set_heard_text)
        self.signals.append_heard.connect(self.append_heard_text)
        self.signals.playback_started.connect(self.on_playback_started)
        self.signals.playback_finished.connect(self.on_playback_finished)
        self.signals.transcription_finished.connect(self.on_transcription_finished)
        self.signals.log_message.connect(self.log)

        # Hardcoded model
        self.piper_model = "en_US-lessac-high.onnx"
        self.settings_file = "sound_test_settings.json"
        self.DEVICE_SELECTION_ERROR = "Please select both input and output devices."
        self.UNKNOWN_DEVICE_NAME = "Unknown Device"
        self.selected_whisper_lang = "en"
        self.selected_google_locale = "en-US"

        self.is_recording = False
        self.is_transcribing = False
        self.playback_done = False
        self.playback_started = False
        self.audio_frames = []
        self.transcription_client = None
        self.transcription_text = ""
        self.whisperlive_process = None

        # UI components (initialized in init_ui)
        self.out_combo = QComboBox()
        self.in_combo = QComboBox()
        self.loop_combo = QComboBox()
        self.speak_text = QTextEdit()
        self.heard_text = QTextEdit()
        self.volume_bar = QProgressBar()
        self.log_text = QTextEdit()
        self.playback_only_btn = QPushButton()
        self.recording_btn = QPushButton()
        self.transcription_btn = QPushButton()
        self.lang_combo = QComboBox()

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Output Device
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("Output Device:"))
        out_layout.addWidget(self.out_combo)
        layout.addLayout(out_layout)

        # Input Device
        in_layout = QHBoxLayout()
        in_layout.addWidget(QLabel("Input Device:"))
        in_layout.addWidget(self.in_combo)
        layout.addLayout(in_layout)
        
        # Loopback Device
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("Loopback Device:"))
        loop_layout.addWidget(self.loop_combo)
        layout.addLayout(loop_layout)

        self.populate_devices()
        self.load_settings()

        # Language Selection
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        for display_name, code, _glocale, _piper in _LANGUAGES:
            self.lang_combo.addItem(display_name, code)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_layout.addWidget(self.lang_combo)
        layout.addLayout(lang_layout)

        # Text to Speak
        layout.addWidget(QLabel("Text to Speak:"))
        self.speak_text.setText(
            "What is the 5th largest country in the world?\ngive me a brief answer."
        )
        self.speak_text.setMaximumHeight(80)
        layout.addWidget(self.speak_text)

        # Text Heard
        layout.addWidget(QLabel("Text Heard:"))
        self.heard_text.setReadOnly(True)
        self.heard_text.setMaximumHeight(80)
        layout.addWidget(self.heard_text)

        # Volume Progress Bar
        layout.addWidget(QLabel("Microphone Volume:"))
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        self.volume_bar.setTextVisible(False)
        self.volume_bar.setStyleSheet(
            """
            QProgressBar {
                min-height: 30px;
                max-height: 30px;
                border-radius: 15px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 15px;
            }
            """
        )
        layout.addWidget(self.volume_bar)

        # Log
        layout.addWidget(QLabel("Log:"))
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Action Buttons
        button_layout = QHBoxLayout()

        self.playback_only_btn = QPushButton("Playback Only")
        self.playback_only_btn.clicked.connect(self.start_playback_only)
        button_layout.addWidget(self.playback_only_btn)

        self.recording_btn = QPushButton("Recording Test")
        self.recording_btn.clicked.connect(self.start_recording_test)
        button_layout.addWidget(self.recording_btn)

        self.transcription_btn = QPushButton("Transcription Test")
        self.transcription_btn.clicked.connect(self.start_transcription_test)
        button_layout.addWidget(self.transcription_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_operations)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def populate_devices(self):
        count = self.p.get_device_count()
        logging.debug(f"Populating devices. Total devices found: {count}")
        for i in range(count):
            try:
                info = self.p.get_device_info_by_index(i)
                host_api = self.p.get_host_api_info_by_index(int(info["hostApi"]))[
                    "name"
                ]
                name = info["name"]
                desc = f"[{host_api}] {name} (Index: {i})"

                if info["maxOutputChannels"] > 0:
                    self.out_combo.addItem(desc, i)
                if info["maxInputChannels"] > 0:
                    self.in_combo.addItem(desc, i)
            except Exception as e:
                logging.warning(f"Failed to load device index {i}: {e}")

        # Input Devices are already populated by PyAudio loop above.
        self.in_combo.insertItem(0, "Default System Input", None)
        
        # Populate Loopback Devices using soundcard directly
        self.loop_combo.addItem("None (Disabled)", None)
        try:
            import soundcard as sc
            devices = sc.all_speakers()
            devices.sort(key=lambda x: x.name.lower())
            for speaker in devices:
                self.loop_combo.addItem(speaker.name, speaker.name)
        except Exception as e:
            self.log(f"Failed to load loopback devices: {e}")

    def load_settings(self):
        logging.debug("Attempting to load last selected devices...")
        if os.path.exists(self.settings_file):
            try:
                import json

                with open(self.settings_file, "r") as f:
                    data = json.load(f)

                if "out_idx" in data:
                    idx = self.out_combo.findData(data["out_idx"])
                    if idx >= 0:
                        self.out_combo.setCurrentIndex(idx)

                if "in_idx" in data:
                    idx = self.in_combo.findData(data["in_idx"])
                    if idx >= 0:
                        self.in_combo.setCurrentIndex(idx)
                        
                if "loop_name" in data:
                    idx = self.loop_combo.findData(data["loop_name"])
                    if idx >= 0:
                        self.loop_combo.setCurrentIndex(idx)

                if "lang_code" in data:
                    idx = self.lang_combo.findData(data["lang_code"])
                    if idx >= 0:
                        self.lang_combo.setCurrentIndex(idx)
            except Exception as e:
                print(f"Failed to load settings: {e}")

    def save_settings(self, out_idx, in_idx, loop_name=None):
        try:
            import json

            data = {
                "out_idx": out_idx,
                "in_idx": in_idx,
                "loop_name": loop_name,
                "lang_code": self.lang_combo.currentData(),
            }
            with open(self.settings_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

    def _on_language_changed(self, index):
        """Update TTS model and recognition language when the combo changes."""
        if index < 0 or index >= len(_LANGUAGES):
            return
        display_name, code, google_locale, piper_basename = _LANGUAGES[index]
        self.selected_whisper_lang = code
        self.selected_google_locale = google_locale
        if piper_basename:
            self.piper_model = piper_basename
            if not os.path.exists(piper_basename):
                self.log(f"⚠ Piper model '{piper_basename}' not found locally. TTS may fail for {display_name}.")
        else:
            self.log(f"ℹ No Piper TTS model available for {display_name}. TTS playback will be skipped.")
            self.piper_model = ""

    def log(self, message):
        logging.info(message)
        self.log_text.append(message)

    def update_volume_bar(self, val):
        self.volume_bar.setValue(val)

    def set_heard_text(self, text):
        self.heard_text.setText(text)

    def append_heard_text(self, text):
        # current_text = self.heard_text.toPlainText()
        # if current_text:
        #     self.heard_text.setText(current_text + " " + text)
        # else:
        self.heard_text.setText(text)

    def on_playback_started(self):
        self.playback_started = True
        self.log("Playback started. Beginning recording...")

    def on_playback_finished(self):
        self.playback_done = True
        self.log("Playback finished. Stopping recording...")
        self._enable_buttons()
        self.signals.update_volume.emit(0)

    def on_transcription_finished(self):
        self.is_transcribing = False
        self.log("Transcription finished.")
        self._enable_buttons()

    def cancel_operations(self):
        self.playback_done = True
        self.is_recording = False
        self.is_transcribing = False
        self.log("Operations cancelled by user.")

    def _enable_buttons(self):
        import PyQt6.QtCore as QtCore

        QtCore.QMetaObject.invokeMethod(
            self.playback_only_btn,
            "setEnabled",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(bool, True),
        )
        QtCore.QMetaObject.invokeMethod(
            self.recording_btn,
            "setEnabled",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(bool, True),
        )
        QtCore.QMetaObject.invokeMethod(
            self.transcription_btn,
            "setEnabled",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(bool, True),
        )
        QtCore.QMetaObject.invokeMethod(
            self.cancel_btn,
            "setEnabled",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(bool, False),
        )

    def start_playback_only(self):
        self.playback_only_btn.setEnabled(False)
        self.recording_btn.setEnabled(False)
        self.transcription_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log(self.DEVICE_SELECTION_ERROR)
            self._enable_buttons()
            return

        self.save_settings(out_idx, in_idx)

        self.playback_done = False

        threading.Thread(
            target=self.play_audio, args=(text, out_idx), daemon=True
        ).start()
        threading.Thread(
            target=self.monitor_mic_volume, args=(in_idx,), daemon=True
        ).start()

    def start_recording_test(self):
        self.playback_only_btn.setEnabled(False)
        self.recording_btn.setEnabled(False)
        self.transcription_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_text.clear()
        self.heard_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log(self.DEVICE_SELECTION_ERROR)
            self._enable_buttons()
            return

        self.save_settings(out_idx, in_idx)

        self.playback_done = False
        self.is_recording = True
        self.audio_frames = []

        # Run playback and record in separate background threads
        threading.Thread(
            target=self.play_audio, args=(text, out_idx), daemon=True
        ).start()
        threading.Thread(target=self.record_audio, args=(in_idx,), daemon=True).start()

    def start_transcription_test(self):
        self.playback_only_btn.setEnabled(False)
        self.recording_btn.setEnabled(False)
        self.transcription_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_text.clear()
        self.heard_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        loop_name = self.loop_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log(self.DEVICE_SELECTION_ERROR)
            self._enable_buttons()
            return

        self.save_settings(out_idx, in_idx, loop_name)

        # Check if WhisperLive service is online
        self.log("Checking WhisperLive service status...")
        if not is_whisperlive_service_online():
            self.log("WhisperLive service is not running. Starting it...")
            self.whisperlive_process = start_whisperlive_service()
            if self.whisperlive_process is None:
                self.log("WhisperLive service is already running or failed to start.")
                # Check again to see if it's actually running
                if is_whisperlive_service_online():
                    self.log("WhisperLive service is running. Proceeding with test.")
                else:
                    self.log("Failed to start WhisperLive service. Aborting test.")
                    self._enable_buttons()
                    return

            # Wait longer for the service to be fully ready
            self.log("Waiting for WhisperLive service to be ready...")
            time.sleep(5)
        else:
            self.log("WhisperLive service is running. Proceeding with test.")

        self.playback_done = False
        self.is_transcribing = True
        self.audio_frames = []
        self.transcription_text = ""

        server_ready_event = threading.Event()

        # Run playback and record in separate background threads
        threading.Thread(
            target=self.play_audio,
            args=(text, out_idx, server_ready_event),
            daemon=True,
        ).start()

        # Record and transcribe in a separate thread
        def record_and_transcribe():
            self.record_audio_to_file(in_idx, server_ready_event)
            self.run_transcription()

        threading.Thread(target=record_and_transcribe, daemon=True).start()

    def _check_piper_model_exists(self):
        """Check if Piper model and config exist."""
        if not os.path.exists(self.piper_model):
            self.signals.log_message.emit(
                f"Piper model not found at {self.piper_model}"
            )
            return False

        piper_config_path = self.piper_model + ".json"
        if not os.path.exists(piper_config_path):
            self.signals.log_message.emit(
                f"Piper config not found at {piper_config_path}"
            )
            return False

        return True

    def _load_piper_voice(self):
        """Load Piper voice model."""
        from piper import PiperVoice

        self.signals.log_message.emit("Loading Piper voice model...")
        piper_config_path = self.piper_model + ".json"
        return PiperVoice.load(self.piper_model, config_path=piper_config_path)

    def _synthesize_audio_lines(self, voice, text):
        """Synthesize audio lines."""
        import io

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return None

        audio_buffers = []
        sample_rate = voice.config.sample_rate

        for i, line in enumerate(lines):
            line_buffer = io.BytesIO()
            with wave.open(line_buffer, "wb") as wav:
                voice.synthesize_wav(line, wav)
            line_buffer.seek(0)

            with wave.open(line_buffer, "rb") as wav:
                frames = wav.readframes(wav.getnframes())
                audio_buffers.append(frames)

            if i < len(lines) - 1:
                silence_samples = int(2 * sample_rate)
                silence = np.zeros(silence_samples, dtype=np.int16)
                audio_buffers.append(silence.tobytes())

        return audio_buffers, sample_rate

    def _write_combined_audio(self, audio_buffers, sample_rate):
        """Write combined audio to file."""
        wav_file = "test_output.wav"
        with wave.open(wav_file, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for buffer in audio_buffers:
                wav.writeframes(buffer)
        return wav_file

    def _play_audio_file(self, wav_file, device_index):
        """Play audio file."""
        wf = wave.open(wav_file, "rb")
        stream = self.p.open(
            format=self.p.get_format_from_width(wf.getsampwidth()),
            channels=wf.getnchannels(),
            rate=wf.getframerate(),
            output=True,
            output_device_index=device_index,
        )

        time.sleep(1.0)

        data = wf.readframes(1024)
        while data and not self.playback_done:
            stream.write(data)
            data = wf.readframes(1024)

        stream.stop_stream()
        stream.close()
        wf.close()

        time.sleep(2.0)

    def play_audio(self, text, device_index, server_ready_event=None):
        try:
            if not self._check_piper_model_exists():
                self.signals.playback_finished.emit()
                if server_ready_event is not None:
                    server_ready_event.set()
                return

            voice = self._load_piper_voice()

            result = self._synthesize_audio_lines(voice, text)
            if result is None:
                self.signals.playback_finished.emit()
                if server_ready_event is not None:
                    server_ready_event.set()
                return

            audio_buffers, sample_rate = result
            wav_file = self._write_combined_audio(audio_buffers, sample_rate)

            if server_ready_event is not None:
                self.signals.log_message.emit(
                    "Waiting for transcription server to be ready before playback..."
                )
                server_ready_event.wait()

            self.signals.log_message.emit("Audio synthesized. Starting playback...")

            self._play_audio_file(wav_file, device_index)

        except Exception as e:
            self.signals.log_message.emit(f"Playback error: {e}")
        finally:
            self.signals.playback_finished.emit()

    def _initialize_whisperlive_client(self, max_retries=3, retry_delay=2):
        """Initialize WhisperLive client with retry logic."""
        self.signals.log_message.emit("Initializing WhisperLive client...")

        for attempt in range(max_retries):
            try:
                self.transcription_client = WhisperLiveTranscriptionClient(
                    host="localhost",
                    port=9090,
                    lang=self.selected_whisper_lang,
                    model="large-v3",
                    use_vad=True,
                    mute_audio_playback=True,
                    enable_translation=False,
                    display_segments=1,
                    send_last_n_segments=3,
                    transcription_callback=self.on_transcription_result,
                    no_speech_thresh=0.9,
                    clip_audio=False,
                    same_output_threshold=5,
                )
                return True, None
            except Exception as e:
                error_msg = f"Error initializing WhisperLive client (attempt {attempt + 1}): {e}"
                self.signals.log_message.emit(error_msg)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    return (
                        False,
                        "Failed to initialize WhisperLive client after multiple attempts.",
                    )

        return False, "Failed to initialize WhisperLive client."

    def _wait_for_client_ready(self, client, timeout=15):
        """Wait for WhisperLive client to be ready."""
        self.signals.log_message.emit("Waiting for WhisperLive server to be ready...")
        start_time = time.time()

        while not client.recording:
            if client.server_error:
                error_msg = getattr(client, "error_message", "Unknown error")
                self.signals.log_message.emit(f"WhisperLive server error: {error_msg}")
                try:
                    client.close_websocket()
                except Exception:
                    pass
                return False, "Server error"

            if client.waiting:
                self.signals.log_message.emit(
                    "WhisperLive server is full. Waiting for slot..."
                )

            if time.time() - start_time > timeout:
                self.signals.log_message.emit(
                    "Timeout waiting for WhisperLive server to be ready."
                )
                try:
                    client.close_websocket()
                except Exception:
                    pass
                return False, "Timeout"

            time.sleep(0.1)

        return True, None

    def _connect_to_whisperlive_server(self, max_retries=3, retry_delay=2):
        """Connect to WhisperLive server with retry logic."""
        for attempt in range(max_retries):
            success, error = self._initialize_whisperlive_client(
                max_retries, retry_delay
            )
            if not success:
                if attempt < max_retries - 1:
                    self.signals.log_message.emit(
                        f"Connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    self.signals.log_message.emit(error)
                    return False
                continue

            client = self.transcription_client.client
            success, error = self._wait_for_client_ready(client)

            if success:
                self.signals.log_message.emit(
                    "WhisperLive server ready. Starting streaming..."
                )
                return True
            else:
                if attempt < max_retries - 1:
                    self.signals.log_message.emit(
                        f"Connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds..."
                    )
                    time.sleep(retry_delay)
                else:
                    self.signals.log_message.emit(error)
                    return False

        return False

    def _setup_audio_stream(self, source):
        """Setup audio stream and resampling."""
        stream = source.stream
        source_sample_rate = source.SAMPLE_RATE
        target_sample_rate = 16000

        self.signals.log_message.emit(
            f"Microphone sample rate: {source_sample_rate} Hz, Target: {target_sample_rate} Hz"
        )

        if source_sample_rate != target_sample_rate:
            resampler = resampy.resample
            self.signals.log_message.emit(
                f"Resampling audio from {source_sample_rate} Hz to {target_sample_rate} Hz"
            )
        else:
            resampler = None

        return stream, source_sample_rate, target_sample_rate, resampler

    def _stream_audio_to_whisperlive(
        self, stream, source, source_sample_rate, target_sample_rate, resampler, client
    ):
        """Stream audio to WhisperLive."""
        while not self.playback_done:
            try:
                data = stream.read(source.CHUNK)
                self.audio_frames.append(data)
                self._update_volume_from_audio(data)

                audio_array = (
                    np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                )

                if resampler is not None:
                    audio_array = resampler(
                        audio_array, source_sample_rate, target_sample_rate
                    )

                client.send_packet_to_server(audio_array.tobytes())

            except Exception as e:
                self.signals.log_message.emit(f"Recording error: {e}")
                break

    def _send_end_of_audio_signal(self, client):
        """Send END_OF_AUDIO signal to WhisperLive."""
        self.signals.log_message.emit("Recording stopped. Sending END_OF_AUDIO...")
        try:
            client.send_packet_to_server("END_OF_AUDIO".encode("utf-8"))
        except Exception as e:
            self.signals.log_message.emit(f"Error sending END_OF_AUDIO: {e}")

    def record_audio_to_file(self, device_index, server_ready_event=None):
        """Records audio from microphone and streams it directly to WhisperLive."""
        device_name = self.p.get_device_info_by_index(device_index).get(
            "name", self.UNKNOWN_DEVICE_NAME
        )
        try:
            self.signals.log_message.emit(
                f"Starting recording on {device_name} for transcription..."
            )

            if not self._connect_to_whisperlive_server():
                if server_ready_event is not None:
                    server_ready_event.set()
                return

            if server_ready_event is not None:
                server_ready_event.set()

            client = self.transcription_client.client

            with sr.Microphone(device_index=device_index) as source:
                stream, source_sample_rate, target_sample_rate, resampler = (
                    self._setup_audio_stream(source)
                )

                self._stream_audio_to_whisperlive(
                    stream, source, source_sample_rate, target_sample_rate, resampler, client
                )

            self._send_end_of_audio_signal(client)

            self.signals.log_message.emit("Waiting for final transcription results...")
            time.sleep(2)

            self.signals.update_volume.emit(0)

        except Exception as e:
            self.signals.log_message.emit(f"Recording thread error: {e}")

    def run_transcription(self):
        """Run transcription test using streaming audio (no file needed)."""
        try:
            # Transcription is now done during recording via streaming
            # This method is called after recording is complete
            self.signals.log_message.emit("Transcription streaming complete.")

            self._compare_transcription_results()

        except Exception as e:
            self.signals.log_message.emit(f"Transcription error: {e}")
        finally:
            self._cleanup_transcription()

    def _normalize_text(self, text):
        """Normalize text by converting to lowercase, removing punctuation, and collapsing whitespace."""
        text = text.lower()
        # Remove punctuation
        text = text.translate(str.maketrans("", "", string.punctuation))
        # Collapse whitespace
        text = " ".join(text.split())
        return text

    def _compare_transcription_results(self):
        """Compare transcription results with original text."""
        original_text = self.speak_text.toPlainText()
        transcribed_text = self.transcription_text

        # Normalize line breaks for comparison
        original_normalized = self._normalize_text(original_text)
        transcribed_normalized = self._normalize_text(transcribed_text)

        self.signals.log_message.emit(f"Original text: '{original_text}'")
        self.signals.log_message.emit(f"Transcribed text: '{transcribed_text}'")

        # Check for empty transcription first
        if not transcribed_text.strip():
            self.signals.log_message.emit(
                "Result: FAILURE - No transcription received."
            )
            return

        match_ratio = difflib.SequenceMatcher(
            None, original_normalized, transcribed_normalized
        ).ratio()

        # Check for exact match (normalized)
        if (
            transcribed_normalized in original_normalized
            or original_normalized in transcribed_normalized
            or match_ratio >= 0.8
        ):
            self.signals.log_message.emit(
                "Result: SUCCESS - Transcribed text matches original."
            )
        else:
            # Check for partial match
            words_original = set(original_normalized.split())
            words_transcribed = set(transcribed_normalized.split())
            common_words = words_original & words_transcribed

            if len(common_words) > 0:
                match_ratio_words = len(common_words) / max(
                    len(words_original), len(words_transcribed)
                )
                self.signals.log_message.emit(
                    f"Result: PARTIAL MATCH - {match_ratio_words:.1%} of words match."
                )
            else:
                self.signals.log_message.emit("Result: FAILURE - Texts do not match.")

    def _cleanup_transcription(self):
        """Clean up transcription resources."""
        self.signals.update_volume.emit(0)
        self.is_transcribing = False

        # Close WhisperLive client if it exists
        if self.transcription_client is not None:
            try:
                self.transcription_client.client.close_websocket()
                self.signals.log_message.emit("WhisperLive client closed.")
            except Exception as e:
                self.signals.log_message.emit(f"Error closing WhisperLive client: {e}")
            finally:
                self.transcription_client = None

        self._enable_buttons()
        self.signals.transcription_finished.emit()

    def on_transcription_result(self, _, segments):
        """Handle real-time transcription results."""
        logging.debug(f"Transcription callback received: segments={segments}")
        new_text = ""
        for segment in segments:
            if new_text:
                new_text += "\n"
            new_text += segment["text"]

        self.transcription_text = new_text
        self.signals.append_heard.emit(new_text)
        self.signals.log_message.emit(f"Transcribed: '{new_text}'")

    def monitor_mic_volume(self, device_index):
        """Monitors microphone volume without recording or transcribing."""
        device_name = self.p.get_device_info_by_index(device_index).get(
            "name", self.UNKNOWN_DEVICE_NAME
        )
        try:
            self.signals.log_message.emit(
                f"Starting microphone monitoring on {device_name}..."
            )
            with sr.Microphone(device_index=device_index) as source:
                stream = source.stream
                while not self.playback_done:
                    try:
                        data = stream.read(source.CHUNK)
                        self._update_volume_from_audio(data)
                    except Exception:
                        break
            self.signals.update_volume.emit(0)
        except Exception as e:
            self.signals.log_message.emit(f"Microphone monitoring error: {e}")

    def record_audio(self, device_index):
        device_name = self.p.get_device_info_by_index(device_index).get(
            "name", self.UNKNOWN_DEVICE_NAME
        )
        try:
            r = sr.Recognizer()
            self.signals.log_message.emit(f"Starting recording on {device_name}...")

            with sr.Microphone(device_index=device_index) as source:
                stream = source.stream

                while not self.playback_done:
                    try:
                        data = stream.read(source.CHUNK)
                        self.audio_frames.append(data)
                        self._update_volume_from_audio(data)

                    except Exception as e:
                        self.signals.log_message.emit(f"Recording error: {e}")
                        break

            self.signals.log_message.emit(
                "Recording stopped. Processing speech recognition..."
            )
            self.signals.update_volume.emit(0)

            if self.audio_frames:
                self._process_google_recognition(r, source)

        except Exception as e:
            self.signals.log_message.emit(f"Recording thread error: {e}")
        finally:
            self._cleanup_recording()

    def _update_volume_from_audio(self, data):
        """Calculate and update volume from audio data."""
        audio_data = np.frombuffer(data, dtype=np.int16)
        if len(audio_data) > 0:
            # Use max() instead of mean() for much better responsiveness
            vol = np.abs(audio_data.astype(np.float32)).max()
            # Max amplitude is 32768, scale logarithmically or with a smaller multiplier
            scaled_vol = min(100, int((vol / 32768.0) * 200))
            self.signals.update_volume.emit(scaled_vol)

    def _process_google_recognition(self, recognizer, source):
        """Process audio with Google Speech Recognition."""
        audio_data = sr.AudioData(
            b"".join(self.audio_frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH
        )
        try:
            recognized_text = recognizer.recognize_google(
                audio_data, language=self.selected_google_locale
            )  # type: ignore[attr-defined]
            self.signals.update_heard.emit(recognized_text)
            self.signals.log_message.emit("Recognition successful.")

            original_text = self.speak_text.toPlainText()

            original_normalized = self._normalize_text(original_text)
            recognized_normalized = self._normalize_text(recognized_text)

            match_ratio = difflib.SequenceMatcher(
                None, original_normalized, recognized_normalized
            ).ratio()

            # Check for empty recognition first
            if not recognized_normalized.strip():
                self.signals.log_message.emit(
                    "Result: FAILURE - No recognition received."
                )
            elif (
                recognized_normalized in original_normalized
                or original_normalized in recognized_normalized
                or match_ratio >= 0.8
            ):
                self.signals.log_message.emit(
                    "Result: SUCCESS - Recognized text matches original."
                )
            else:
                self.signals.log_message.emit(
                    "Result: FAILURE - Texts do not match closely."
                )

        except sr.UnknownValueError:
            self.signals.log_message.emit(
                "Speech Recognition could not understand audio."
            )
        except sr.RequestError as e:
            self.signals.log_message.emit(f"Could not request results; {e}")

    def _cleanup_recording(self):
        """Clean up recording resources."""
        self.is_recording = False
        self._enable_buttons()

    def closeEvent(self, event):
        self.p.terminate()

        # Clean up WhisperLive process if it was started by this app
        if self.whisperlive_process is not None:
            try:
                self.log("Stopping WhisperLive service...")
                self.whisperlive_process.terminate()
                self.whisperlive_process.wait(timeout=5)
                self.log("WhisperLive service stopped.")
            except Exception as e:
                print(f"Error stopping WhisperLive service: {e}")

        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SoundTestApp()
    window.show()
    sys.exit(app.exec())
