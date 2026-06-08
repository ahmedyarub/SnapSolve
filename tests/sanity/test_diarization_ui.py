import sys
import os
import threading
import requests
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLineEdit, QTextEdit, QFileDialog, QLabel
)

class DiarizationTestUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diarization Sanity Test")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # Path input row
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        
        default_wav = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commercial_mono.wav")
        self.path_input.setText(default_wav)
        self.path_input.setPlaceholderText("Select a .wav file")
        
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse)
        
        path_layout.addWidget(QLabel("Session Dir:"))
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.browse_btn)
        
        layout.addLayout(path_layout)
        
        # Submit button
        self.submit_btn = QPushButton("Run Diarization")
        self.submit_btn.clicked.connect(self._run_diarization)
        layout.addWidget(self.submit_btn)
        
        # Results text box
        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        # Apply dark theme
        self.results_box.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, monospace;
            }
        """)
        layout.addWidget(self.results_box)
        
    def _browse(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Wav File", "", "Audio Files (*.wav)")
        if file_path:
            self.path_input.setText(file_path)
            
    def _run_diarization(self):
        wav_file = self.path_input.text().strip()
        if not wav_file or not os.path.isfile(wav_file):
            self.results_box.append("Error: Please select a valid .wav file.")
            return
            
        self.submit_btn.setEnabled(False)
        self.results_box.clear()
        self.results_box.append(f"Sending diarization request for: {wav_file}\n")
        
        def run_proc():
            try:
                # We send the selected wav file as audio_loopback to the service.
                with open(wav_file, "rb") as f:
                    files = {"audio_loopback": f}
                    data = {"speaker_name": "TestUser"}
                    
                    QMetaObject.invokeMethod(
                        self.results_box, 
                        "append", 
                        Qt.ConnectionType.QueuedConnection, 
                        Q_ARG(str, "Waiting for service response from http://127.0.0.1:8001/diarize...")
                    )
                    
                    response = requests.post("http://127.0.0.1:8001/diarize", files=files, data=data)
                    
                    if response.status_code == 200:
                        res_json = response.json()
                        segments = res_json.get("segments", [])
                        
                        QMetaObject.invokeMethod(
                            self.results_box, 
                            "append", 
                            Qt.ConnectionType.QueuedConnection, 
                            Q_ARG(str, "\n--- Final Transcription ---\n")
                        )
                        
                        for seg in segments:
                            QMetaObject.invokeMethod(
                                self.results_box, 
                                "append", 
                                Qt.ConnectionType.QueuedConnection, 
                                Q_ARG(str, f"[{seg['speaker']}] {seg['text']}")
                            )
                    else:
                        QMetaObject.invokeMethod(
                            self.results_box, 
                            "append", 
                            Qt.ConnectionType.QueuedConnection, 
                            Q_ARG(str, f"\nError from server: {response.status_code} - {response.text}")
                        )
            except Exception as e:
                QMetaObject.invokeMethod(
                    self.results_box, 
                    "append", 
                    Qt.ConnectionType.QueuedConnection, 
                    Q_ARG(str, f"\nError: {e}")
                )
            finally:
                QMetaObject.invokeMethod(
                    self.submit_btn, 
                    "setEnabled", 
                    Qt.ConnectionType.QueuedConnection, 
                    Q_ARG(bool, True)
                )
                
        threading.Thread(target=run_proc, daemon=True).start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Optional: Apply simple dark theme to the app for better look
    app.setStyle("Fusion")
    
    window = DiarizationTestUI()
    window.show()
    sys.exit(app.exec())
