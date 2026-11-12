"""LLM layer: typed errors, retries, fallback cancellation and history limits."""

import threading
import time

import pytest

from core.llm.base import LLMEngine
from core.llm.errors import LLMError, is_error_text, is_transient
from core.pipeline.frames import ErrorFrame, LLMResponseFrame, PromptFrame
from core.pipeline.pipeline import LinkedCancel, _call_llm_with_retry
from core.pipeline.processors import ConcurrentLLMProcessor


class FakeEngine(LLMEngine):
    """Returns queued results in order (strings, or exceptions to raise)."""

    def __init__(self, results=(), history=None, config=None, context=None):
        manager = None
        if history is not None:
            manager = type(
                "Manager",
                (),
                {
                    "config": config or {},
                    "get_history": lambda _self: history,
                    "get_context_config": lambda _self: context or {},
                },
            )()
        super().__init__("fake", session_manager=manager)
        self.results = list(results)
        self.calls = 0

    @property
    def supports_images(self):
        return True

    def warmup(self, status_callback=None):
        return True

    def _next(self):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def process_text(
        self,
        prompt,
        status_callback=None,
        enable_chat_sessions=True,
        sink=None,
        is_main=True,
        cancel_event=None,
    ):
        return self._next()

    def process_image(
        self,
        prompt,
        image_path,
        status_callback=None,
        enable_chat_sessions=True,
        sink=None,
        is_main=True,
        cancel_event=None,
    ):
        return self._next()


@pytest.mark.parametrize(
    ("message", "transient"),
    [
        ("Error: 429 Too Many Requests", True),
        ("Error: 503 Service Unavailable", True),
        ("model is overloaded, try later", True),
        ("Read timed out", True),
        ("Error: invalid API key", False),
        ("request id 14290 failed validation", False),  # 429 inside a number
        ("Error from Claude: prompt is too long", False),
    ],
)
def test_is_transient(message, transient):
    assert is_transient(message) is transient


def test_error_text_detection():
    assert is_error_text("Error calling X")
    assert is_error_text("CLI Error: boom")
    assert not is_error_text("The answer is 42")
    assert not is_error_text(None)


def test_generate_turns_error_strings_into_llm_error():
    engine = FakeEngine(["Error: 503 Service Unavailable"])
    with pytest.raises(LLMError) as exc:
        engine.generate("q")
    assert exc.value.retryable


def test_generate_wraps_unexpected_exceptions():
    engine = FakeEngine([ValueError("bad payload")])
    with pytest.raises(LLMError, match="bad payload") as exc:
        engine.generate("q")
    assert not exc.value.retryable


def _retry(engine, max_retries=3):
    return _call_llm_with_retry(
        engine,
        "q",
        None,
        False,
        None,
        True,
        None,
        True,
        cancel_event=threading.Event(),
        max_retries=max_retries,
        base_delay=0,
    )


def test_retry_recovers_from_transient_errors():
    engine = FakeEngine(["Error: 429 rate limit", "Error: 503", "answer"])
    assert _retry(engine) == "answer"
    assert engine.calls == 3


def test_retry_gives_up_at_once_on_permanent_errors():
    engine = FakeEngine(["Error: invalid API key", "never reached"])
    with pytest.raises(LLMError):
        _retry(engine)
    assert engine.calls == 1


def test_retry_stops_after_max_retries():
    engine = FakeEngine(["Error: 503"] * 3)
    with pytest.raises(LLMError):
        _retry(engine, max_retries=2)
    assert engine.calls == 3


def test_linked_cancel_follows_parent():
    parent = threading.Event()
    child = LinkedCancel(parent)
    assert not child.is_set()
    parent.set()
    assert child.is_set()
    assert child.wait(0.01)
    own = LinkedCancel(threading.Event())
    own.set()
    assert own.is_set()


class SlowFallback(FakeEngine):
    """Waits until cancelled (or 5 s) and records whether it was stopped."""

    def __init__(self):
        super().__init__()
        self.cancelled = threading.Event()

    def process_text(
        self,
        prompt,
        status_callback=None,
        enable_chat_sessions=True,
        sink=None,
        is_main=True,
        cancel_event=None,
    ):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cancel_event and cancel_event.is_set():
                self.cancelled.set()
                return "Cancelled"
            time.sleep(0.01)
        return "slow fallback answer"


def _prompt_frame(cancel_event):
    return PromptFrame(
        cancel_event=cancel_event,
        metadata={},
        prompt="q",
        image_path=None,
        is_image=False,
        extracted_text=None,
        source_name="text",
    )


def test_fallback_is_cancelled_once_main_answers():
    fallback = SlowFallback()
    processor = ConcurrentLLMProcessor(
        FakeEngine(["main answer"]), fallback, base_delay=0
    )
    request_cancel = threading.Event()
    result = processor.process(_prompt_frame(request_cancel))
    assert isinstance(result, LLMResponseFrame)
    assert result.result == "main answer"
    assert fallback.cancelled.wait(2)
    assert not request_cancel.is_set()  # the user's request was not cancelled


def test_both_models_failing_gives_an_error_frame():
    processor = ConcurrentLLMProcessor(
        FakeEngine(["Error: invalid key"]),
        FakeEngine(["Error: model not found"]),
        base_delay=0,
    )
    result = processor.process(_prompt_frame(threading.Event()))
    assert isinstance(result, ErrorFrame)
    assert "invalid key" in result.error and "model not found" in result.error


def _history(n, size=10):
    return [{"prompt": f"q{i}" + "x" * size, "response": f"a{i}"} for i in range(n)]


def test_history_keeps_the_most_recent_turns():
    engine = FakeEngine(history=_history(30), config={"history_max_turns": 3})
    turns = engine.history_turns(True)
    assert [u[:3] for u, _ in turns] == ["q27", "q28", "q29"]


def test_history_respects_the_character_budget():
    engine = FakeEngine(
        history=_history(10, size=1000),
        config={"history_max_turns": 10, "history_max_chars": 2500},
    )
    assert len(engine.history_turns(True)) == 2


def test_history_respects_context_flags_and_chat_switch():
    engine = FakeEngine(
        history=_history(2),
        context={"include_previous_questions": False, "include_previous_answers": True},
    )
    assert engine.history_messages(True) == [
        {"role": "assistant", "content": "a0"},
        {"role": "assistant", "content": "a1"},
    ]
    assert engine.history_turns(False) == []


def test_prepare_prompt_flattens_history_for_single_prompt_engines():
    engine = FakeEngine(history=_history(1, size=0))
    assert engine._prepare_prompt("now?", True) == (
        "Previous conversation:\nUser: q0\nAssistant: a0\n\nCurrent request:\nnow?"
    )
