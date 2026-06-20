"""Audio recording source — thin orchestrator.

Delegates to:
- :mod:`whisperlive_manager` — WhisperLive service lifecycle
- :mod:`audio_recorder` — device discovery, mic/loopback recording workers
- :mod:`transcription` — transcription/translation client management and callbacks
"""
import logging
import threading
from typing import Callable, Optional

from .base import Source
from .whisperlive_manager import WhisperLiveManager
from .audio_recorder import (
    record_mic_simple,
    record_loopback_simple,
    stream_mic_to_whisperlive,
    stream_loopback_to_whisperlive,
    find_audio_device_index,
    update_volume,
)
from .transcription import TranscriptionProcessor

logger = logging.getLogger(__name__)


class SoundSource(Source):
    def __init__(self, config=None, session_manager=None):
        self.config = config or {}
        self.session_manager = session_manager
        self.is_recording = False
        self._record_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.realtime_transcription = True

        # Delegates
        self._wl_manager = WhisperLiveManager()
        self._transcription = TranscriptionProcessor(self.config, session_manager)

        # Volume metering state
        self._volume_state: dict = {"max_observed_vol": 500.0}

        # Simple recording state
        self._audio_frames_dict: dict = {"mic": [], "loopback": []}
        self._sample_rate: int | None = None
        self._sample_width: int | None = None

    @property
    def correction_engine(self):
        """Proxy for backward compatibility — delegates to TranscriptionProcessor."""
        return self._transcription.correction_engine

    @correction_engine.setter
    def correction_engine(self, value):
        self._transcription.correction_engine = value

    def warmup(self):
        if not TranscriptionProcessor.is_client_available():
            logger.error("WhisperLive client not imported. Cannot perform warmup.")
            return

        logger.info("Warming up SoundSource...")
        self._wl_manager.warmup(self.config)

    @property
    def name(self):
        return "audio"

    def get_text(self, *args, **kwargs) -> str:
        return self._transcription.last_transcription_text

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
        self._audio_frames_dict = {"mic": [], "loopback": []}
        self._volume_state = {"max_observed_vol": 500.0}
        self._transcription.reset()

        # Override transcription setting if explicitly provided
        if enable_transcription is not None:
            self.realtime_transcription = enable_transcription
        else:
            self.realtime_transcription = self.config.get("realtime_transcription", True)

        if self.realtime_transcription and not TranscriptionProcessor.is_client_available():
            logger.error("Cannot start transcription: WhisperLive client is not available.")
            if status_callback:
                status_callback("Error: Transcription client not found.")
            return

        device_name = self.config.get("audio_input_device_name", "Default Device")
        loopback_name = self.config.get("audio_loopback_device_name")
        if status_callback:
            if loopback_name:
                status_callback(f"Starting recording on {device_name} & {loopback_name}...")
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
                target=self._record_only_worker,
                args=(status_callback,),
                daemon=True,
            )

        self._record_thread.start()

    # ------------------------------------------------------------------
    # Recording workers
    # ------------------------------------------------------------------
    def _record_only_worker(self, status_callback=None):
        """Records audio without streaming it to WhisperLive."""
        loopback_name = self.config.get("audio_loopback_device_name")

        threads = []

        def _mic_worker():
            sr, sw = record_mic_simple(
                self.config,
                self._stop_event,
                self._audio_frames_dict,
                self._volume_state,
                status_callback,
            )
            self._sample_rate = sr
            self._sample_width = sw

        t1 = threading.Thread(target=_mic_worker)
        threads.append(t1)
        t1.start()

        if loopback_name:
            t2 = threading.Thread(
                target=record_loopback_simple,
                args=(
                    self.config,
                    self._stop_event,
                    self._audio_frames_dict,
                    getattr(self, "_sample_rate", 16000) or 16000,
                    status_callback,
                ),
            )
            threads.append(t2)
            t2.start()

        for t in threads:
            t.join()

        logger.info("Simple recording loops stopped.")
        self.is_recording = False

    def _record_and_transcribe_worker(self, status_callback=None):
        """Streams audio to WhisperLive for real-time transcription."""
        if not self._wl_manager.ensure_service(self.config):
            self.is_recording = False
            return

        if not self._transcription.initialize_clients():
            self.is_recording = False
            return

        timeout = 600 if self._transcription._translation_language else 15
        if not self._transcription.wait_for_clients_ready(
            timeout=timeout, status_callback=status_callback
        ):
            self.is_recording = False
            return

        logger.info("WhisperLive clients initialized and recording.")
        self._transcription.write_transcription_separator()

        loopback_name = self.config.get("audio_loopback_device_name")

        threads = []
        try:
            if self._transcription.client_mic:
                t1 = threading.Thread(
                    target=stream_mic_to_whisperlive,
                    args=(
                        self.config,
                        self._stop_event,
                        self._transcription.client_mic,
                        self._volume_state,
                        self.session_manager,
                        status_callback,
                    ),
                )
                threads.append(t1)
                t1.start()
            if self._transcription.client_loopback and loopback_name:
                t2 = threading.Thread(
                    target=stream_loopback_to_whisperlive,
                    args=(
                        self.config,
                        self._stop_event,
                        self._transcription.client_loopback,
                        self.session_manager,
                        status_callback,
                    ),
                )
                threads.append(t2)
                t2.start()

            for t in threads:
                t.join()
        finally:
            logger.info("Recording loops stopped.")
            self._transcription.cleanup_clients()
            self.is_recording = False

    # ------------------------------------------------------------------
    # Stop / cleanup
    # ------------------------------------------------------------------
    def _stop_recording_thread(self):
        """Stop recording thread."""
        self._stop_event.set()
        if self._record_thread:
            self._record_thread.join(timeout=3.0)
            if self._record_thread.is_alive():
                logger.warning("Recording thread did not terminate in time.")

    def stop_recording(self) -> str:
        if not self.is_recording:
            return ""

        self._stop_recording_thread()

        self.is_recording = False
        logger.info("Recording stopped.")

        from core.ui.signals import ui_signals

        ui_signals.update_volume.emit(0)

        if self.realtime_transcription:
            return self._transcription.finalize_all()
        else:
            return TranscriptionProcessor.process_simple_recording(
                self._audio_frames_dict,
                self.config,
                self._sample_rate,
                self._sample_width,
            )

    def __del__(self):
        self._wl_manager.cleanup()
