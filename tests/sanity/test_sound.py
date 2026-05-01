import json
import logging
import os
import sys
import threading
import wave
import time

import numpy as np
import pyaudio
import speech_recognition as sr

# Configure basic logging
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

from PyQt6.QtWidgets import (
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
from PyQt6.QtCore import pyqtSignal, QObject
import websocket
import uuid


class WorkerSignals(QObject):
    update_volume = pyqtSignal(int)
    update_heard = pyqtSignal(str)
    append_heard = pyqtSignal(str)
    playback_finished = pyqtSignal()
    record_finished = pyqtSignal()
    transcription_finished = pyqtSignal()
    log_message = pyqtSignal(str)


class TranscriptionClient:
    """Client for real-time transcription using WhisperLive server."""

    END_OF_AUDIO = "END_OF_AUDIO"

    def __init__(
        self,
        host="localhost",
        port=9090,
        lang=None,
        model="small",
        use_vad=True,
        transcription_callback=None,
    ):
        self.host = host
        self.port = port
        self.lang = lang
        self.model = model
        self.use_vad = use_vad
        self.transcription_callback = transcription_callback

        self.recording = False
        self.uid = str(uuid.uuid4())
        self.waiting = False
        self.server_error = False
        self.last_response_received = None
        self.disconnect_if_no_response_for = 15
        self.transcript = []
        self.last_segment = None

        socket_url = f"ws://{host}:{port}"
        self.client_socket = websocket.WebSocketApp(
            socket_url,
            on_open=lambda ws: self.on_open(ws),
            on_message=lambda ws, message: self.on_message(ws, message),
            on_error=lambda ws, error: self.on_error(ws, error),
            on_close=lambda ws, close_status_code, close_msg: self.on_close(
                ws, close_status_code, close_msg
            ),
        )

        # Start websocket client in a thread
        self.ws_thread = threading.Thread(target=self.client_socket.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()

    def on_open(self, ws):
        """Send configuration message when connection opens."""
        print("[INFO]: Opened connection")
        ws.send(
            json.dumps(
                {
                    "uid": self.uid,
                    "language": self.lang,
                    "task": "transcribe",
                    "model": self.model,
                    "use_vad": self.use_vad,
                }
            )
        )

    def on_message(self, ws, message):
        """Handle incoming messages from server."""
        message = json.loads(message)

        if self.uid != message.get("uid"):
            return

        if "status" in message.keys():
            status = message["status"]
            if status == "WAIT":
                self.waiting = True
                print(
                    f"[INFO]: Server is full. Estimated wait time {round(message['message'])} minutes."
                )
            elif status == "ERROR":
                print(f"Message from Server: {message['message']}")
                self.server_error = True
            elif status == "WARNING":
                print(f"Message from Server: {message['message']}")
            return

        if "message" in message.keys() and message["message"] == "DISCONNECT":
            print("[INFO]: Server disconnected due to overtime.")
            self.recording = False

        if "message" in message.keys() and message["message"] == "SERVER_READY":
            self.last_response_received = time.time()
            self.recording = True
            print("[INFO]: Server Ready!")
            return

        if "segments" in message.keys():
            self.process_segments(message["segments"])

    def process_segments(self, segments):
        """Process transcript segments and call callback."""
        text = []
        for i, seg in enumerate(segments):
            if not text or text[-1] != seg["text"]:
                text.append(seg["text"].strip())
                if i == len(segments) - 1 and not seg.get("completed", False):
                    self.last_segment = seg
                elif seg.get("completed", False):
                    if not self.transcript or float(seg["start"]) >= float(
                        self.transcript[-1]["end"]
                    ):
                        self.transcript.append(seg)

        # Update last response time
        if (
            self.last_received_segment is None
            or self.last_received_segment != segments[-1]["text"]
        ):
            self.last_response_received = time.time()
            self.last_received_segment = segments[-1]["text"]

        # Call transcription callback
        if self.transcription_callback and callable(self.transcription_callback):
            try:
                self.transcription_callback(" ".join(text), segments)
            except Exception as e:
                print(f"[WARN] transcription_callback raised: {e}")

    def on_error(self, ws, error):
        print(f"[ERROR] WebSocket Error: {error}")
        self.server_error = True

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[INFO]: Websocket connection closed: {close_status_code}: {close_msg}")
        self.recording = False
        self.waiting = False

    def send_packet(self, message):
        """Send audio packet to server."""
        try:
            self.client_socket.send(message, websocket.ABNF.OPCODE_BINARY)
        except Exception as e:
            print(f"[ERROR] Failed to send packet: {e}")

    def close(self):
        """Close WebSocket connection."""
        try:
            self.client_socket.close()
        except Exception as e:
            print(f"[ERROR] Error closing WebSocket: {e}")

        try:
            self.ws_thread.join(timeout=2)
        except Exception as e:
            print(f"[ERROR] Error joining WebSocket thread: {e}")

    def wait_before_disconnect(self):
        """Wait before disconnecting to process pending responses."""
        if self.last_response_received:
            while (
                time.time() - self.last_response_received
                < self.disconnect_if_no_response_for
            ):
                time.sleep(0.1)


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
        self.speak_text.setText("this is a test of the audio system")
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
        current_text = self.heard_text.toPlainText()
        if current_text:
            self.heard_text.setText(current_text + " " + text)
        else:
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

        in_idx = self.in_combo.currentData()

        if in_idx is None:
            self.log("Please select an input device.")
            self.recording_btn.setEnabled(True)
            self.transcription_btn.setEnabled(True)
            return

        self.save_settings(self.out_combo.currentData(), in_idx)

        self.is_transcribing = True
        self.transcription_text = ""

        # Start transcription in background thread
        threading.Thread(
            target=self.run_transcription, args=(in_idx,), daemon=True
        ).start()

    def play_audio(self, text, device_index):
        try:
            from piper import PiperVoice

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

            wav_file = "test_output.wav"
            with wave.open(wav_file, "wb") as wav:
                voice.synthesize_wav(text, wav)

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

    def run_transcription(self, device_index):
        """Run real-time transcription test."""
        try:
            self.signals.log_message.emit("Initializing transcription client...")

            # Create transcription client
            self.transcription_client = TranscriptionClient(
                host="localhost",
                port=9090,
                lang="en",
                model="small",
                use_vad=True,
                transcription_callback=self.on_transcription_result,
            )

            # Wait for server to be ready
            self.signals.log_message.emit("Waiting for transcription server...")
            timeout = 30  # 30 seconds timeout
            start_time = time.time()

            while not self.transcription_client.recording:
                if (
                    self.transcription_client.waiting
                    or self.transcription_client.server_error
                ):
                    self.signals.log_message.emit(
                        "Failed to connect to transcription server."
                    )
                    self.signals.transcription_finished.emit()
                    return

                if time.time() - start_time > timeout:
                    self.signals.log_message.emit(
                        "Timeout waiting for transcription server."
                    )
                    self.signals.transcription_finished.emit()
                    return

                time.sleep(0.1)

            self.signals.log_message.emit(
                "Transcription server ready. Starting recording..."
            )

            # Start recording and streaming
            chunk = 4096
            format = pyaudio.paInt16
            channels = 1
            rate = 16000

            stream = self.p.open(
                format=format,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk,
            )

            self.signals.log_message.emit("Recording... Speak now.")
            self.signals.log_message.emit("Press Ctrl+C in terminal to stop early.")

            # Record for 30 seconds or until stopped
            record_duration = 30
            start_time = time.time()

            while self.is_transcribing and (time.time() - start_time) < record_duration:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                    self.audio_frames.append(data)

                    # Calculate volume
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    if len(audio_data) > 0:
                        vol = np.abs(audio_data).mean()
                        scaled_vol = min(100, int((vol / 32768.0) * 500))
                        self.signals.update_volume.emit(scaled_vol)

                    # Convert to float and send to server
                    audio_array = (
                        np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    )
                    self.transcription_client.send_packet(audio_array.tobytes())

                except Exception as e:
                    self.signals.log_message.emit(f"Recording error: {e}")
                    break

            stream.stop_stream()
            stream.close()

            # Send end of audio signal
            self.transcription_client.send_packet(
                TranscriptionClient.END_OF_AUDIO.encode("utf-8")
            )

            # Wait for final transcription
            self.signals.log_message.emit("Processing final transcription...")
            self.transcription_client.wait_before_disconnect()

            # Close client
            self.transcription_client.close()

            # Compare transcription with original text
            original_text = self.speak_text.toPlainText().lower()
            transcribed_text = self.transcription_text.lower()

            self.signals.log_message.emit(f"Original text: '{original_text}'")
            self.signals.log_message.emit(f"Transcribed text: '{transcribed_text}'")

            if transcribed_text in original_text or original_text in transcribed_text:
                self.signals.log_message.emit(
                    "Result: SUCCESS - Transcribed text matches original."
                )
            else:
                # Check for partial match
                words_original = set(original_text.split())
                words_transcribed = set(transcribed_text.split())
                common_words = words_original & words_transcribed

                if len(common_words) > 0:
                    match_ratio = len(common_words) / max(
                        len(words_original), len(words_transcribed)
                    )
                    self.signals.log_message.emit(
                        f"Result: PARTIAL MATCH - {match_ratio:.1%} of words match."
                    )
                else:
                    self.signals.log_message.emit(
                        "Result: FAILURE - Texts do not match."
                    )

        except Exception as e:
            self.signals.log_message.emit(f"Transcription error: {e}")
        finally:
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

    def on_transcription_result(self, text, segments):
        """Handle real-time transcription results."""
        if text and text != self.transcription_text:
            self.transcription_text = text
            self.signals.append_heard.emit(text)
            self.signals.log_message.emit(f"Transcribed: '{text}'")

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

                        # Calculate volume
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        if len(audio_data) > 0:
                            vol = np.abs(audio_data).mean()
                            # Scale volume to 0-100 (rough estimate)
                            scaled_vol = min(100, int((vol / 32768.0) * 500))
                            self.signals.update_volume.emit(scaled_vol)

                    except Exception as e:
                        self.signals.log_message.emit(f"Recording error: {e}")
                        break

            self.signals.log_message.emit(
                "Recording stopped. Processing speech recognition..."
            )
            self.signals.update_volume.emit(0)

            if self.audio_frames:
                audio_data = sr.AudioData(
                    b"".join(self.audio_frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH
                )
                try:
                    recognized_text = r.recognize_google(audio_data)  # type: ignore[attr-defined]
                    self.signals.update_heard.emit(recognized_text)
                    self.signals.log_message.emit("Recognition successful.")

                    original_text = self.speak_text.toPlainText().lower()
                    # Perform a simple check if the recognized text resembles the original
                    if (
                        recognized_text.lower() in original_text
                        or original_text in recognized_text.lower()
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

        except Exception as e:
            self.signals.log_message.emit(f"Recording thread error: {e}")
        finally:
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
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SoundTestApp()
    window.show()
    sys.exit(app.exec())
