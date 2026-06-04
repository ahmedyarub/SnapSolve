"""Configuration validation — model/OCR compatibility checks."""
import json
import os
import sys

from app.state import DEFAULT_MODEL_NAME


def load_models_data():
    """Load the LLM models registry from config/llm_models.json."""
    try:
        models_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "llm_models.json"
        )
        with open(models_path, "r") as f:
            return json.load(f)
    except Exception as models_error:
        print(f"Warning: Could not load llm_models.json: {models_error}")
        return {}


def _check_model_ocr_support(models, model_id):
    """Check if model supports OCR."""
    for m in models:
        if m.get("id") == model_id:
            return m.get("supports_ocr", False)
    return False


def _validate_main_model(active_profile, models_data):
    """Validate main model configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    model_id = active_profile.get("model", DEFAULT_MODEL_NAME)
    ocr_type = active_profile.get("ocr_engine", "none")

    models = models_data.get(llm_type, [])
    supports_ocr = _check_model_ocr_support(models, model_id)

    if not supports_ocr and ocr_type == "none":
        print(
            f"Error: Selected model '{model_id}' does not support built-in OCR and no OCR engine is configured."
        )
        print("Please configure an OCR engine or select a model that supports OCR.")
        sys.exit(1)


def _validate_fallback_model(active_profile, models_data):
    """Validate fallback model configuration."""
    llm_type = active_profile.get("llm_engine", "gemini")
    fallback_model_id = active_profile.get("fallback_model", "None")
    ocr_type = active_profile.get("ocr_engine", "none")

    if not fallback_model_id or fallback_model_id == "None":
        return

    models = models_data.get(llm_type, [])
    fallback_supports_ocr = _check_model_ocr_support(models, fallback_model_id)

    if not fallback_supports_ocr and ocr_type == "none":
        print(
            f"Error: Selected fallback model '{fallback_model_id}' does not support built-in OCR "
            f"and no OCR engine is configured."
        )
        print(
            "Please configure an OCR engine or select a fallback model that supports OCR."
        )
        sys.exit(1)


def validate_config(active_profile):
    """Validate the active profile's model and OCR configuration."""
    models_data = load_models_data()

    _validate_main_model(active_profile, models_data)
    _validate_fallback_model(active_profile, models_data)
