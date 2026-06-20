"""Real-time correction engine — analyzes transcribed speech mid-recording.

Accumulates finalized transcription sentences into a rolling window and
periodically sends them to an LLM for fact-checking, grammar correction,
and/or content suggestions.  Results are emitted via UISignals so the
CorrectionPanelWidget can display them without blocking the recording thread.
"""
import hashlib
import json
import logging
import threading
import time
from typing import Optional

from core.llm.base import LLMEngine
from core.sinks.base import Sink

logger = logging.getLogger(__name__)


class _NullSink(Sink):
    """A no-op sink that discards all chunks.

    Used by the correction engine so that LLM engines that require a
    non-None sink (like GoogleGenAIEngine with its ``assert sink is not None``)
    can stream normally while the full response text is still returned.
    """

    def process_chunk(self, chunk: str, is_main: bool = True, replace: bool = False):
        pass

# Prompt IDs in prompts.json for each correction type
_PROMPT_IDS: dict[str, str] = {
    "fact_check": "correction_fact_check",
    "grammar": "correction_grammar",
    "content_suggestion": "correction_content_suggestions",
}

# Config keys that enable each correction type
_CONFIG_KEYS: dict[str, str] = {
    "fact_check": "realtime_correction_fact_check",
    "grammar": "realtime_correction_grammar",
    "content_suggestion": "realtime_correction_content_suggestions",
}


def _load_prompt_text(prompts: list[dict], prompt_id: str) -> str:
    """Look up a prompt's text by its ``id`` inside the prompts list."""
    for p in prompts:
        if p.get("id") == prompt_id:
            return p.get("text", "")
    return ""


def _window_hash(sentences: list[str]) -> str:
    """Return a short hash for a list of sentences (deduplication key)."""
    raw = "|".join(sentences)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _parse_corrections(raw_text: str) -> list[dict]:
    """Best-effort extraction of a JSON array from LLM output."""
    text = raw_text.strip()
    # Strip markdown fences
    text = text.replace("```json", "").replace("```", "").strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        logger.warning("[CorrectionEngine] Failed to parse LLM response as JSON")
        return []


class CorrectionEngine:
    """Orchestrates real-time LLM corrections during audio recording."""

    def __init__(
        self,
        config: dict,
        llm_engine: LLMEngine,
        prompts: list[dict],
        session_manager=None,
    ):
        self.config = config
        self.llm_engine = llm_engine
        self.prompts = prompts
        self.session_manager = session_manager

        self._window_size: int = config.get("realtime_correction_window_size", 4)
        self._sentence_buffer: list[str] = []
        self._processed_hashes: set[str] = set()
        self._corrections: list[dict] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Which audio source(s) to apply corrections to: "both", "mic", "loopback"
        self._audio_source: str = config.get("realtime_correction_audio_source", "both")

        # Determine which correction types are enabled
        self._enabled_types: list[str] = []
        for ctype, config_key in _CONFIG_KEYS.items():
            if config.get(config_key, False):
                self._enabled_types.append(ctype)

        logger.info(
            "[CorrectionEngine] Initialized with window_size=%d, "
            "audio_source=%s, enabled_types=%s",
            self._window_size,
            self._audio_source,
            self._enabled_types,
        )

    def on_sentence_finalized(self, text: str, source: str = "mic"):
        """Called by SoundSource when an utterance segment is finalized."""
        if not text.strip() or not self._enabled_types:
            logger.debug(
                "[CorrectionEngine] Skipping: text=%r, enabled_types=%s",
                text.strip()[:50], self._enabled_types,
            )
            return

        # Filter by configured audio source
        if self._audio_source != "both" and source != self._audio_source:
            logger.debug(
                "[CorrectionEngine] Ignoring source '%s' (configured for '%s' only)",
                source, self._audio_source,
            )
            return

        logger.info(
            "[CorrectionEngine] Sentence finalized (%s): %s",
            source, text.strip()[:80],
        )

        window = None
        with self._lock:
            self._sentence_buffer.append(text.strip())
            logger.info(
                "[CorrectionEngine] Buffer size: %d / %d",
                len(self._sentence_buffer), self._window_size,
            )

            if len(self._sentence_buffer) >= self._window_size:
                window = list(self._sentence_buffer)
                self._sentence_buffer.clear()

                h = _window_hash(window)
                if h in self._processed_hashes:
                    logger.info("[CorrectionEngine] Duplicate window, skipping")
                    return
                self._processed_hashes.add(h)

        if window is None:
            return

        # Fire background evaluation — don't block the recording thread
        logger.info(
            "[CorrectionEngine] Evaluating window of %d sentences", len(window),
        )
        threading.Thread(
            target=self._evaluate_window,
            args=(window,),
            daemon=True,
        ).start()

    def _evaluate_window(self, sentences: list[str]):
        """Run LLM evaluation for a window of sentences."""
        if self._stop_event.is_set():
            return

        transcript_block = " ".join(sentences)
        all_corrections: list[dict] = []

        for ctype in self._enabled_types:
            if self._stop_event.is_set():
                break

            prompt_id = _PROMPT_IDS.get(ctype, "")
            system_prompt = _load_prompt_text(self.prompts, prompt_id)
            if not system_prompt:
                logger.warning(
                    "[CorrectionEngine] No prompt found for type '%s' (id='%s')",
                    ctype,
                    prompt_id,
                )
                continue

            full_prompt = f"{system_prompt}\n\nTranscript:\n\"{transcript_block}\""

            try:
                logger.info(
                    "[CorrectionEngine] Calling LLM for type '%s', transcript: %s",
                    ctype, transcript_block[:100],
                )
                raw_response = self.llm_engine.process_text(
                    full_prompt,
                    status_callback=None,
                    enable_chat_sessions=False,
                    sink=_NullSink(),
                    is_main=True,
                )

                logger.info(
                    "[CorrectionEngine] LLM response for '%s': %s",
                    ctype, (raw_response or "")[:200],
                )

                parsed = _parse_corrections(raw_response)
                logger.info(
                    "[CorrectionEngine] Parsed %d corrections for '%s'",
                    len(parsed), ctype,
                )
                for item in parsed:
                    correction = {
                        "timestamp": time.time(),
                        "type": item.get("type", ctype),
                        "original": item.get("original", ""),
                        "correction": item.get("correction", ""),
                        "confidence": item.get("confidence", "MEDIUM"),
                        "explanation": item.get("explanation", ""),
                        "source_sentences": sentences,
                    }
                    all_corrections.append(correction)

            except Exception as e:
                logger.error(
                    "[CorrectionEngine] LLM call failed for type '%s': %s",
                    ctype,
                    e,
                    exc_info=True,
                )

        if not all_corrections:
            return

        # Store and emit
        with self._lock:
            self._corrections.extend(all_corrections)

        # Emit each correction to the UI via signals
        try:
            from core.ui.signals import ui_signals
            for correction in all_corrections:
                ui_signals.show_correction.emit(correction)
        except Exception as e:
            logger.error("[CorrectionEngine] Failed to emit correction signal: %s", e)

    def get_corrections(self) -> list[dict]:
        """Return all corrections accumulated during this recording session."""
        with self._lock:
            return list(self._corrections)

    def reset(self):
        """Reset state for a new recording session."""
        with self._lock:
            self._sentence_buffer.clear()
            self._processed_hashes.clear()
            self._corrections.clear()
        self._stop_event.clear()
        logger.info("[CorrectionEngine] State reset for new session")

    def stop(self):
        """Signal the engine to stop processing (called when recording stops)."""
        self._stop_event.set()
