import logging
import os
import subprocess
import tempfile
import threading
import wave
from typing import Callable, Optional

import numpy as np
import pyaudio
import resampy
import speech_recognition as sr
import sys
import time

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
    logging.error(
        "Failed to import WhisperLiveTranscriptionClient. Real-time transcription will not work."
    )

logger = logging.getLogger(__name__)

# Short language code → BCP-47 locale for Google Speech Recognition
_GOOGLE_LANGUAGE_MAP: dict[str, str] = {
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "ru": "ru-RU",
    "zh": "zh-CN",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "ar": "ar-SA",
    "hi": "hi-IN",
    "tr": "tr-TR",
    "pl": "pl-PL",
    "nl": "nl-NL",
    "sv": "sv-SE",
    "cs": "cs-CZ",
    "ro": "ro-RO",
    "hu": "hu-HU",
    "uk": "uk-UA",
    "el": "el-GR",
    "he": "he-IL",
    "th": "th-TH",
    "vi": "vi-VN",
    "id": "id-ID",
    "ms": "ms-MY",
}


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


def start_whisperlive_service(model_size="small"):
    """Start WhisperLive service if not already running."""
    server_script = os.path.join(whisperlive_path, "run_server.py")
    if not os.path.exists(server_script):
        logger.error(f"WhisperLive server script not found at {server_script}")
        return None

    venv_python = (
        os.path.join(whisperlive_path, ".venv", "Scripts", "python.exe")
        if os.name == "nt"
        else os.path.join(whisperlive_path, ".venv", "bin", "python")
    )
    python_exec = venv_python if os.path.exists(venv_python) else sys.executable

    try:
        process = subprocess.Popen(
            [
                python_exec,
                server_script,
                "--port",
                "9090",
                "--backend",
                "faster_whisper",
                "--faster_whisper_custom_model_path",
                model_size,
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
    def __init__(self, config=None, session_manager=None):
        self._sample_width = None
        self._sample_rate = None
        self.config = config or {}
        self.session_manager = session_manager
        self.is_recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.audio_frames = []
        self.recognizer = sr.Recognizer()

        # WhisperLive related
        self.transcription_client_mic: Optional[WhisperLiveTranscriptionClient] = None
        self.transcription_client_loopback: Optional[WhisperLiveTranscriptionClient] = (
            None
        )
        self.whisperlive_process: Optional[subprocess.Popen] = None
        self._last_transcription_text = ""
        self._current_utterance_text = {"mic": "", "loopback": ""}
        self.realtime_transcription = True
        self._last_segment_start = {"mic": -1.0, "loopback": -1.0}

        # Translation related
        self._translation_language: str = ""
        self._last_translated_text = ""
        self._current_translated_utterance = {"mic": "", "loopback": ""}
        self._last_translated_segment_start = {"mic": -1.0, "loopback": -1.0}

        # Real-time correction engine (set externally before start_recording)
        self.correction_engine = None

    def warmup(self):
        if WhisperLiveTranscriptionClient is None:
            logger.error("WhisperLive client not imported. Cannot perform warmup.")
            return

        logger.info("Warming up SoundSource...")
        if not is_whisperlive_service_online():
            logger.info("WhisperLive service is not running. Starting it now...")
            model_size = self.config.get("transcription_model", "small")
            self.whisperlive_process = start_whisperlive_service(model_size)
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
        self._current_utterance_text = {"mic": "", "loopback": ""}
        self._last_segment_start = {"mic": -1.0, "loopback": -1.0}
        self._last_translated_text = ""
        self._current_translated_utterance = {"mic": "", "loopback": ""}
        self._last_translated_segment_start = {"mic": -1.0, "loopback": -1.0}
        self._translation_language = self.config.get("translation_language", "")

        # Override transcription setting if explicitly provided
        if enable_transcription is not None:
            self.realtime_transcription = enable_transcription
        else:
            self.realtime_transcription = self.config.get(
                "realtime_transcription", True
            )

        if self.realtime_transcription and WhisperLiveTranscriptionClient is None:
            logger.error(
                "Cannot start transcription: WhisperLive client is not available."
            )
            if status_callback:
                status_callback("Error: Transcription client not found.")
            return

        device_name = self.config.get("audio_input_device_name", "Default Device")
        loopback_name = self.config.get("audio_loopback_device_name")
        if status_callback:
            if loopback_name:
                status_callback(
                    f"Starting recording on {device_name} & {loopback_name}..."
                )
            else:
                status_callback(f"Starting recording on {device_name}...")

        if self.realtime_transcription:
            self._record_thread = threading.Thread(
                target=self._record_and_transcribe_worker,
                args=(status_callback,),
                daemon=True,
            )
        else:
            self._record_thread = threading.Thread(
                target=self._record_only_worker, daemon=True
            )

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

        loopback_name = self.config.get("audio_loopback_device_name")
        self.audio_frames_dict = {"mic": [], "loopback": []}

        def record_mic():
            fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                with sr.Microphone(device_index=device_index) as source:
                    self._sample_rate = source.SAMPLE_RATE
                    self._sample_width = source.SAMPLE_WIDTH
                    stream = source.stream
                    logger.info(
                        f"Microphone {device_name} opened for simple recording."
                    )

                    enhancer = None
                    if self.config.get("enable_audio_enhancement", False):
                        from .audio_processing import AudioEnhancer

                        enhancer = AudioEnhancer(sample_rate=self._sample_rate)

                    with wave.open(temp_wav_path, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(self._sample_width)
                        wf.setframerate(self._sample_rate)
                        while not self._stop_event.is_set():
                            data = stream.read(source.CHUNK)

                            if enhancer:
                                audio_array = (
                                    np.frombuffer(data, dtype=np.int16).astype(
                                        np.float32
                                    )
                                    / 32768.0
                                )
                                audio_array = enhancer.enhance(audio_array)
                                data = (audio_array * 32767).astype(np.int16).tobytes()

                            self.audio_frames_dict["mic"].append(data)
                            self._update_volume(data)
                            wf.writeframes(data)
            except Exception as e:
                logger.error(f"Mic Recording error: {e}")

        def record_loopback():
            import soundcard as sc
            import numpy as np

            try:
                speaker_name = (
                    loopback_name if loopback_name else sc.default_speaker().name
                )
                loopback_device = next(
                    (
                        m
                        for m in sc.all_microphones(include_loopback=True)
                        if m.name == speaker_name and m.isloopback
                    ),
                    None,
                )
                if loopback_device is None:
                    raise ValueError(f"Loopback device {speaker_name} not found")
                # Fallback if sample rate wasn't set yet
                sample_rate = getattr(self, "_sample_rate", 16000)
                if not sample_rate:
                    sample_rate = 16000
                logger.info(f"Loopback {loopback_name} opened for simple recording.")

                enhancer = None
                if self.config.get("enable_audio_enhancement", False):
                    from .audio_processing import AudioEnhancer

                    enhancer = AudioEnhancer(sample_rate=sample_rate)

                with loopback_device.recorder(
                    samplerate=sample_rate, channels=1
                ) as mic:
                    while not self._stop_event.is_set():
                        data = mic.record(numframes=1024)
                        audio_array = data.flatten()

                        if enhancer:
                            audio_array = enhancer.enhance(
                                audio_array.astype(np.float32)
                            )

                        int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                        self.audio_frames_dict["loopback"].append(int16_data)
            except Exception as e:
                logger.error(f"Loopback Recording error: {e}")

        threads = []
        t1 = threading.Thread(target=record_mic)
        threads.append(t1)
        t1.start()

        if loopback_name:
            t2 = threading.Thread(target=record_loopback)
            threads.append(t2)
            t2.start()

        for t in threads:
            t.join()

        logger.info("Simple recording loops stopped.")
        self.is_recording = False

    def _ensure_whisperlive_service(self):
        """Ensure WhisperLive service is running."""
        if not is_whisperlive_service_online():
            logger.warning("WhisperLive service not detected. Attempting to start...")
            self.warmup()
            if not is_whisperlive_service_online():
                logger.error(
                    "Failed to start or connect to WhisperLive service. Aborting."
                )
                self.is_recording = False
                return False
        return True

    def _initialize_transcription_clients(self):
        """Initialize transcription clients."""
        try:
            transcription_lang = self.config.get("transcription_language", "en") or None
            translation_lang = self._translation_language

            if translation_lang and translation_lang == transcription_lang:
                translation_lang = ""

            translate_kwargs: dict = {}
            if translation_lang:
                translate_kwargs["enable_translation"] = True
                translate_kwargs["target_language"] = translation_lang
                logger.info(
                    "Translation enabled — target language: %s", translation_lang
                )

            # Mic Client
            mic_kwargs = translate_kwargs.copy()
            if translation_lang:
                mic_kwargs["translation_callback"] = lambda _, segs: (
                    self._on_translation_result(_, segs, source="mic")
                )
            self.transcription_client_mic = WhisperLiveTranscriptionClient(
                host="localhost",
                port=9090,
                lang=transcription_lang,
                use_vad=True,
                transcription_callback=lambda _, segs: self._on_transcription_result(
                    _, segs, source="mic"
                ),
                no_speech_thresh=0.4,
                **mic_kwargs,
            )

            # Loopback Client
            loopback_device = self.config.get("audio_loopback_device_name")
            if loopback_device:
                loop_kwargs = translate_kwargs.copy()
                if translation_lang:
                    loop_kwargs["translation_callback"] = lambda _, segs: (
                        self._on_translation_result(_, segs, source="loopback")
                    )
                self.transcription_client_loopback = WhisperLiveTranscriptionClient(
                    host="localhost",
                    port=9090,
                    lang=transcription_lang,
                    use_vad=True,
                    transcription_callback=lambda _, segs: (
                        self._on_transcription_result(_, segs, source="loopback")
                    ),
                    no_speech_thresh=0.4,
                    **loop_kwargs,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize WhisperLive client: {e}")
            self.is_recording = False
            return False

    def _wait_for_client_ready(self, client, timeout=15, status_callback=None):
        """Wait for client to be ready."""
        start_time = time.time()
        if timeout > 15:
            msg = "Downloading translation model (may take 5+ mins the first time)..."
            logger.info(msg)
            if status_callback:
                status_callback(msg)

        while not client.recording:
            if getattr(client, "server_error", False):
                logger.error(
                    f"WhisperLive server error: {getattr(client, 'error_message', 'Unknown error')}"
                )
                return False
            if time.time() - start_time > timeout:
                logger.error("Timeout waiting for WhisperLive server to be ready.")
                return False
            time.sleep(0.1)

        return client.recording

    def _write_transcription_separator(self):
        """Write transcription separator to file."""
        if (
            self.session_manager
            and getattr(self.session_manager, "save_transcriptions", False)
            and getattr(self.session_manager, "transcription_file", None)
        ):
            try:
                speaker = "🎤/💻"
                with open(
                    self.session_manager.transcription_file, "a", encoding="utf-8"
                ) as f:
                    f.write(f"\n--- [{speaker}] ---\n")
            except Exception as e:
                logger.error(f"Failed to write initial transcription separator: {e}")

    @staticmethod
    def _find_audio_device_index(device_name):
        """Find audio device index by name."""
        device_index = None
        if device_name:
            p = pyaudio.PyAudio()
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["name"] == device_name and info["maxInputChannels"] > 0:
                    device_index = i
                    break
            p.terminate()
        return device_index

    def _stream_loopback_to_whisperlive(self, device_name):
        """Stream loopback audio to WhisperLive."""
        if not self.transcription_client_loopback:
            return

        wav_file = None
        if (
            self.config.get("post_recording_diarization", False)
            and self.session_manager
        ):
            session_dir = self.session_manager.get_session_dir(
                self.session_manager.current_session_id
            )
            if session_dir:
                wav_path = os.path.join(session_dir, "audio_loopback.wav")
                wav_file = wave.open(wav_path, "wb")
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
        try:
            import soundcard as sc

            loopback_device = next(
                (
                    m
                    for m in sc.all_microphones(include_loopback=True)
                    if m.name == device_name and m.isloopback
                ),
                None,
            )
            if loopback_device is None:
                raise ValueError(f"Loopback device {device_name} not found")
            target_sample_rate = 16000

            if wav_file:
                wav_file.setframerate(target_sample_rate)

            enhancer = None
            if self.config.get("enable_audio_enhancement", False):
                from .audio_processing import AudioEnhancer

                enhancer = AudioEnhancer(sample_rate=target_sample_rate)

            logger.info(f"Loopback device {device_name} opened.")
            with loopback_device.recorder(
                samplerate=target_sample_rate, channels=1
            ) as mic:
                while not self._stop_event.is_set():
                    data = mic.record(numframes=4096)
                    audio_array = data.flatten().astype(np.float32)

                    if enhancer:
                        audio_array = enhancer.enhance(audio_array)

                    self.transcription_client_loopback.client.send_packet_to_server(
                        audio_array.tobytes()
                    )

                    if wav_file:
                        int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                        wav_file.writeframes(int16_data)
        except Exception as e:
            logger.error(f"Audio streaming loopback error: {e}")
        finally:
            if wav_file:
                wav_file.close()

    def _stream_audio_to_whisperlive(self, device_index, device_name):
        """Stream audio to WhisperLive."""
        wav_file = None
        if (
            self.config.get("post_recording_diarization", False)
            and self.session_manager
        ):
            session_dir = self.session_manager.get_session_dir(
                self.session_manager.current_session_id
            )
            if session_dir:
                wav_path = os.path.join(session_dir, "audio_mic.wav")
                wav_file = wave.open(wav_path, "wb")
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
        try:
            with sr.Microphone(device_index=device_index) as source:
                stream = source.stream
                source_sample_rate = source.SAMPLE_RATE
                target_sample_rate = 16000
                logger.info(
                    f"Microphone {device_name} opened. Sample rate: {source_sample_rate}Hz."
                )

                if wav_file:
                    wav_file.setframerate(target_sample_rate)

                enhancer = None
                if self.config.get("enable_audio_enhancement", False):
                    from .audio_processing import AudioEnhancer

                    enhancer = AudioEnhancer(sample_rate=target_sample_rate)

                while not self._stop_event.is_set():
                    data = stream.read(source.CHUNK)
                    self._update_volume(data)
                    audio_array = (
                        np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    )
                    if source_sample_rate != target_sample_rate:
                        audio_array = resampy.resample(
                            audio_array, source_sample_rate, target_sample_rate
                        )

                    if enhancer:
                        audio_array = enhancer.enhance(audio_array)

                    self.transcription_client_mic.client.send_packet_to_server(
                        audio_array.tobytes()
                    )

                    if wav_file:
                        int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                        wav_file.writeframes(int16_data)
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")
        finally:
            if wav_file:
                wav_file.close()

    def _cleanup_transcription_clients(self):
        """Cleanup transcription clients."""
        for client_attr in [
            "transcription_client_mic",
            "transcription_client_loopback",
        ]:
            client = getattr(self, client_attr, None)
            if client:
                try:
                    client.client.send_packet_to_server("END_OF_AUDIO".encode("utf-8"))
                    time.sleep(1)
                    client.client.close_websocket()
                except Exception as e:
                    logger.error(f"Error closing WhisperLive client: {e}")
                setattr(self, client_attr, None)

    def _wait_for_clients_ready(self, timeout=15, status_callback=None):
        ready = True
        if self.transcription_client_mic:
            ready = ready and self._wait_for_client_ready(
                self.transcription_client_mic.client, timeout, status_callback
            )
        if self.transcription_client_loopback:
            ready = ready and self._wait_for_client_ready(
                self.transcription_client_loopback.client, timeout, status_callback
            )
        return ready

    def _record_and_transcribe_worker(self, status_callback=None):
        """Streams audio to WhisperLive."""
        if not self._ensure_whisperlive_service():
            return

        if not self._initialize_transcription_clients():
            return

        timeout = 600 if self._translation_language else 15
        if not self._wait_for_clients_ready(
            timeout=timeout, status_callback=status_callback
        ):
            self.is_recording = False
            return

        logger.info("WhisperLive clients initialized and recording.")
        self._write_transcription_separator()

        device_name = self.config.get("audio_input_device_name")
        device_index = self._find_audio_device_index(device_name)

        loopback_name = self.config.get("audio_loopback_device_name")

        threads = []
        try:
            if self.transcription_client_mic:
                t1 = threading.Thread(
                    target=self._stream_audio_to_whisperlive,
                    args=(device_index, device_name),
                )
                threads.append(t1)
                t1.start()
            if self.transcription_client_loopback and loopback_name:
                t2 = threading.Thread(
                    target=self._stream_loopback_to_whisperlive, args=(loopback_name,)
                )
                threads.append(t2)
                t2.start()

            for t in threads:
                t.join()
        finally:
            logger.info("Recording loops stopped.")
            self._cleanup_transcription_clients()
            self.is_recording = False

    def _finalize_current_utterance(self, source="mic"):
        """Finalize current utterance."""
        if self._current_utterance_text[source]:
            finalized_text = self._current_utterance_text[source]
            prefix = "🎤 " if source == "mic" else "💻 "
            self._last_transcription_text += f"{prefix}{finalized_text} "
            if self.session_manager:
                speaker = "🎤" if source == "mic" else "💻"
                self.session_manager.append_transcription_segment(
                    finalized_text, speaker_name=speaker
                )
            self._current_utterance_text[source] = ""

    def _process_new_segment(self, text, start, source="mic"):
        """Process new segment."""
        self._finalize_current_utterance(source)
        if not self._translation_language:
            prefix = "🎤 " if source == "mic" else "💻 "
            show_subtitle(f"{prefix}{text}")
        self._last_segment_start[source] = start
        self._current_utterance_text[source] = text

    def _process_segment_update(self, text, source="mic"):
        """Process segment update."""
        if text != self._current_utterance_text[source]:
            if not self._translation_language:
                prefix = "🎤 " if source == "mic" else "💻 "
                update_subtitle(f"{prefix}{text}", append=False)
            self._current_utterance_text[source] = text

    def _on_transcription_result(self, _, segments, source="mic"):
        """Callback from WhisperLive client with transcription segments."""
        logger.debug(f"Received segments from {source}: {segments}")
        if not segments:
            self._finalize_current_utterance(source)
            return

        for segment in segments:
            text = segment["text"].strip()
            start = float(segment.get("start", 0.0))

            if not text:
                continue

            if start > self._last_segment_start[source]:
                self._process_new_segment(text, start, source)
            elif start == self._last_segment_start[source]:
                self._process_segment_update(text, source)

            # When a segment is marked completed, immediately forward it
            # to the correction engine.  The normal finalization path only
            # triggers when the *next* segment arrives, which can be
            # arbitrarily delayed — too late for real-time feedback.
            if segment.get("completed") and self.correction_engine and text:
                self.correction_engine.on_sentence_finalized(text, source)

    def _on_translation_result(self, _, segments, source="mic"):
        """Callback from WhisperLive client with translated segments."""
        logger.debug(f"Received translated segments from {source}: {segments}")
        if not segments:
            return

        for segment in segments:
            text = segment["text"].strip()
            start = float(segment.get("start", 0.0))

            if not text:
                continue

            if start > self._last_translated_segment_start[source]:
                if self._current_translated_utterance[source]:
                    prefix = "🎤 " if source == "mic" else "💻 "
                    self._last_translated_text += (
                        f"{prefix}{self._current_translated_utterance[source]} "
                    )
                prefix = "🎤 " if source == "mic" else "💻 "
                show_subtitle(f"{prefix}{text}")
                self._last_translated_segment_start[source] = start
                self._current_translated_utterance[source] = text
            elif start == self._last_translated_segment_start[source]:
                if text != self._current_translated_utterance[source]:
                    prefix = "🎤 " if source == "mic" else "💻 "
                    update_subtitle(f"{prefix}{text}", append=False)
                    self._current_translated_utterance[source] = text

    def _stop_recording_thread(self):
        """Stop recording thread."""
        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=3.0)
            if self._record_thread.is_alive():
                logger.warning("Recording thread did not terminate in time.")

    def _finalize_last_utterance(self):
        """Finalize last utterance."""
        for source in ["mic", "loopback"]:
            if self._current_utterance_text[source]:
                finalized_text = self._current_utterance_text[source]
                prefix = "🎤 " if source == "mic" else "💻 "
                self._last_transcription_text += f"{prefix}{finalized_text} "
                if self.session_manager:
                    speaker = "🎤" if source == "mic" else "💻"
                    self.session_manager.append_transcription_segment(
                        finalized_text, speaker_name=speaker
                    )
                # Feed finalized sentence to the real-time correction engine
                if self.correction_engine:
                    self.correction_engine.on_sentence_finalized(finalized_text, source)

    def _process_realtime_transcription(self):
        """Process realtime transcription."""
        self._finalize_last_utterance()

        # Finalize any remaining translated utterance
        for source in ["mic", "loopback"]:
            if self._current_translated_utterance[source]:
                prefix = "🎤 " if source == "mic" else "💻 "
                self._last_translated_text += (
                    f"{prefix}{self._current_translated_utterance[source]} "
                )

        has_content = any(self._current_utterance_text.values()) or any(
            self._current_translated_utterance.values()
        )
        if not has_content:
            threading.Timer(5.0, clear_subtitles).start()

        # Return translated text if translation was active, otherwise original
        if self._translation_language and self._last_translated_text.strip():
            return self._last_translated_text.strip()
        return self._last_transcription_text.strip()

    def _process_simple_recording(self):
        """Process simple recording."""
        if not hasattr(self, "audio_frames_dict"):
            return ""

        results = []
        transcription_lang = self.config.get("transcription_language", "en")
        google_lang = _GOOGLE_LANGUAGE_MAP.get(transcription_lang, transcription_lang)

        for source, frames in self.audio_frames_dict.items():
            if not frames:
                continue
            try:
                if not hasattr(self, "_sample_rate") or not hasattr(
                    self, "_sample_width"
                ):
                    continue
                audio_data = sr.AudioData(
                    b"".join(frames), self._sample_rate, self._sample_width
                )
                text = self.recognizer.recognize_google(
                    audio_data, language=google_lang
                )  # type: ignore[attr-defined]
                if text:
                    prefix = "🎤 " if source == "mic" else "💻 "
                    results.append(f"{prefix}{text}")
            except sr.UnknownValueError:
                logger.info(
                    f"Speech Recognition could not understand audio from {source}"
                )
            except sr.RequestError as e:
                logger.error(
                    f"Could not request results from Speech Recognition service for {source}; {e}"
                )
            except Exception as e:
                logger.error(f"Error during audio processing for {source}: {e}")

        return " ".join(results).strip()

    def _update_volume(self, data: bytes):
        """Calculate and broadcast audio volume for UI."""
        from core.ui.signals import ui_signals

        audio_data = np.frombuffer(data, dtype=np.int16)
        if len(audio_data) > 0:
            vol = np.abs(audio_data.astype(np.float32)).max()

            # Keep a running max of the volume to auto-normalize
            # against whatever the current OS mixer volume is.
            self._max_observed_vol = max(getattr(self, "_max_observed_vol", 500.0), vol)

            # Slowly decay the max volume so it can adapt if the user turns their system volume down
            # Floor at 500.0 so that a totally silent room doesn't decay to the noise floor and show 100%
            self._max_observed_vol = max(500.0, self._max_observed_vol * 0.995)

            # Scale the current volume relative to the maximum observed volume
            scaled_vol = int((vol / self._max_observed_vol) * 100)
            scaled_vol = min(100, max(0, scaled_vol))

            ui_signals.update_volume.emit(scaled_vol)

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self._stop_recording_thread()

        self.is_recording = False
        logger.info("Recording stopped.")

        from core.ui.signals import ui_signals

        ui_signals.update_volume.emit(0)

        if self.realtime_transcription:
            return self._process_realtime_transcription()
        else:
            return self._process_simple_recording()

    def __del__(self):
        # Terminate the server process if this instance started it
        if self.whisperlive_process:
            logger.info("Terminating WhisperLive service process...")
            self.whisperlive_process.terminate()
            self.whisperlive_process.wait()
