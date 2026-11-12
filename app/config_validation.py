"""Profile validation: known engines, and a way to read images (vision model or OCR)."""

import json
import logging
import os

from app.context import DEFAULT_MODEL_NAME, model_or_none

logger = logging.getLogger(__name__)

DEFAULT_LLM_ENGINE = "claude-code"
OCR_ENGINES = ("none", "paddleocr", "remote_paddle")

_MODELS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "llm_models.json",
)


def load_models_data() -> dict:
    """The LLM model registry (config/llm_models.json): engine -> list of models."""
    try:
        with open(_MODELS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not load llm_models.json: %s", e)
        return {}


def fallback_engine_type(profile: dict) -> str:
    """The fallback model's engine: its own ``fallback_llm_engine``, else the main one."""
    return profile.get("fallback_llm_engine") or profile.get(
        "llm_engine", DEFAULT_LLM_ENGINE
    )


def _has_vision(models_data: dict, engine: str, model_id: str) -> bool:
    # "supports_ocr" in llm_models.json means the model reads images itself.
    return any(
        m.get("id") == model_id and m.get("supports_ocr", False)
        for m in models_data.get(engine, [])
    )


def profile_problems(profile: dict, models_data: dict | None = None) -> list[str]:
    """Everything that stops this profile from working; empty when it is usable."""
    from app.engine_init import LLM_ENGINE_TYPES

    if models_data is None:
        models_data = load_models_data()
    problems = []
    ocr_type = profile.get("ocr_engine", "none")
    if ocr_type not in OCR_ENGINES:
        problems.append(f"Unknown ocr_engine '{ocr_type}' (use one of {OCR_ENGINES}).")

    checks = [
        (
            "Model",
            profile.get("llm_engine", DEFAULT_LLM_ENGINE),
            profile.get("model", DEFAULT_MODEL_NAME),
        )
    ]
    fallback = model_or_none(profile.get("fallback_model"))
    if fallback:
        checks.append(("Fallback model", fallback_engine_type(profile), fallback))

    for label, engine, model_id in checks:
        if engine not in LLM_ENGINE_TYPES:
            problems.append(
                f"{label} '{model_id}': unknown engine '{engine}' "
                f"(use one of {sorted(LLM_ENGINE_TYPES)})."
            )
        elif ocr_type == "none" and not _has_vision(models_data, engine, model_id):
            problems.append(
                f"{label} '{model_id}' cannot read images and the profile has no "
                "OCR engine. Set ocr_engine, or pick a model that supports images."
            )
    return problems
