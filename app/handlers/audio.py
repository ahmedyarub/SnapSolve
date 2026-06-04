"""Audio recording handlers — start and stop recording."""
import threading

from core.sources import SoundSource, get_active_source_instance


def handle_start_record(config, enable_transcription):
    """Start audio recording on the active SoundSource."""
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    def status_update(msg):
        from core.output import ui_signals

        if "popup" in config.get("output_mode", ["popup"]):
            ui_signals.show_popup.emit(
                {
                    "text": msg,
                    "auto_close": 3000,
                    "opacity": config.get("opacity", 0.8),
                    "is_result": False,
                }
            )

    active_source.start_recording(
        status_callback=status_update, enable_transcription=enable_transcription
    )


def handle_stop_record(config, active_profile, _active_prompt_text, is_long_press):
    """Stop audio recording and optionally send transcription to LLM."""
    active_source = get_active_source_instance()
    if not isinstance(active_source, SoundSource):
        return

    from core.output import ui_signals

    def status_update(msg):
        if "popup" in config.get("output_mode", ["popup"]):
            ui_signals.show_popup.emit(
                {
                    "text": msg,
                    "auto_close": None,
                    "opacity": config.get("opacity", 0.8),
                    "is_result": False,
                }
            )

    status_update("Processing audio...")

    def _process_audio():
        assert active_source is not None
        assert isinstance(active_source, SoundSource)
        text = active_source.stop_recording()

        if not is_long_press:
            status_update("Transcription stopped.")
            from core.output import clear_subtitles

            clear_subtitles()
            return

        if not text:
            status_update("No speech recognized.")
            return

        print(f"Recognized Speech: {text}")
        status_update(f"Recognized: {text}\nSending to LLM...")

        from app.handlers.text import handle_text_submit

        handle_text_submit(config, active_profile, text)

    threading.Thread(target=_process_audio, daemon=True).start()
