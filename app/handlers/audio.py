"""Audio recording handlers — start and stop recording."""

import contextlib
import logging
import os
import threading

from app.context import AppContext
from core.sources import SoundSource, get_active_source_instance

logger = logging.getLogger(__name__)

DIARIZATION_URL = "http://127.0.0.1:8001/diarize"
DIARIZATION_TIMEOUT_S = 900  # long recordings take minutes on the GPU


def _popup_status(ctx: AppContext, auto_close: int | None):
    from core.output import ui_signals

    def status_update(msg: str) -> None:
        if "popup" in ctx.config.get("output_mode", ["popup"]):
            ui_signals.show_popup.emit(
                {
                    "text": msg,
                    "auto_close": auto_close,
                    "opacity": ctx.config.get("opacity", 0.8),
                    "is_result": False,
                }
            )

    return status_update


def handle_start_record(ctx: AppContext, enable_transcription):
    """Start audio recording on the active SoundSource."""
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    active_source.start_recording(
        status_callback=_popup_status(ctx, 3000),
        enable_transcription=enable_transcription,
    )

    if ctx.correction_engine:
        ctx.correction_engine.reset()
        active_source.correction_engine = ctx.correction_engine
        from core.ui.signals import ui_signals

        ui_signals.clear_corrections.emit()


def _run_diarization(ctx: AppContext, session_dir: str) -> None:
    """Send the session's recordings to the diarization service; save its transcript."""
    import requests

    config = ctx.config
    mic_path = os.path.join(session_dir, "audio_mic.wav")
    loopback_path = os.path.join(session_dir, "audio_loopback.wav")
    data = {
        "speaker_name": config.get("speaker_name", "interviewer"),
        "model": config.get("diarization_model", "base"),
    }
    try:
        # The handles must close even if the POST fails, or Windows keeps the
        # WAVs locked and the cleanup below cannot delete them.
        with contextlib.ExitStack() as stack:
            files = {}
            if os.path.exists(mic_path):
                files["audio_mic"] = stack.enter_context(open(mic_path, "rb"))
            if os.path.exists(loopback_path):
                files["audio_loopback"] = stack.enter_context(open(loopback_path, "rb"))
            if not files:
                return
            response = requests.post(
                DIARIZATION_URL, files=files, data=data, timeout=DIARIZATION_TIMEOUT_S
            )
    except requests.RequestException as e:
        logger.error("Diarization service failed: %s", e)
        return

    if response.status_code != 200:
        logger.error("Diarization service returned HTTP %s", response.status_code)
        return

    segments = response.json().get("segments", [])
    if segments:
        with open(
            os.path.join(session_dir, "transcription.txt"), "w", encoding="utf-8"
        ) as f:
            for seg in segments:
                f.write(f"[{seg['speaker']}] {seg['text']}\n")

    if config.get("delete_wav_after_diarization", True):
        for path in (mic_path, loopback_path):
            with contextlib.suppress(OSError):
                os.remove(path)

    if ctx.session_manager:
        ctx.session_manager.index_session(ctx.session_manager.current_session_id)


def _summarize_transcription(ctx: AppContext, status_update) -> None:
    manager = ctx.session_manager
    full_transcription = manager.get_full_transcription() if manager else None
    if not full_transcription:
        return
    prompt_prefix = ctx.config.get(
        "summarize_transcription_prompt",
        "Summarize the following transcribed conversation:\n",
    )
    status_update("Summarizing transcription...")
    session_id = manager.current_session_id

    def on_summary(summary_text):
        if ctx.config.get("webhook_trigger_on_summary", False):
            from core.webhook import trigger_webhook

            trigger_webhook(ctx.config, session_id, summary_text)

    from app.handlers.text import handle_text_submit

    handle_text_submit(
        ctx,
        f"{prompt_prefix}\n\n{full_transcription}",
        source_name="audio",
        post_action=on_summary,
    )


def handle_stop_record(ctx: AppContext, is_long_press):
    """Stop audio recording and optionally send the transcription to the LLM."""
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    status_update = _popup_status(ctx, None)
    status_update("Processing audio...")

    def process_audio() -> None:
        text = active_source.stop_recording()

        # Save any accumulated corrections to the session
        if ctx.correction_engine:
            ctx.correction_engine.stop()
            corrections = ctx.correction_engine.get_corrections()
            if corrections and ctx.session_manager:
                ctx.session_manager.append_corrections(corrections)
        active_source.correction_engine = None

        manager = ctx.session_manager
        if ctx.config.get("post_recording_diarization", False) and manager:
            session_dir = manager.get_session_dir(manager.current_session_id)
            if session_dir:
                threading.Thread(
                    target=_run_diarization,
                    args=(ctx, session_dir),
                    daemon=True,
                    name="diarization",
                ).start()
                status_update("Diarization sent to service.")

        if not is_long_press:
            status_update("Transcription stopped.")
            from core.output import clear_subtitles

            clear_subtitles()
            if ctx.config.get("auto_summarize_transcription", False):
                _summarize_transcription(ctx, status_update)
            elif manager:
                manager.index_session(manager.current_session_id)
            return

        if not text:
            status_update("No speech recognized.")
            return

        logger.info("Recognized speech (%d chars)", len(text))
        status_update(f"Recognized: {text}\nSending to LLM...")

        from app.handlers.text import handle_text_submit

        handle_text_submit(ctx, text, source_name="audio")

    threading.Thread(target=process_audio, daemon=True, name="stop-record").start()
