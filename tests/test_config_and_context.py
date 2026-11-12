"""Configuration layering, request claiming, profile validation and hotkeys."""

import json
import threading

import pytest

import config.settings as settings
from app.config_validation import profile_problems
from app.context import AppContext, model_or_none


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(settings, "CONFIG_FILE", str(path))
    return path


def test_save_config_never_persists_unchanged_cli_overrides(config_file):
    config_file.write_text(json.dumps({"opacity": 0.5}))
    config = settings.AppConfig(
        {"opacity": 0.5, "gemini_api_key": "from-cli", "continue_last": True},
        cli_overrides={"gemini_api_key": "from-cli", "continue_last": True},
    )
    settings.save_config(config)
    saved = json.loads(config_file.read_text())
    assert "gemini_api_key" not in saved
    assert "continue_last" not in saved
    assert saved["opacity"] == 0.5


def test_save_config_keeps_the_file_value_of_an_overridden_key(config_file):
    config_file.write_text(json.dumps({"api_server_port": 3031}))
    config = settings.AppConfig(
        {"api_server_port": 9999}, cli_overrides={"api_server_port": 9999}
    )
    settings.save_config(config)
    assert json.loads(config_file.read_text())["api_server_port"] == 3031


def test_save_config_persists_an_overridden_key_changed_later(config_file):
    config = settings.AppConfig(
        {"transcription_language": "es"},
        cli_overrides={"transcription_language": "en"},
    )
    settings.save_config(config)  # changed in the UI after startup: a real setting
    assert json.loads(config_file.read_text())["transcription_language"] == "es"


def test_update_config_file_touches_only_the_given_keys(config_file):
    config_file.write_text(json.dumps({"a": 1, "b": 2}))
    settings.update_config_file({"b": 3, "c": 4})
    assert json.loads(config_file.read_text()) == {"a": 1, "b": 3, "c": 4}


def test_mistyped_values_fall_back_to_defaults():
    defaults = {"opacity": 0.8, "enable_api_server": False, "port": 3031, "x": None}
    kept = settings._drop_mistyped(
        {
            "opacity": "high",
            "enable_api_server": 1,
            "port": 3031.0,
            "x": "anything",
            "unknown": [],
        },
        defaults,
    )
    assert kept == {"port": 3031.0, "x": "anything", "unknown": []}


def test_defaults_cover_every_key_in_the_sample_config():
    with open("config/config.sample.json", encoding="utf-8") as f:
        sample = json.load(f)
    assert set(sample) <= set(settings._get_default_config())


def test_exactly_one_request_wins(monkeypatch):
    import app.context as context

    monkeypatch.setattr(context, "_notify_processing", lambda processing: None)
    ctx = AppContext(config={})
    start = threading.Barrier(20)
    wins = []

    def claim():
        start.wait()
        if ctx.try_start_processing():
            wins.append(1)

    threads = [threading.Thread(target=claim) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1
    ctx.cancel_event.set()
    ctx.finish_processing()
    assert not ctx.is_processing and not ctx.cancel_event.is_set()
    assert ctx.try_start_processing()


@pytest.mark.parametrize("value", [None, "", "None", "none", " NONE "])
def test_model_or_none(value):
    assert model_or_none(value) is None


MODELS = {
    "claude-code": [{"id": "claude-opus-5-5", "supports_ocr": True}],
    "ollama": [{"id": "llama3", "supports_ocr": False}],
}


def test_valid_profile_has_no_problems():
    profile = {"llm_engine": "claude-code", "model": "claude-opus-5-5"}
    assert profile_problems(profile, MODELS) == []


def test_unknown_engine_and_ocr_are_reported():
    problems = profile_problems(
        {"llm_engine": "skynet", "model": "x", "ocr_engine": "magic"}, MODELS
    )
    assert any("unknown engine 'skynet'" in p for p in problems)
    assert any("Unknown ocr_engine 'magic'" in p for p in problems)


def test_text_only_model_needs_an_ocr_engine():
    profile = {"llm_engine": "ollama", "model": "llama3", "ocr_engine": "none"}
    assert profile_problems(profile, MODELS)
    assert profile_problems({**profile, "ocr_engine": "remote_paddle"}, MODELS) == []


def test_fallback_on_another_provider_is_checked_against_that_provider():
    profile = {
        "llm_engine": "ollama",
        "model": "llama3",
        "ocr_engine": "paddleocr",
        "fallback_model": "claude-opus-5-5",
        "fallback_llm_engine": "claude-code",
    }
    assert profile_problems(profile, MODELS) == []
    wrong = {**profile, "fallback_llm_engine": "nope"}
    assert any("Fallback model" in p for p in profile_problems(wrong, MODELS))


def test_every_configured_hotkey_action_has_a_handler():
    from app.hotkeys import _actions

    actions = _actions(AppContext(config={}))
    defaults = {hk["action"] for hk in settings._get_default_config()["hotkeys"]}
    file_config = {"hotkeys": [{"action": "capture", "key": "x"}]}
    settings._ensure_hotkey_actions(file_config)
    required = {hk["action"] for hk in file_config["hotkeys"]}
    assert (defaults | required) <= set(actions)
    # Each handler is called with no arguments by the keyboard hook.
    import inspect

    for name, handler in actions.items():
        assert not inspect.signature(handler).parameters, name
