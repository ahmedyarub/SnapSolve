"""Engine initialization — LLM, OCR, audio, and WhisperLive warmup."""
import os
import subprocess
import sys
import threading

from app.state import DEFAULT_MODEL_NAME
from core.llm import OllamaEngine, GeminiCLIEngine, GoogleGenAIEngine, AntigravityEngine
from core.sinks import AudioSink
from core.sources import SoundSource
from core.sources.ocr import LocalPaddleOCREngine, NoOCREngine, RemotePaddleOCREngine


# ---------------------------------------------------------------------------
# OCR engine
# ---------------------------------------------------------------------------
def _initialize_ocr_engine(active_profile, config):
    """Initialize OCR engine based on profile configuration."""
    ocr_type = active_profile.get("ocr_engine", "none")
    if ocr_type == "paddleocr":
        ocr_engine = LocalPaddleOCREngine(
            status_callback=lambda msg: print(f"Init status: {msg}")
        )
    elif ocr_type == "remote_paddle":
        ocr_config = config.get("ocr_config", {})
        ocr_engine = RemotePaddleOCREngine(
            config=ocr_config, status_callback=lambda msg: print(f"Init status: {msg}")
        )
    else:
        ocr_engine = NoOCREngine()

    if config.get("warmup_ocr", True) and hasattr(ocr_engine, "warmup"):
        ocr_engine.warmup()

    return ocr_engine


# ---------------------------------------------------------------------------
# LLM engines
# ---------------------------------------------------------------------------
def _initialize_llm_engines(active_profile, config, manager):
    """Initialize LLM engines based on profile configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    model = active_profile.get("model", DEFAULT_MODEL_NAME)
    fallback_model = active_profile.get("fallback_model", "None")

    # noinspection PyUnusedLocal
    llm_engine = None
    fallback_llm_engine = None

    if llm_type == "ollama":
        print("Initializing Ollama Engine...")
        llm_engine = OllamaEngine(
            model,
            config.get("ollama_url", "http://localhost:11434"),
            session_manager=manager,
        )
        if fallback_model and fallback_model != "None":
            print("Initializing Fallback Ollama Engine (with warmup)...")
            fallback_llm_engine = OllamaEngine(
                fallback_model,
                config.get("ollama_url", "http://localhost:11434"),
                session_manager=manager,
            )
    elif llm_type == "google-genai":
        llm_engine = GoogleGenAIEngine(
            model,
            config.get("gemini_api_key", ""),
            session_manager=manager,
        )
        if fallback_model and fallback_model != "None":
            fallback_llm_engine = GoogleGenAIEngine(
                fallback_model,
                config.get("gemini_api_key", ""),
                session_manager=manager,
            )
    elif llm_type == "antigravity":
        llm_engine = AntigravityEngine(
            model,
            config.get("antigravity_service_url", "http://localhost:8200"),
            session_manager=manager,
        )
        if fallback_model and fallback_model != "None":
            fallback_llm_engine = AntigravityEngine(
                fallback_model,
                config.get("antigravity_service_url", "http://localhost:8200"),
                session_manager=manager,
            )
    else:
        llm_engine = GeminiCLIEngine(model, session_manager=manager)
        if fallback_model and fallback_model != "None":
            fallback_llm_engine = GeminiCLIEngine(
                fallback_model, session_manager=manager
            )

    # Use variables to avoid "unused" warnings
    _ = llm_engine, fallback_llm_engine
    return llm_engine, fallback_llm_engine


def _initialize_correction_engine(active_profile, config, manager, prompts):
    """Initialize the real-time correction engine with its own LLM instance.

    Returns a ``CorrectionEngine`` if correction is enabled and a valid
    correction model is configured, otherwise ``None``.
    """
    if not config.get("realtime_correction_enabled", False):
        return None

    correction_model = active_profile.get("correction_model", "None")
    if not correction_model or correction_model == "None":
        # Fall back to the profile's main model
        correction_model = active_profile.get("model", DEFAULT_MODEL_NAME)

    llm_type = active_profile.get("llm_engine", "google-genai")

    # Create a lightweight LLM engine instance dedicated to corrections
    if llm_type == "ollama":
        correction_llm = OllamaEngine(
            correction_model,
            config.get("ollama_url", "http://localhost:11434"),
            session_manager=None,  # corrections don't need session history
        )
    elif llm_type == "google-genai":
        correction_llm = GoogleGenAIEngine(
            correction_model,
            config.get("gemini_api_key", ""),
            session_manager=None,
        )
    elif llm_type == "antigravity":
        correction_llm = AntigravityEngine(
            correction_model,
            config.get("antigravity_service_url", "http://localhost:8200"),
            session_manager=None,
        )
    else:
        correction_llm = GeminiCLIEngine(correction_model, session_manager=None)

    from core.correction_engine import CorrectionEngine
    engine = CorrectionEngine(config, correction_llm, prompts, session_manager=manager)
    print(f"[CorrectionEngine] Initialized with model={correction_model}, engine={llm_type}")
    return engine


def _perform_llm_warmup(config, llm_engine, fallback_llm_engine):
    """Perform LLM warmup."""

    def warmup_status_cb(msg):
        print(f"Init status: {msg}")

    warmup_success = False
    if config.get("warmup_llm", True):
        if fallback_llm_engine:
            warmup_success = fallback_llm_engine.warmup(
                status_callback=warmup_status_cb
            )

        if not warmup_success and llm_engine:
            llm_engine.warmup(status_callback=warmup_status_cb)


# ---------------------------------------------------------------------------
# Audio components
# ---------------------------------------------------------------------------
def _initialize_audio_components(config, manager, cancel):
    """Initialize audio components."""
    audio_sink = AudioSink(config, cancel)

    if config.get("warmup_tts", False) and hasattr(audio_sink, "warmup"):
        threading.Thread(target=audio_sink.warmup, daemon=True).start()

    if config.get("warmup_speech_recognition", True):
        temp_sr = SoundSource(config, session_manager=manager)
        threading.Thread(target=temp_sr.warmup, daemon=True).start()

    if config.get("warmup_realtime_transcription", False):
        warmup_whisperlive_process(config)

    return audio_sink


# ---------------------------------------------------------------------------
# WhisperLive warmup
# ---------------------------------------------------------------------------
def _read_process_output(process, output_type="stdout"):
    """Read process output in real time."""
    if output_type == "stdout":
        for line in iter(process.stdout.readline, ""):
            print(f"[WhisperLive Warmup] {line.strip()}")
        process.stdout.close()
    else:
        for line in iter(process.stderr.readline, ""):
            print(
                f"[WhisperLive Warmup ERR] {line.strip()}",
                file=sys.stderr,
            )
        process.stderr.close()


def _run_warmup_process(script_path):
    """Run the warmup process and handle its output."""
    try:
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
        )

        # Read stdout and stderr in background threads
        t1 = threading.Thread(
            target=_read_process_output, args=(process, "stdout"), daemon=True
        )
        t2 = threading.Thread(
            target=_read_process_output, args=(process, "stderr"), daemon=True
        )
        t1.start()
        t2.start()

        process.wait()
        t1.join()
        t2.join()

        if process.returncode == 0:
            print("Real-time transcription warmup completed successfully.")
        else:
            print(
                f"Real-time transcription warmup failed with code {process.returncode}"
            )
    except Exception as warmup_error:
        print(f"Error executing warmup script: {warmup_error}")


def warmup_whisperlive_process(_config):
    """Executes the test_whisperlive_warmup script from main thread as a warmup."""
    try:
        # Get path to test_whisperlive_warmup.py
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "tests",
            "sanity",
            "test_whisperlive_warmup.py",
        )
        if os.path.exists(script_path):
            print(
                "Running Real-time transcription warmup (test_whisperlive_warmup.py)..."
            )
            threading.Thread(
                target=_run_warmup_process, args=(script_path,), daemon=True
            ).start()
        else:
            print("Warning: Real-time transcription warmup script not found.")
    except Exception as init_error:
        print(f"Error initializing Real-time transcription warmup: {init_error}")
