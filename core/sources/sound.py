import logging
import queue
import threading
import time
from typing import Callable, Optional

import pyaudio
import speech_recognition as sr

from core.output import show_subtitle, update_subtitle
from .base import Source

logger = logging.getLogger(__name__)


class SoundSource(Source):
    def __init__(self, config=None):
        self._sample_width = None
        self._sample_rate = None
        self.config = config or {}
        self.is_recording = False
        self.audio_frames = []
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Ensure we have SpeechRecognition ready
        self.recognizer = sr.Recognizer()

        # Real-time transcription settings
        self.realtime_transcription = self.config.get("realtime_transcription", True)
        self.pause_threshold = self.config.get("transcription_pause_threshold", 1.0)
        self.transcription_interval = self.config.get(
            "transcription_interval", 2.0
        )  # Transcribe every N seconds during speech

        # Real-time transcription state
        self._transcription_thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._last_audio_time = 0
        self._current_transcription_buffer = []
        self._transcription_stop_event = threading.Event()

    def warmup(self):
        try:
            p = pyaudio.PyAudio()
            p.terminate()

            test_file = "test_sound.wav"
            logger.info(f"Testing recognition with {test_file}...")
            with sr.AudioFile(test_file) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)  # type: ignore[attr-defined]

                expected_text = "this is a test of the audio system"
                if text.lower() == expected_text:
                    logger.info(f"Warmup recognition success: {text}")
                else:
                    logger.error(
                        f"Warmup recognition failed: expected '{expected_text}', got '{text}'"
                    )

            logger.info("Speech Recognition / PyAudio warmup complete.")
        except sr.UnknownValueError:
            logger.warning("Warmup recognition could not understand audio.")
        except sr.RequestError as e:
            logger.warning(f"Warmup recognition request failed: {e}")
        except Exception as e:
            logger.error(f"Speech Recognition warmup failed: {e}")

    @property
    def name(self):
        return "audio"

    def get_text(
        self, status_callback: Callable[[str], None] = None, *args, **kwargs
    ) -> str:
        """This returns the text synchronously if we already have it.
        For interactive capture, we use start_recording/stop_recording manually,
        and the text is returned via a callback or handled in main."""
        # This function might not be used directly like screenshot, since audio is over time
        # The architecture typically calls `process_pipeline` with the extracted text for TextSource,
        # or the image for ImageSource. For Audio, we'll probably extract the text and pass it.
        raise ValueError(
            "SoundSource does not support synchronous get_text without a pre-recorded buffer."
        )

    def get_image(self, *args, **kwargs) -> str:
        raise ValueError("SoundSource does not support image retrieval.")

    def start_recording(self, status_callback: Callable[[str], None] = None):
        if self.is_recording:
            return

        self.is_recording = True
        self.audio_frames = []
        self._stop_event.clear()
        self._transcription_stop_event.clear()
        self._current_transcription_buffer = []
        self._last_audio_time = time.time()

        device_name = self.config.get("audio_input_device_name")
        device_index = None

        # Find device index
        if device_name:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["name"] == device_name and info["maxInputChannels"] > 0:
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
                        data = stream.read(source.CHUNK)
                        self.audio_frames.append(data)

                        # Add to transcription queue if enabled
                        if self.realtime_transcription:
                            self._audio_queue.put((data, time.time()))
                            self._last_audio_time = time.time()

            except Exception as e:
                logger.error(f"Recording error: {e}")
            finally:
                self.is_recording = False

        self._record_thread = threading.Thread(target=_record, daemon=True)
        assert self._record_thread is not None
        self._record_thread.start()

        # Start real-time transcription thread if enabled
        if self.realtime_transcription:
            logger.info("Starting real-time transcription worker thread")
            self._transcription_thread = threading.Thread(
                target=self._realtime_transcription_worker, daemon=True
            )
            assert self._transcription_thread is not None
            self._transcription_thread.start()
            logger.info("Real-time transcription worker thread started")

    def _realtime_transcription_worker(self):
        """Worker thread for real-time transcription with pause detection."""
        logger.info("Real-time transcription worker started")
        transcription_buffer = []
        current_sentence = ""  # Track the current sentence being built
        last_transcription_time = 0
        loop_count = 0

        while not self._transcription_stop_event.is_set():
            loop_count += 1
            try:
                current_time = time.time()

                # Wait for audio data. If we get it, add it and check for transcription triggers
                try:
                    data, timestamp = self._audio_queue.get(timeout=0.1)
                    transcription_buffer.append(data)
                    if loop_count % 10 == 0:  # Log every 10 loops
                        logger.debug(
                            f"Audio buffer size: {len(transcription_buffer)} chunks"
                        )
                except queue.Empty:
                    # Queue is empty, which means we're in a potential pause.
                    pass  # Proceed to check for pause logic below.

                # Check for transcription triggers (both when queue is empty AND when we have audio)
                time_since_last_audio = current_time - self._last_audio_time

                # Transcribe on pause OR at regular intervals during speech
                should_transcribe = False
                is_silence = False

                if (
                    time_since_last_audio >= self.pause_threshold
                    and transcription_buffer
                ):
                    # Silence detected - finalize current sentence and start new one
                    should_transcribe = True
                    is_silence = True
                    logger.info(
                        f"Silence detected ({time_since_last_audio:.1f}s), finalizing sentence with {len(transcription_buffer)} chunks"
                    )
                elif (
                    current_time - last_transcription_time
                    >= self.transcription_interval
                    and transcription_buffer
                    and len(transcription_buffer) > 5
                ):
                    # Regular interval during speech - transcribe and append to current sentence
                    should_transcribe = True
                    logger.info(
                        f"Interval reached ({self.transcription_interval}s), transcribing buffer with {len(transcription_buffer)} chunks"
                    )

                if should_transcribe:
                    new_text = self._transcribe_buffer(transcription_buffer)
                    transcription_buffer = []
                    last_transcription_time = current_time

                    if new_text:
                        if is_silence:
                            # Silence detected - show current sentence and start new one
                            if current_sentence:
                                # Show the accumulated sentence (update last one)
                                self._display_subtitle(
                                    current_sentence, update_last=True
                                )
                                logger.info(f"Finalized sentence: {current_sentence}")
                                current_sentence = ""
                            # Start new sentence with the new text
                            current_sentence = new_text
                            logger.info(f"Starting new sentence: {current_sentence}")
                            # Display the new sentence as a new subtitle
                            self._display_subtitle(current_sentence, update_last=False)
                        else:
                            # Interval during speech - append to current sentence and display
                            if current_sentence:
                                # Append to existing sentence
                                current_sentence += " " + new_text
                                logger.info(f"Appended to sentence: {current_sentence}")
                            else:
                                # Start new sentence
                                current_sentence = new_text
                                logger.info(f"Started sentence: {current_sentence}")

                            # Display the accumulated sentence during intervals (update last one)
                            self._display_subtitle(current_sentence, update_last=True)

            except Exception as e:
                logger.error(f"Real-time transcription error: {e}")
                transcription_buffer = []

        # Transcribe any remaining audio and finalize current sentence
        if transcription_buffer:
            logger.info(
                f"Transcribing remaining audio with {len(transcription_buffer)} chunks"
            )
            new_text = self._transcribe_buffer(transcription_buffer)
            if new_text:
                if current_sentence:
                    current_sentence += " " + new_text
                else:
                    current_sentence = new_text

        # Show the final accumulated sentence (update last one instead of creating new)
        if current_sentence:
            logger.info(f"Final accumulated sentence: {current_sentence}")
            self._display_subtitle(current_sentence, update_last=True)

        logger.info("Real-time transcription worker stopped")

    def _transcribe_buffer(self, audio_buffer):
        """Transcribe a buffer of audio data and return the text."""
        if not audio_buffer:
            return ""

        try:
            # Combine audio chunks
            audio_data = b"".join(audio_buffer)

            # Create AudioData object
            if not hasattr(self, "_sample_rate") or not hasattr(self, "_sample_width"):
                return ""

            sr_audio = sr.AudioData(audio_data, self._sample_rate, self._sample_width)

            # Transcribe
            try:
                text = self.recognizer.recognize_google(sr_audio)  # type: ignore[attr-defined]
                if text.strip():
                    logger.info(f"Real-time transcription: {text}")
                    return text
            except sr.UnknownValueError:
                logger.debug("Real-time transcription could not understand audio")
            except sr.RequestError as e:
                logger.error(f"Real-time transcription service error: {e}")

        except Exception as e:
            logger.error(f"Error transcribing buffer: {e}")

        return ""

    @staticmethod
    def _display_subtitle(text: str, update_last: bool = False):
        """Display transcription as subtitle."""
        try:
            logger.info(
                f"Attempting to display subtitle: {text}, update_last: {update_last}"
            )
            if update_last:
                update_subtitle(text)
            else:
                show_subtitle(text)
            logger.info("Subtitle display signal sent successfully")
        except Exception as e:
            logger.error(f"Error displaying subtitle: {e}")

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self._stop_event.set()
        self._transcription_stop_event.set()

        if self._record_thread:
            self._record_thread.join(timeout=2.0)

        if self._transcription_thread:
            self._transcription_thread.join(timeout=2.0)

        self.is_recording = False

        # Don't clear subtitles immediately - let them fade naturally
        # try:
        #     clear_subtitles()
        # except Exception as e:
        #     logger.error(f"Error clearing subtitles: {e}")

        if not self.audio_frames:
            return ""

        try:
            # We saved these when we started the microphone
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
