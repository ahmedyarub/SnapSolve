"""Real-time transcription and translation processing.

Manages WhisperLive transcription client lifecycle, segment callbacks,
utterance finalization, and subtitle updates.  Also provides a Google
Speech-to-Text fallback for simple (non-streaming) recordings.
"""
import logging
import os
import sys
import threading
import time
from typing import Callable, Optional

import speech_recognition as sr

from core.output import show_subtitle, update_subtitle, clear_subtitles

logger = logging.getLogger(__name__)

# Add WhisperLive to path for import
_WHISPERLIVE_PATH = os.path.join(
    str(os.path.dirname(os.path.dirname(str(os.path.dirname(__file__))))),
    "services",
    "whisperlive",
)
if _WHISPERLIVE_PATH not in sys.path:
    sys.path.insert(0, _WHISPERLIVE_PATH)

try:
    from whisper_live.client import (
        TranscriptionClient as WhisperLiveTranscriptionClient,
    )  # noqa: E402
except ImportError:
    WhisperLiveTranscriptionClient = None
    logging.error(
        "Failed to import WhisperLiveTranscriptionClient. Real-time transcription will not work."
    )

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


class TranscriptionProcessor:
    """Manages transcription client lifecycle and segment processing.

    Owns the WhisperLive clients, handles transcription/translation
    callbacks, accumulates utterances, and writes to session transcription
    files.
    """

    def __init__(self, config: dict | None = None, session_manager=None):
        self.config = config or {}
        self.session_manager = session_manager

        # WhisperLive clients
        self.client_mic: Optional[WhisperLiveTranscriptionClient] = None
        self.client_loopback: Optional[WhisperLiveTranscriptionClient] = None

        # Transcription state
        self._last_transcription_text: str = ""
        self._current_utterance_text: dict[str, str] = {"mic": "", "loopback": ""}
        self._last_segment_start: dict[str, float] = {"mic": -1.0, "loopback": -1.0}

        # Translation state
        self._translation_language: str = ""
        self._last_translated_text: str = ""
        self._current_translated_utterance: dict[str, str] = {"mic": "", "loopback": ""}
        self._last_translated_segment_start: dict[str, float] = {"mic": -1.0, "loopback": -1.0}

        # Real-time correction engine (set externally)
        self.correction_engine = None

    def reset(self):
        """Reset all transcription state for a new recording session."""
        self._last_transcription_text = ""
        self._current_utterance_text = {"mic": "", "loopback": ""}
        self._last_segment_start = {"mic": -1.0, "loopback": -1.0}
        self._last_translated_text = ""
        self._current_translated_utterance = {"mic": "", "loopback": ""}
        self._last_translated_segment_start = {"mic": -1.0, "loopback": -1.0}
        self._translation_language = self.config.get("translation_language", "")

    @property
    def last_transcription_text(self) -> str:
        """The accumulated transcription text from the last recording."""
        return self._last_transcription_text

    @staticmethod
    def is_client_available() -> bool:
        """Return True if WhisperLiveTranscriptionClient is importable."""
        return WhisperLiveTranscriptionClient is not None

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------
    def initialize_clients(self) -> bool:
        """Initialize WhisperLive transcription clients."""
        try:
            transcription_lang = self.config.get("transcription_language", "en") or None
            translation_lang = self._translation_language

            if translation_lang and translation_lang == transcription_lang:
                translation_lang = ""

            translate_kwargs: dict = {}
            if translation_lang:
                translate_kwargs["enable_translation"] = True
                translate_kwargs["target_language"] = translation_lang
                logger.info("Translation enabled — target language: %s", translation_lang)

            # Mic Client
            mic_kwargs = translate_kwargs.copy()
            if translation_lang:
                mic_kwargs["translation_callback"] = lambda _, segs: (
                    self._on_translation_result(_, segs, source="mic")
                )
            self.client_mic = WhisperLiveTranscriptionClient(
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
                self.client_loopback = WhisperLiveTranscriptionClient(
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
            return False

    def wait_for_clients_ready(
        self,
        timeout: int = 15,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Wait for transcription clients to be ready."""
        ready = True
        if self.client_mic:
            ready = ready and self._wait_for_client_ready(
                self.client_mic.client, timeout, status_callback
            )
        if self.client_loopback:
            ready = ready and self._wait_for_client_ready(
                self.client_loopback.client, timeout, status_callback
            )
        return ready

    @staticmethod
    def _wait_for_client_ready(client, timeout: int = 15, status_callback=None) -> bool:
        """Wait for a single client to be ready."""
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

    def cleanup_clients(self):
        """Close WebSocket connections and release client resources."""
        for client_attr in ["client_mic", "client_loopback"]:
            client = getattr(self, client_attr, None)
            if client:
                try:
                    client.client.send_packet_to_server("END_OF_AUDIO".encode("utf-8"))
                    time.sleep(1)
                    client.client.close_websocket()
                except Exception as e:
                    logger.error(f"Error closing WhisperLive client: {e}")
                setattr(self, client_attr, None)

    # ------------------------------------------------------------------
    # Transcription separator
    # ------------------------------------------------------------------
    def write_transcription_separator(self):
        """Write a visual separator to the transcription file."""
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

    # ------------------------------------------------------------------
    # Transcription callbacks
    # ------------------------------------------------------------------
    def _finalize_current_utterance(self, source: str = "mic"):
        """Finalize current utterance and append to accumulated text."""
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

    def _process_new_segment(self, text: str, start: float, source: str = "mic"):
        """Process a new transcription segment."""
        self._finalize_current_utterance(source)
        if not self._translation_language:
            prefix = "🎤 " if source == "mic" else "💻 "
            show_subtitle(f"{prefix}{text}")
        self._last_segment_start[source] = start
        self._current_utterance_text[source] = text

    def _process_segment_update(self, text: str, source: str = "mic"):
        """Process an update to the current segment."""
        if text != self._current_utterance_text[source]:
            if not self._translation_language:
                prefix = "🎤 " if source == "mic" else "💻 "
                update_subtitle(f"{prefix}{text}", append=False)
            self._current_utterance_text[source] = text

    def _on_transcription_result(self, _, segments, source: str = "mic"):
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

            # Forward completed segments to correction engine immediately
            if segment.get("completed") and self.correction_engine and text:
                self.correction_engine.on_sentence_finalized(text, source)

    def _on_translation_result(self, _, segments, source: str = "mic"):
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

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------
    def finalize_all(self) -> str:
        """Finalize all utterances and return the transcription text.

        Call after recording stops.  Returns translated text if translation
        was active, otherwise the original transcription.
        """
        # Finalize remaining utterances
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

        # Finalize remaining translated utterances
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

    # ------------------------------------------------------------------
    # Simple recording fallback (Google Speech-to-Text)
    # ------------------------------------------------------------------
    @staticmethod
    def process_simple_recording(
        audio_frames_dict: dict,
        config: dict,
        sample_rate: int | None,
        sample_width: int | None,
    ) -> str:
        """Transcribe audio frames using Google Speech-to-Text.

        Used when real-time WhisperLive transcription is disabled.
        """
        if not audio_frames_dict:
            return ""

        recognizer = sr.Recognizer()
        results = []
        transcription_lang = config.get("transcription_language", "en")
        google_lang = _GOOGLE_LANGUAGE_MAP.get(transcription_lang, transcription_lang)

        for source, frames in audio_frames_dict.items():
            if not frames:
                continue
            if sample_rate is None or sample_width is None:
                continue
            try:
                audio_data = sr.AudioData(b"".join(frames), sample_rate, sample_width)
                text = recognizer.recognize_google(
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
