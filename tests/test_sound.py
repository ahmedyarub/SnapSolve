import json
import logging
import os
import sys
import threading
import wave

import numpy as np
import pyaudio
import speech_recognition as sr

# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QTextEdit,
                             QPushButton, QProgressBar)
from PyQt6.QtCore import pyqtSignal, QObject


class WorkerSignals(QObject):
    update_volume = pyqtSignal(int)
    update_heard = pyqtSignal(str)
    playback_finished = pyqtSignal()
    record_finished = pyqtSignal()
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
        self.signals.playback_finished.connect(self.on_playback_finished)
        self.signals.log_message.connect(self.log)

        # Hardcoded model
        self.piper_model = 'en_US-lessac-high.onnx'
        self.settings_file = 'sound_test_settings.json'

        self.is_recording = False
        self.playback_done = False
        self.audio_frames = []

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Output Device
        out_layout = QHBoxLayout()
        out_layout.addWidget(QLabel("Output Device:"))
        self.out_combo = QComboBox()
        out_layout.addWidget(self.out_combo)
        layout.addLayout(out_layout)

        # Input Device
        in_layout = QHBoxLayout()
        in_layout.addWidget(QLabel("Input Device:"))
        self.in_combo = QComboBox()
        in_layout.addWidget(self.in_combo)
        layout.addLayout(in_layout)

        self.populate_devices()
        self.load_settings()

        # Text to Speak
        layout.addWidget(QLabel("Text to Speak:"))
        self.speak_text = QTextEdit()
        self.speak_text.setText("this is a test of the audio system")
        self.speak_text.setMaximumHeight(80)
        layout.addWidget(self.speak_text)

        # Text Heard
        layout.addWidget(QLabel("Text Heard:"))
        self.heard_text = QTextEdit()
        self.heard_text.setReadOnly(True)
        self.heard_text.setMaximumHeight(80)
        layout.addWidget(self.heard_text)

        # Volume Progress Bar
        layout.addWidget(QLabel("Microphone Volume:"))
        self.volume_bar = QProgressBar()
        self.volume_bar.setRange(0, 100)
        self.volume_bar.setValue(0)
        layout.addWidget(self.volume_bar)

        # Log
        layout.addWidget(QLabel("Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        # Action Button
        self.action_btn = QPushButton("Start Test")
        self.action_btn.clicked.connect(self.start_test)
        layout.addWidget(self.action_btn)

    def populate_devices(self):
        count = self.p.get_device_count()
        logging.debug(f"Populating devices. Total devices found: {count}")
        for i in range(count):
            try:
                info = self.p.get_device_info_by_index(i)
                host_api = self.p.get_host_api_info_by_index(info['hostApi'])['name']
                name = info['name']
                desc = f"[{host_api}] {name} (Index: {i})"

                if info['maxOutputChannels'] > 0:
                    self.out_combo.addItem(desc, i)
                if info['maxInputChannels'] > 0:
                    self.in_combo.addItem(desc, i)
            except Exception as e:
                logging.warning(f"Failed to load device index {i}: {e}")

    def load_settings(self):
        logging.debug("Attempting to load last selected devices...")
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    last_out = settings.get('last_out_index')
                    last_in = settings.get('last_in_index')

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
            with open(self.settings_file, 'w') as f:
                json.dump({'last_out_index': out_idx, 'last_in_index': in_idx}, f)
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

    def on_playback_finished(self):
        self.playback_done = True
        self.log("Playback finished. Stopping recording...")

    def start_test(self):
        self.action_btn.setEnabled(False)
        self.log_text.clear()
        self.heard_text.clear()
        self.volume_bar.setValue(0)

        out_idx = self.out_combo.currentData()
        in_idx = self.in_combo.currentData()
        text = self.speak_text.toPlainText()

        if out_idx is None or in_idx is None:
            self.log("Please select both input and output devices.")
            self.action_btn.setEnabled(True)
            return

        self.save_settings(out_idx, in_idx)

        self.playback_done = False
        self.is_recording = True
        self.audio_frames = []

        # Run playback and record in separate background threads
        threading.Thread(target=self.play_audio, args=(text, out_idx), daemon=True).start()
        threading.Thread(target=self.record_audio, args=(in_idx,), daemon=True).start()

    def play_audio(self, text, device_index):
        try:
            from piper import PiperVoice

            if not os.path.exists(self.piper_model):
                self.signals.log_message.emit(f"Piper model not found at {self.piper_model}")
                self.signals.playback_finished.emit()
                return

            piper_config_path = self.piper_model + ".json"
            if not os.path.exists(piper_config_path):
                self.signals.log_message.emit(f"Piper config not found at {piper_config_path}")
                self.signals.playback_finished.emit()
                return

            self.signals.log_message.emit("Loading Piper voice model...")
            voice = PiperVoice.load(self.piper_model, config_path=piper_config_path)

            wav_file = "test_output.wav"
            with wave.open(wav_file, "wb") as wav:
                voice.synthesize_wav(text, wav)

            self.signals.log_message.emit("Audio synthesized. Starting playback...")

            wf = wave.open(wav_file, 'rb')
            stream = self.p.open(format=self.p.get_format_from_width(wf.getsampwidth()),
                                 channels=wf.getnchannels(),
                                 rate=wf.getframerate(),
                                 output=True,
                                 output_device_index=device_index)

            data = wf.readframes(1024)
            while data and not self.playback_done:
                stream.write(data)
                data = wf.readframes(1024)

            stream.stop_stream()
            stream.close()
            wf.close()

            if os.path.exists(wav_file):
                os.remove(wav_file)

        except Exception as e:
            self.signals.log_message.emit(f"Playback error: {e}")
        finally:
            self.signals.playback_finished.emit()

    def record_audio(self, device_index):
        try:
            r = sr.Recognizer()
            self.signals.log_message.emit(f"Starting recording on device {device_index}...")

            with sr.Microphone(device_index=device_index) as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
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

            self.signals.log_message.emit("Recording stopped. Processing speech recognition...")
            self.signals.update_volume.emit(0)

            if self.audio_frames:
                audio_data = sr.AudioData(b''.join(self.audio_frames), source.SAMPLE_RATE, source.SAMPLE_WIDTH)
                try:
                    recognized_text = r.recognize_google(audio_data)
                    self.signals.update_heard.emit(recognized_text)
                    self.signals.log_message.emit("Recognition successful.")

                    original_text = self.speak_text.toPlainText().lower()
                    # Perform a simple check if the recognized text resembles the original
                    if recognized_text.lower() in original_text or original_text in recognized_text.lower():
                        self.signals.log_message.emit("Result: SUCCESS - Recognized text matches original.")
                    else:
                        self.signals.log_message.emit("Result: FAILURE - Texts do not match closely.")

                except sr.UnknownValueError:
                    self.signals.log_message.emit("Speech Recognition could not understand audio.")
                except sr.RequestError as e:
                    self.signals.log_message.emit(f"Could not request results; {e}")

        except Exception as e:
            self.signals.log_message.emit(f"Recording thread error: {e}")
        finally:
            self.is_recording = False
            # Re-enable the button safely on the main thread via signals if possible,
            # but for simplicity we'll just re-enable it directly (Qt may warn, so let's emit a signal)
            # Actually, modifying GUI directly from a thread is unsafe in PyQt,
            # so let's use a lambda or QTimer, or better just use the main thread event loop.
            # We will use QMetaObject.invokeMethod.
            import PyQt6.QtCore as QtCore
            QtCore.QMetaObject.invokeMethod(self.action_btn, "setEnabled", QtCore.Qt.ConnectionType.QueuedConnection,
                                            QtCore.Q_ARG(bool, True))

    def closeEvent(self, event):
        self.p.terminate()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SoundTestApp()
    window.show()
    sys.exit(app.exec())
