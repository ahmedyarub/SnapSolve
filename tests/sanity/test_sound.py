import json
import logging
import os
import subprocess
import sys
import threading
import time
import wave

import numpy as np
import pyaudio
import speech_recognition as sr

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

        # Start the server in a subprocess with extended connection time
        process = subprocess.Popen(
            [
                sys.executable,
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
        self.signals.playback_finished.connect(self.on_playback_finished)
        self.signals.transcription_finished.connect(self.on_transcription_finished)
        self.signals.log_message.connect(self.log)

        # Hardcoded model
        self.piper_model = "en_US-lessac-high.onnx"
        self.settings_file = "sound_test_settings.json"

        self.is_recording = False
        self.is_transcribing = False
        self.playback_done = False
        self.audio_frames = []
        self.transcription_client = None
        self.transcription_text = ""
        self.whisperlive_process = None

        # UI components (initialized in init_ui)
        self.out_combo = QComboBox()
        self.in_combo = QComboBox()
        self.speak_text = QTextEdit()
        self.heard_text = QTextEdit()
        self.volume_bar = QProgressBar()
        self.log_text = QTextEdit()
        self.recording_btn = QPushButton()
        self.transcription_btn = QPushButton()

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

        self.populate_devices()
        self.load_settings()

        # Text to Speak
        layout.addWidget(QLabel("Text to Speak:"))
        self.speak_text.setText(
            "this is a test of the audio system\nand this is a second line"
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
        self.recording_btn = QPushButton("Recording Test")
        self.recording_btn.clicked.connect(self.start_recording_test)
        button_layout.addWidget(self.recording_btn)

        self.transcription_btn = QPushButton("Transcription Test")
        self.transcription_btn.clicked.connect(self.start_transcription_test)
        button_layout.addWidget(self.transcription_btn)

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

    def load_settings(self):
        logging.debug("Attempting to load last selected devices...")
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
                    last_out = settings.get("last_out_index")
                    last_in = settings.get("last_in_index")

                    if last_out is not None:
                        idx = self.out_combo.findData(last_out)
                        if idx >= 0:
                            self.out_combo.setCurrentIndex(idx)

                    if last_in is not None:
                        idx = self.in_combo.findData(last_in)
                        if idx >= 0:
                            self.in_combo.setCurrentIndex(idx)
                logging.debug("Settings loaded successfully.")
            except Exception as e:
                logging.error(f"Failed to load settings: {e}")

    def save_settings(self, out_idx, in_idx):
        logging.debug("Saving last selected devices...")
        try:
            with open(self.settings_file, "w") as f:
                json.dump({"last_out_index": out_idx, "last_in_index": in_idx}, f)
            logging.debug("Settings saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save settings: {e}")

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

    def on_playback_finished(self):
        self.playback_done = True
        self.log("Playback finished. Stopping recording...")

    def on_transcription_finished(self):
        self.is_transcribing = False
        self.log("Transcription finished.")

    def start_recording_test(self):
        self.recording_btn.setEnabled(False)
        self.transcription_btn.setEnabled(False)
        self.log_text.clear()
        self.heard_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log("Please select both input and output devices.")
            self.recording_btn.setEnabled(True)
            self.transcription_btn.setEnabled(True)
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
        self.recording_btn.setEnabled(False)
        self.transcription_btn.setEnabled(False)
        self.log_text.clear()
        self.heard_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log("Please select both input and output devices.")
            self.recording_btn.setEnabled(True)
            self.transcription_btn.setEnabled(True)
            return

        self.save_settings(out_idx, in_idx)

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
                    self.recording_btn.setEnabled(True)
                    self.transcription_btn.setEnabled(True)
                    return

            # Wait a bit more for the service to be fully ready
            self.log("Waiting for WhisperLive service to be ready...")
            time.sleep(2)
        else:
            self.log("WhisperLive service is running. Proceeding with test.")

        self.playback_done = False
        self.is_transcribing = True
        self.audio_frames = []
        self.transcription_text = ""

        # Run playback and record in separate background threads
        threading.Thread(
            target=self.play_audio, args=(text, out_idx), daemon=True
        ).start()

        # We need to record and save it to a file, then pass it to run_transcription
        def record_and_transcribe():
            self.record_audio_to_file(in_idx)
            self.run_transcription()

        threading.Thread(target=record_and_transcribe, daemon=True).start()

    def play_audio(self, text, device_index):
        try:
            from piper import PiperVoice
            import io

            if not os.path.exists(self.piper_model):
                self.signals.log_message.emit(
                    f"Piper model not found at {self.piper_model}"
                )
                self.signals.playback_finished.emit()
                return

            piper_config_path = self.piper_model + ".json"
            if not os.path.exists(piper_config_path):
                self.signals.log_message.emit(
                    f"Piper config not found at {piper_config_path}"
                )
                self.signals.playback_finished.emit()
                return

            self.signals.log_message.emit("Loading Piper voice model...")
            voice = PiperVoice.load(self.piper_model, config_path=piper_config_path)

            # Split text by newlines and synthesize each line separately
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if not lines:
                self.signals.playback_finished.emit()
                return

            # Synthesize each line to a buffer and combine with silence
            audio_buffers = []
            sample_rate = voice.config.sample_rate

            for i, line in enumerate(lines):
                # Synthesize line to a buffer
                line_buffer = io.BytesIO()
                with wave.open(line_buffer, "wb") as wav:
                    voice.synthesize_wav(line, wav)
                line_buffer.seek(0)

                # Read the WAV data
                with wave.open(line_buffer, "rb") as wav:
                    frames = wav.readframes(wav.getnframes())
                    audio_buffers.append(frames)

                # Add 2 seconds of silence between lines (except after last line)
                if i < len(lines) - 1:
                    silence_samples = int(2 * sample_rate)
                    silence = np.zeros(silence_samples, dtype=np.int16)
                    audio_buffers.append(silence.tobytes())

            # Write combined audio to file
            wav_file = "test_output.wav"
            with wave.open(wav_file, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)
                for buffer in audio_buffers:
                    wav.writeframes(buffer)

            self.signals.log_message.emit("Audio synthesized. Starting playback...")

            wf = wave.open(wav_file, "rb")
            stream = self.p.open(
                format=self.p.get_format_from_width(wf.getsampwidth()),
                channels=wf.getnchannels(),
                rate=wf.getframerate(),
                output=True,
                output_device_index=device_index,
            )

            data = wf.readframes(1024)
            while data and not self.playback_done:
                stream.write(data)
                data = wf.readframes(1024)

            stream.stop_stream()
            stream.close()
            wf.close()

        except Exception as e:
            self.signals.log_message.emit(f"Playback error: {e}")
        finally:
            self.signals.playback_finished.emit()

    def record_audio_to_file(self, device_index):
        """Records audio from microphone until playback is done and saves to a file."""
        try:
            self.signals.log_message.emit(
                f"Starting recording on device {device_index} for transcription..."
            )

            audio_data = None
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

                audio_data = sr.AudioData(
                    b"".join(self.audio_frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH
                )

            self.signals.log_message.emit(
                "Recording stopped. Saving intermediate file..."
            )
            self.signals.update_volume.emit(0)

            if audio_data:
                wav_data = audio_data.get_wav_data()
                temp_file = os.path.join(
                    str(os.path.dirname(__file__)), "..", "..", "temp_transcription.wav"
                )
                with open(temp_file, "wb") as f:
                    f.write(wav_data)
                self.signals.log_message.emit(f"Saved audio to {temp_file}")

        except Exception as e:
            self.signals.log_message.emit(f"Recording thread error: {e}")

    def run_transcription(self):
        """Run transcription test using a pre-recorded audio file."""
        try:
            self.signals.log_message.emit("Initializing transcription client...")

            # Create WhisperLive client
            self.transcription_client = WhisperLiveTranscriptionClient(
                host="localhost",
                port=9090,
                lang="en",
                model="large-v3",
                use_vad=True,
                mute_audio_playback=True,
                enable_translation=False,
                display_segments=1,
                send_last_n_segments=3,
                transcription_callback=self.on_transcription_result,
            )

            audio_file = os.path.join(
                str(os.path.dirname(__file__)), "..", "..", "temp_transcription.wav"
            )

            if not os.path.exists(audio_file):
                self.signals.log_message.emit(
                    f"Could not find test audio file at {audio_file}"
                )
                return

            self.signals.log_message.emit(f"Starting transcription of {audio_file}...")
            self.transcription_client(audio_file)

            self._compare_transcription_results()

        except Exception as e:
            self.signals.log_message.emit(f"Transcription error: {e}")
        finally:
            self._cleanup_transcription()

    def _compare_transcription_results(self):
        """Compare transcription results with original text."""
        original_text = self.speak_text.toPlainText().lower()
        transcribed_text = self.transcription_text.lower().replace(".", "").strip()

        # Normalize line breaks for comparison
        original_normalized = " ".join(original_text.split())
        transcribed_normalized = " ".join(transcribed_text.split())

        self.signals.log_message.emit(f"Original text: '{original_text}'")
        self.signals.log_message.emit(f"Transcribed text: '{transcribed_text}'")

        # Check for empty transcription first
        if not transcribed_text.strip():
            self.signals.log_message.emit(
                "Result: FAILURE - No transcription received."
            )
            return

        # Check for exact match (normalized)
        if (
            transcribed_normalized in original_normalized
            or original_normalized in transcribed_normalized
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
                match_ratio = len(common_words) / max(
                    len(words_original), len(words_transcribed)
                )
                self.signals.log_message.emit(
                    f"Result: PARTIAL MATCH - {match_ratio:.1%} of words match."
                )
            else:
                self.signals.log_message.emit("Result: FAILURE - Texts do not match.")

    def _cleanup_transcription(self):
        """Clean up transcription resources."""
        self.signals.update_volume.emit(0)
        self.is_transcribing = False
        import PyQt6.QtCore as QtCore

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

    def record_audio(self, device_index):
        try:
            r = sr.Recognizer()
            self.signals.log_message.emit(
                f"Starting recording on device {device_index}..."
            )

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
            vol = np.abs(audio_data).mean()
            scaled_vol = min(100, int((vol / 32768.0) * 500))
            self.signals.update_volume.emit(scaled_vol)

    def _process_google_recognition(self, recognizer, source):
        """Process audio with Google Speech Recognition."""
        audio_data = sr.AudioData(
            b"".join(self.audio_frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH
        )
        try:
            recognized_text = recognizer.recognize_google(audio_data)  # type: ignore[attr-defined]
            self.signals.update_heard.emit(recognized_text)
            self.signals.log_message.emit("Recognition successful.")

            original_text = self.speak_text.toPlainText().lower().replace("\n", " ")
            recognized_lower = recognized_text.lower()

            # Check for empty recognition first
            if not recognized_lower.strip():
                self.signals.log_message.emit(
                    "Result: FAILURE - No recognition received."
                )
            elif recognized_lower in original_text or original_text in recognized_lower:
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
        import PyQt6.QtCore as QtCore

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
