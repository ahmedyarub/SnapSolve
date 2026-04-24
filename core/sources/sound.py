import pyaudio
import speech_recognition as sr
import threading
import logging
from typing import Callable, Optional

from .base import Source

logger = logging.getLogger(__name__)

class SoundSource(Source):
    def __init__(self, config=None):
        self.config = config or {}
        self.is_recording = False
        self.audio_frames = []
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Ensure we have SpeechRecognition ready
        self.recognizer = sr.Recognizer()

    def warmup(self):
        # We can just initialize PyAudio briefly to cache its startup
        try:
            p = pyaudio.PyAudio()
            p.terminate()
            logger.info("Speech Recognition / PyAudio warmup complete.")
        except Exception as e:
            logger.error(f"Speech Recognition warmup failed: {e}")

    @property
    def name(self):
        return "audio"

    def get_text(self, status_callback: Callable[[str], None] = None, *args, **kwargs) -> str:
        """This returns the text synchronously if we already have it.
        For interactive capture, we use start_recording/stop_recording manually,
        and the text is returned via a callback or handled in main."""
        # This function might not be used directly like screenshot, since audio is over time
        # The architecture typically calls `process_pipeline` with the extracted text for TextSource,
        # or the image for ImageSource. For Audio, we'll probably extract the text and pass it.
        raise ValueError("SoundSource does not support synchronous get_text without a pre-recorded buffer.")

    def get_image(self, *args, **kwargs) -> str:
        raise ValueError("SoundSource does not support image retrieval.")

    def start_recording(self, status_callback: Callable[[str], None] = None):
        if self.is_recording:
            return

        self.is_recording = True
        self.audio_frames = []
        self._stop_event.clear()

        device_name = self.config.get('audio_input_device_name')
        device_index = None

        # Find device index
        if device_name:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info['name'] == device_name and info['maxInputChannels'] > 0:
                    device_index = i
                    break
            p.terminate()

        if status_callback:
            status_callback("Recording started...")

        def _record():
            try:
                with sr.Microphone(device_index=device_index) as source:
                    self._sample_rate = source.SAMPLE_RATE
                    self._sample_width = source.SAMPLE_WIDTH
                    # Do not adjust for ambient noise to avoid delay on start, as per tests or just start streaming
                    stream = source.stream
                    while not self._stop_event.is_set():
                        data = stream.read(source.CHUNK, exception_on_overflow=False)
                        self.audio_frames.append(data)
            except Exception as e:
                logger.error(f"Recording error: {e}")
            finally:
                self.is_recording = False

        self._record_thread = threading.Thread(target=_record, daemon=True)
        self._record_thread.start()

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=2.0)

        self.is_recording = False

        if not self.audio_frames:
            return ""

        try:
            # We saved these when we started the microphone
            if not hasattr(self, '_sample_rate') or not hasattr(self, '_sample_width'):
                return ""
            audio_data = sr.AudioData(b''.join(self.audio_frames), self._sample_rate, self._sample_width)
            text = self.recognizer.recognize_google(audio_data)
            return text
        except sr.UnknownValueError:
            logger.info("Speech Recognition could not understand audio")
            return ""
        except sr.RequestError as e:
            logger.error(f"Could not request results from Speech Recognition service; {e}")
            return ""
        except Exception as e:
            logger.error(f"Error during audio processing: {e}")
            return ""
