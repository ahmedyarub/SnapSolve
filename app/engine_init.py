"""Building the engines a profile needs: LLM (main, fallback, correction), OCR, audio."""

import logging
import os
import subprocess
import sys
import threading

from app.config_validation import DEFAULT_LLM_ENGINE, fallback_engine_type
from app.context import DEFAULT_MODEL_NAME, model_or_none
from core.llm import (
    AntigravityEngine,
    ClaudeCodeEngine,
    GeminiCLIEngine,
    GoogleGenAIEngine,
    LiteLLMEngine,
    OllamaEngine,
)
from core.sinks import AudioSink
from core.sources import SoundSource
from core.sources.ocr import LocalPaddleOCREngine, NoOCREngine, RemotePaddleOCREngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OCR engine
# ---------------------------------------------------------------------------
def build_ocr_engine(profile: dict, config: dict):
    """The OCR engine the profile asks for (warmed up if the config says so)."""
    ocr_type = profile.get("ocr_engine", "none")

    def report(msg: str) -> None:
        logger.info("OCR init: %s", msg)

    if ocr_type == "paddleocr":
        ocr_engine = LocalPaddleOCREngine(status_callback=report)
    elif ocr_type == "remote_paddle":
        ocr_engine = RemotePaddleOCREngine(
            config=config.get("ocr_config", {}), status_callback=report
        )
    else:
        ocr_engine = NoOCREngine()

    if config.get("warmup_ocr", True) and hasattr(ocr_engine, "warmup"):
        ocr_engine.warmup()
    return ocr_engine


# ---------------------------------------------------------------------------
# LLM engines
# ---------------------------------------------------------------------------
def _ollama(model, config, manager):
    return OllamaEngine(
        model,
        config.get("ollama_url", "http://localhost:11434"),
        session_manager=manager,
    )


def _google_genai(model, config, manager):
    return GoogleGenAIEngine(
        model, config.get("gemini_api_key", ""), session_manager=manager
    )


def _antigravity(model, config, manager):
    return AntigravityEngine(
        model,
        config.get("antigravity_service_url", "http://localhost:8200"),
        session_manager=manager,
    )


def _litellm(model, config, manager):
    return LiteLLMEngine(model, config, session_manager=manager)


def _gemini_cli(model, _config, manager):
    return GeminiCLIEngine(model, session_manager=manager)


def _claude_code(model, config, manager):
    return ClaudeCodeEngine(model, config, session_manager=manager)


_LLM_FACTORIES = {
    "claude-code": _claude_code,
    "ollama": _ollama,
    "google-genai": _google_genai,
    "antigravity": _antigravity,
    "litellm": _litellm,
    "gemini": _gemini_cli,
}
LLM_ENGINE_TYPES = frozenset(_LLM_FACTORIES)


def create_llm_engine(llm_type: str, model: str, config: dict, session_manager):
    """Build one LLM engine instance; an unknown type is an error."""
    factory = _LLM_FACTORIES.get(llm_type)
    if factory is None:
        raise ValueError(
            f"Unknown llm_engine '{llm_type}' (use one of {sorted(LLM_ENGINE_TYPES)})"
        )
    return factory(model, config, session_manager)


def build_llm_engines(profile: dict, config: dict, manager):
    """The main and (optional) fallback engines. The fallback may use another
    provider (``fallback_llm_engine``), so one provider's outage is covered."""
    llm_type = profile.get("llm_engine", DEFAULT_LLM_ENGINE)
    model = profile.get("model", DEFAULT_MODEL_NAME)
    logger.info("Initializing %s engine (%s)...", llm_type, model)
    main = create_llm_engine(llm_type, model, config, manager)

    fallback = None
    fallback_model = model_or_none(profile.get("fallback_model"))
    if fallback_model:
        fallback_type = fallback_engine_type(profile)
        logger.info(
            "Initializing fallback %s engine (%s)...", fallback_type, fallback_model
        )
        fallback = create_llm_engine(fallback_type, fallback_model, config, manager)
    return main, fallback


def build_correction_engine(profile: dict, config: dict, manager, prompts):
    """The real-time correction engine with its own LLM instance, or None if off."""
    if not config.get("realtime_correction_enabled", False):
        return None

    correction_model = model_or_none(profile.get("correction_model")) or profile.get(
        "model", DEFAULT_MODEL_NAME
    )
    llm_type = profile.get("llm_engine", DEFAULT_LLM_ENGINE)
    # Dedicated instance; corrections don't need session history
    correction_llm = create_llm_engine(llm_type, correction_model, config, None)

    from core.correction_engine import CorrectionEngine

    engine = CorrectionEngine(config, correction_llm, prompts, session_manager=manager)
    logger.info(
        "Correction engine ready: model=%s, engine=%s", correction_model, llm_type
    )
    return engine


def warm_up_llms(config: dict, llm_engine, fallback_llm_engine) -> None:
    """Warm up the fallback engine, or the main one if that fails or is absent."""
    if not config.get("warmup_llm", True):
        return

    def report(msg: str) -> None:
        logger.info("LLM warmup: %s", msg)

    warmed = False
    if fallback_llm_engine:
        warmed = fallback_llm_engine.warmup(status_callback=report)
    if not warmed and llm_engine:
        llm_engine.warmup(status_callback=report)


# ---------------------------------------------------------------------------
# Audio components
# ---------------------------------------------------------------------------
def build_audio_sink(config: dict, manager, cancel_event):
    """The TTS sink, plus background warmups the config asks for."""
    audio_sink = AudioSink(config, cancel_event)

    if config.get("warmup_tts", False) and hasattr(audio_sink, "warmup"):
        threading.Thread(
            target=audio_sink.warmup, daemon=True, name="tts-warmup"
        ).start()

    if config.get("warmup_speech_recognition", True):
        temp_sr = SoundSource(config, session_manager=manager)
        threading.Thread(target=temp_sr.warmup, daemon=True, name="sr-warmup").start()

    if config.get("warmup_realtime_transcription", False):
        warmup_whisperlive_process()

    return audio_sink


# ---------------------------------------------------------------------------
# WhisperLive warmup
# ---------------------------------------------------------------------------
def _relay_output(stream, label: str) -> None:
    for line in iter(stream.readline, ""):
        logger.info("[WhisperLive warmup%s] %s", label, line.strip())
    stream.close()


def _run_warmup_process(script_path: str) -> None:
    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )
        readers = [
            threading.Thread(
                target=_relay_output, args=(process.stdout, ""), daemon=True
            ),
            threading.Thread(
                target=_relay_output, args=(process.stderr, " ERR"), daemon=True
            ),
        ]
        for reader in readers:
            reader.start()
        process.wait()
        for reader in readers:
            reader.join()
        if process.returncode == 0:
            logger.info("Real-time transcription warmup completed.")
        else:
            logger.warning(
                "Real-time transcription warmup failed with code %s", process.returncode
            )
    except OSError:
        logger.exception("Could not run the real-time transcription warmup")


def warmup_whisperlive_process() -> None:
    """Run tests/sanity/test_whisperlive_warmup.py in the background as a warmup."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests",
        "sanity",
        "test_whisperlive_warmup.py",
    )
    if not os.path.exists(script_path):
        logger.warning("Real-time transcription warmup script not found.")
        return
    logger.info("Running real-time transcription warmup...")
    threading.Thread(
        target=_run_warmup_process, args=(script_path,), daemon=True, name="wl-warmup"
    ).start()
