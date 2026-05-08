import logging
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

import numpy as np
import pyaudio
import resampy
import speech_recognition as sr

from core.output import show_subtitle, update_subtitle, clear_subtitles
from .base import Source

# Add WhisperLive to path
whisperlive_path = os.path.join(
    str(os.path.dirname(os.path.dirname(str(os.path.dirname(__file__))))),
    "services",
    "whisperlive",
)
if whisperlive_path not in sys.path:
    sys.path.insert(0, whisperlive_path)

try:
    from whisper_live.client import (
        TranscriptionClient as WhisperLiveTranscriptionClient,
    )  # noqa: E402
except ImportError:
    WhisperLiveTranscriptionClient = None
    logging.error("Failed to import WhisperLiveTranscriptionClient. Real-time transcription will not work.")

logger = logging.getLogger(__name__)


def is_whisperlive_service_online(host="localhost", port=9090):
    """Check if WhisperLive service is online by checking if port is open."""
    try:
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.debug(f"WhisperLive service health check failed: {e}")
        return False


def start_whisperlive_service():
    """Start WhisperLive service if not already running."""
    server_script = os.path.join(whisperlive_path, "run_server.py")
    if not os.path.exists(server_script):
        logger.error(f"WhisperLive server script not found at {server_script}")
        return None

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                server_script,
                "--port",
                "9090",
                "--backend",
                "faster_whisper",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info(f"WhisperLive service starting with PID: {process.pid}...")
        # Don't wait here, let it start in the background. Health check will verify.
        return process
    except Exception as e:
        logger.error(f"Error starting WhisperLive service: {e}")
        return None


class SoundSource(Source):
    def __init__(self, config=None):
        self._sample_width = None
        self._sample_rate = None
        self.config = config or {}
        self.is_recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.audio_frames = []
        self.recognizer = sr.Recognizer()

        # WhisperLive related
        self.transcription_client: Optional[WhisperLiveTranscriptionClient] = None
        self.whisperlive_process: Optional[subprocess.Popen] = None
        self._last_transcription_text = ""
        self._current_utterance_text = ""
        self.realtime_transcription = True
        self._current_segment_is_completed = False

    def warmup(self):
        if WhisperLiveTranscriptionClient is None:
            logger.error("WhisperLive client not imported. Cannot perform warmup.")
            return

        logger.info("Warming up SoundSource...")
        if not is_whisperlive_service_online():
            logger.info("WhisperLive service is not running. Starting it now...")
            self.whisperlive_process = start_whisperlive_service()
            time.sleep(10)  # Give it time to start and load models
            if self.whisperlive_process and self.whisperlive_process.poll() is not None:
                logger.error("Failed to start WhisperLive service.")
                self.whisperlive_process = None
            elif not is_whisperlive_service_online():
                logger.error("WhisperLive service failed to become online.")
            else:
                logger.info("WhisperLive service started successfully.")
        else:
            logger.info("WhisperLive service is already running.")

    @property
    def name(self):
        return "audio"

    def get_text(self, *args, **kwargs) -> str:
        return self._last_transcription_text

    def get_image(self, *args, **kwargs) -> str:
        raise ValueError("SoundSource does not support image retrieval.")

    def start_recording(
        self,
        status_callback: Callable[[str], None] = None,
        enable_transcription: bool = None,
    ):
        if self.is_recording:
            return

        self.is_recording = True
        self._stop_event.clear()
        self.audio_frames = []
        self._last_transcription_text = ""
        self._current_utterance_text = ""
        self._current_segment_is_completed = False
        
        # Override transcription setting if explicitly provided
        if enable_transcription is not None:
            self.realtime_transcription = enable_transcription
        else:
            self.realtime_transcription = self.config.get("realtime_transcription", True)

        if self.realtime_transcription and WhisperLiveTranscriptionClient is None:
            logger.error("Cannot start transcription: WhisperLive client is not available.")
            if status_callback:
                status_callback("Error: Transcription client not found.")
            return

        if status_callback:
            status_callback("Starting recording...")

        if self.realtime_transcription:
            self._record_thread = threading.Thread(target=self._record_and_transcribe_worker, daemon=True)
        else:
            self._record_thread = threading.Thread(target=self._record_only_worker, daemon=True)
            
        self._record_thread.start()

    def _record_only_worker(self):
        """Records audio without streaming it to WhisperLive."""
        device_name = self.config.get("audio_input_device_name")
        device_index = None
        if device_name:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["name"] == device_name and info["maxInputChannels"] > 0:
                    device_index = i
                    break
            p.terminate()

        try:
            with sr.Microphone(device_index=device_index) as source:
                self._sample_rate = source.SAMPLE_RATE
                self._sample_width = source.SAMPLE_WIDTH
                stream = source.stream
                logger.info(f"Microphone opened for simple recording. Sample rate: {self._sample_rate}Hz.")

                while not self._stop_event.is_set():
                    data = stream.read(source.CHUNK)
                    self.audio_frames.append(data)
        except Exception as e:
            logger.error(f"Recording error: {e}")
        finally:
            logger.info("Simple recording loop stopped.")
            self.is_recording = False

    def _record_and_transcribe_worker(self):
        """Connects to WhisperLive and streams microphone audio for transcription."""
        # 1. Ensure WhisperLive service is running
        if not is_whisperlive_service_online():
            logger.warning("WhisperLive service not detected. Attempting to start...")
            self.warmup()  # This will start the service and wait
            if not is_whisperlive_service_online():
                logger.error("Failed to start or connect to WhisperLive service. Aborting.")
                self.is_recording = False
                return

        # 2. Initialize Transcription Client
        try:
            self.transcription_client = WhisperLiveTranscriptionClient(
                host="localhost",
                port=9090,
                lang="en",
                use_vad=True,
                transcription_callback=self._on_transcription_result,
            )
            
            # Wait for client to be ready, similar to test_sound.py
            client = self.transcription_client.client
            timeout = 15
            start_time = time.time()
            
            while not client.recording:
                if getattr(client, "server_error", False):
                    logger.error(f"WhisperLive server error: {getattr(client, 'error_message', 'Unknown error')}")
                    break
                if time.time() - start_time > timeout:
                    logger.error("Timeout waiting for WhisperLive server to be ready.")
                    break
                time.sleep(0.1)
                
            if not client.recording:
                logger.error("Failed to connect to WhisperLive server.")
                self.is_recording = False
                return
                
            logger.info("WhisperLive client initialized and recording.")
        except Exception as e:
            logger.error(f"Failed to initialize WhisperLive client: {e}")
            self.is_recording = False
            return

        # 3. Start streaming from microphone
        device_name = self.config.get("audio_input_device_name")
        device_index = None
        if device_name:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["name"] == device_name and info["maxInputChannels"] > 0:
                    device_index = i
                    break
            p.terminate()

        try:
            with sr.Microphone(device_index=device_index) as source:
                stream = source.stream
                source_sample_rate = source.SAMPLE_RATE
                target_sample_rate = 16000
                logger.info(f"Microphone opened. Sample rate: {source_sample_rate}Hz.")

                while not self._stop_event.is_set():
                    data = stream.read(source.CHUNK)
                    audio_array = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    if source_sample_rate != target_sample_rate:
                        audio_array = resampy.resample(audio_array, source_sample_rate, target_sample_rate)

                    self.transcription_client.client.send_packet_to_server(audio_array.tobytes())
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")
        finally:
            logger.info("Recording loop stopped.")
            if self.transcription_client:
                try:
                    self.transcription_client.client.send_packet_to_server("END_OF_AUDIO".encode("utf-8"))
                    logger.info("END_OF_AUDIO signal sent.")
                    time.sleep(1) # Give it a moment to process final audio
                    self.transcription_client.client.close_websocket()
                    logger.info("WhisperLive client closed.")
                except Exception as e:
                    logger.error(f"Error closing WhisperLive client: {e}")
            self.transcription_client = None
            self.is_recording = False

    def _on_transcription_result(self, _, segments):
        """Callback from WhisperLive client with transcription segments."""
        if not segments:
            # End of an utterance
            if self._current_utterance_text:
                self._last_transcription_text += self._current_utterance_text + " "
                self._current_utterance_text = ""
                self._current_segment_is_completed = False
            return

        latest_segment = segments[-1]
        full_text = latest_segment['text'].strip()
        is_completed = latest_segment.get('completed', False)

        if not full_text:
            return

        # If the segment we were working on is now marked as completed
        # or if the previous segment was completed and we are now on a new one
        if self._current_segment_is_completed:
            # We are starting a brand new segment because the last one finished
            show_subtitle(full_text)
            self._current_utterance_text = full_text
            self._current_segment_is_completed = is_completed
        elif full_text != self._current_utterance_text:
            # We are updating the current segment
            if not self._current_utterance_text:
                show_subtitle(full_text)
            else:
                update_subtitle(full_text, append=False)
            self._current_utterance_text = full_text
            self._current_segment_is_completed = is_completed

        # If this segment just completed, add it to the final text
        if is_completed and full_text:
            self._last_transcription_text += full_text + " "

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=3.0)
            if self._record_thread.is_alive():
                logger.warning("Recording thread did not terminate in time.")

        self.is_recording = False
        logger.info("Recording stopped.")

        if self.realtime_transcription:
            # Finalize last utterance if it wasn't already marked completed
            if self._current_utterance_text and not self._current_segment_is_completed:
                self._last_transcription_text += self._current_utterance_text
            
            # Let subtitles fade out naturally, but clear any empty ones
            if not self._current_utterance_text:
                 # Small delay to allow fade out animation to be noticeable
                threading.Timer(5.0, clear_subtitles).start()

            return self._last_transcription_text.strip()
        else:
            # Simple recording logic (non-streaming)
            if not self.audio_frames:
                return ""

            try:
                if not hasattr(self, "_sample_rate") or not hasattr(self, "_sample_width"):
                    return ""
                audio_data = sr.AudioData(
                    b"".join(self.audio_frames), self._sample_rate, self._sample_width
                )
                text = self.recognizer.recognize_google(audio_data)  # type: ignore[attr-defined]
                return text
            except sr.UnknownValueError:
                logger.info("Speech Recognition could not understand audio")
                return ""
            except sr.RequestError as e:
                logger.error(
                    f"Could not request results from Speech Recognition service; {e}"
                )
                return ""
            except Exception as e:
                logger.error(f"Error during audio processing: {e}")
                return ""

    def __del__(self):
        # Terminate the server process if this instance started it
        if self.whisperlive_process:
            logger.info("Terminating WhisperLive service process...")
            self.whisperlive_process.terminate()
            self.whisperlive_process.wait()