"""Audio device discovery, capture workers, and volume metering.

Contains the low-level recording logic for both simple (record-only) and
streaming (WhisperLive) modes, for both microphone and system loopback
devices.
"""
import logging
import os
import tempfile
import threading
import wave
from typing import Callable, Optional

import numpy as np
import pyaudio
import resampy
import speech_recognition as sr

from core.output import show_subtitle

logger = logging.getLogger(__name__)


def find_audio_device_index(device_name: str | None) -> int | None:
    """Find audio device index by name. Returns ``None`` if not found."""
    if not device_name:
        return None
    p = pyaudio.PyAudio()
    try:
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["name"] == device_name and info["maxInputChannels"] > 0:
                return i
    finally:
        p.terminate()
    return None


def handle_stream_error(
    e: Exception,
    device_name: str,
    source_type: str,
    status_callback: Optional[Callable[[str], None]] = None,
):
    """Classify and report an audio stream error."""
    error_str = str(e).lower()
    err_msg = ""

    if "unanticipated host error" in error_str or "-9999" in error_str:
        err_msg = f"Device Disconnected: {device_name} ({source_type}) was unplugged or lost."
    elif "device unavailable" in error_str or "-9985" in error_str:
        err_msg = f"Device Unavailable: {device_name} ({source_type}) is in use or disconnected."
    elif "invalid input device" in error_str or "-9996" in error_str:
        err_msg = f"Invalid Device: {device_name} ({source_type}) cannot be opened."
    elif "input overflowed" in error_str or "-9981" in error_str:
        logger.warning(f"Audio input overflow on {device_name} ({source_type})")
        return
    elif "access denied" in error_str or "permission" in error_str:
        err_msg = f"Permission Denied: Cannot access {device_name} ({source_type}). Check OS privacy settings."
    else:
        err_msg = f"Audio Stream Error on {device_name} ({source_type}): {e}"

    logger.error(err_msg)
    if status_callback:
        status_callback(f"Error: {err_msg}")

    show_subtitle(f"⚠️ {err_msg}")


def update_volume(data: bytes, volume_state: dict):
    """Calculate and broadcast audio volume for UI.

    *volume_state* must be a mutable dict with a ``max_observed_vol`` key
    (initialised to ``500.0``).
    """
    from core.ui.signals import ui_signals

    audio_data = np.frombuffer(data, dtype=np.int16)
    if len(audio_data) > 0:
        vol = np.abs(audio_data.astype(np.float32)).max()

        # Keep a running max of the volume to auto-normalize
        volume_state["max_observed_vol"] = max(volume_state.get("max_observed_vol", 500.0), vol)

        # Slowly decay so it adapts if volume decreases; floor at 500.0
        volume_state["max_observed_vol"] = max(500.0, volume_state["max_observed_vol"] * 0.995)

        scaled_vol = int((vol / volume_state["max_observed_vol"]) * 100)
        scaled_vol = min(100, max(0, scaled_vol))

        ui_signals.update_volume.emit(scaled_vol)


def _get_enhancer(config: dict, sample_rate: int):
    """Create an AudioEnhancer if enhancement is enabled, else ``None``."""
    if config.get("enable_audio_enhancement", False):
        from .audio_processing import AudioEnhancer

        return AudioEnhancer(sample_rate=sample_rate)
    return None


# ---------------------------------------------------------------------------
# Simple recording workers (no WhisperLive)
# ---------------------------------------------------------------------------
def record_mic_simple(
    config: dict,
    stop_event: threading.Event,
    audio_frames_dict: dict,
    volume_state: dict,
    status_callback: Optional[Callable[[str], None]] = None,
) -> tuple[int | None, int | None]:
    """Record microphone audio without streaming to WhisperLive.

    Returns ``(sample_rate, sample_width)`` from the opened microphone.
    """
    device_name = config.get("audio_input_device_name")
    device_index = find_audio_device_index(device_name)
    sample_rate = None
    sample_width = None

    fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with sr.Microphone(device_index=device_index) as source:
            sample_rate = source.SAMPLE_RATE
            sample_width = source.SAMPLE_WIDTH
            stream = source.stream
            logger.info(f"Microphone {device_name} opened for simple recording.")

            enhancer = _get_enhancer(config, sample_rate)

            with wave.open(temp_wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(sample_width)
                wf.setframerate(sample_rate)
                while not stop_event.is_set():
                    data = stream.read(source.CHUNK)

                    if enhancer:
                        audio_array = (
                            np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                        )
                        audio_array = enhancer.enhance(audio_array)
                        data = (audio_array * 32767).astype(np.int16).tobytes()

                    audio_frames_dict["mic"].append(data)
                    update_volume(data, volume_state)
                    wf.writeframes(data)
    except Exception as e:
        handle_stream_error(e, str(device_name), "mic", status_callback)

    return sample_rate, sample_width


def record_loopback_simple(
    config: dict,
    stop_event: threading.Event,
    audio_frames_dict: dict,
    fallback_sample_rate: int = 16000,
    status_callback: Optional[Callable[[str], None]] = None,
):
    """Record system loopback audio without streaming to WhisperLive."""
    loopback_name = config.get("audio_loopback_device_name")
    if not loopback_name:
        return

    import soundcard as sc

    speaker_name = loopback_name
    try:
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

        sample_rate = fallback_sample_rate or 16000
        logger.info(f"Loopback {loopback_name} opened for simple recording.")

        enhancer = _get_enhancer(config, sample_rate)

        with loopback_device.recorder(samplerate=sample_rate, channels=1) as mic:
            while not stop_event.is_set():
                data = mic.record(numframes=1024)
                audio_array = data.flatten()

                if enhancer:
                    audio_array = enhancer.enhance(audio_array.astype(np.float32))

                int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                audio_frames_dict["loopback"].append(int16_data)
    except Exception as e:
        handle_stream_error(e, str(speaker_name), "loopback", status_callback)


# ---------------------------------------------------------------------------
# WhisperLive streaming workers
# ---------------------------------------------------------------------------
def stream_mic_to_whisperlive(
    config: dict,
    stop_event: threading.Event,
    transcription_client,
    volume_state: dict,
    session_manager=None,
    status_callback: Optional[Callable[[str], None]] = None,
):
    """Stream microphone audio to WhisperLive for real-time transcription."""
    device_name = config.get("audio_input_device_name")
    device_index = find_audio_device_index(device_name)

    wav_file = None
    if config.get("post_recording_diarization", False) and session_manager:
        session_dir = session_manager.get_session_dir(session_manager.current_session_id)
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
            logger.info(f"Microphone {device_name} opened. Sample rate: {source_sample_rate}Hz.")

            if wav_file:
                wav_file.setframerate(target_sample_rate)

            enhancer = _get_enhancer(config, target_sample_rate)

            while not stop_event.is_set():
                data = stream.read(source.CHUNK)
                update_volume(data, volume_state)
                audio_array = (
                    np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                )
                if source_sample_rate != target_sample_rate:
                    audio_array = resampy.resample(
                        audio_array, source_sample_rate, target_sample_rate
                    )

                if enhancer:
                    audio_array = enhancer.enhance(audio_array)

                transcription_client.client.send_packet_to_server(audio_array.tobytes())

                if wav_file:
                    int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                    wav_file.writeframes(int16_data)
    except Exception as e:
        handle_stream_error(e, str(device_name), "mic", status_callback)
    finally:
        if wav_file:
            wav_file.close()


def stream_loopback_to_whisperlive(
    config: dict,
    stop_event: threading.Event,
    transcription_client,
    session_manager=None,
    status_callback: Optional[Callable[[str], None]] = None,
):
    """Stream system loopback audio to WhisperLive for real-time transcription."""
    device_name = config.get("audio_loopback_device_name")
    if not transcription_client or not device_name:
        return

    wav_file = None
    if config.get("post_recording_diarization", False) and session_manager:
        session_dir = session_manager.get_session_dir(session_manager.current_session_id)
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

        enhancer = _get_enhancer(config, target_sample_rate)

        logger.info(f"Loopback device {device_name} opened.")
        with loopback_device.recorder(samplerate=target_sample_rate, channels=1) as mic:
            while not stop_event.is_set():
                data = mic.record(numframes=4096)
                audio_array = data.flatten().astype(np.float32)

                if enhancer:
                    audio_array = enhancer.enhance(audio_array)

                transcription_client.client.send_packet_to_server(audio_array.tobytes())

                if wav_file:
                    int16_data = (audio_array * 32767).astype(np.int16).tobytes()
                    wav_file.writeframes(int16_data)
    except Exception as e:
        handle_stream_error(e, str(device_name), "loopback", status_callback)
    finally:
        if wav_file:
            wav_file.close()
