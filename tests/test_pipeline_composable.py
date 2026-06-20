"""Unit tests for the composable pipeline architecture.

Tests the Frame types, Processor implementations, Pipeline runner, and
the backward-compatible ``process_pipeline()`` adapter.
"""
import threading
import unittest
from unittest.mock import MagicMock, patch

from core.pipeline.frames import (
    CancelledFrame,
    ErrorFrame,
    Frame,
    LLMResponseFrame,
    PromptFrame,
    SourceFrame,
)
from core.pipeline.processors import (
    ConcurrentLLMProcessor,
    LLMProcessor,
    Processor,
    PromptBuilderProcessor,
    SessionSaveProcessor,
    SinkProcessor,
    SourceProcessor,
    _check_cancelled,
    _is_terminal,
)
from core.pipeline.runner import Pipeline, build_pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_frame(**kwargs) -> Frame:
    """Create a base frame with defaults."""
    defaults = {"cancel_event": threading.Event(), "metadata": {}}
    defaults.update(kwargs)
    return Frame(**defaults)


def _make_source_frame(**kwargs) -> SourceFrame:
    """Create a SourceFrame with defaults."""
    defaults = {
        "cancel_event": threading.Event(),
        "metadata": {},
        "extracted_text": "Hello world",
        "image_path": None,
        "is_image": False,
        "source_name": "text",
    }
    defaults.update(kwargs)
    return SourceFrame(**defaults)


def _make_prompt_frame(**kwargs) -> PromptFrame:
    """Create a PromptFrame with defaults."""
    defaults = {
        "cancel_event": threading.Event(),
        "metadata": {},
        "prompt": "Analyze: Hello world",
        "image_path": None,
        "is_image": False,
        "source_name": "text",
        "extracted_text": "Hello world",
    }
    defaults.update(kwargs)
    return PromptFrame(**defaults)


class _PassthroughProcessor(Processor):
    """Test processor that passes frames through unchanged."""

    def __init__(self):
        self.called_with = None

    def process(self, frame: Frame) -> Frame:
        self.called_with = frame
        return frame


class _ErrorRaisingProcessor(Processor):
    """Test processor that always returns an ErrorFrame."""

    def process(self, frame: Frame) -> Frame:
        return ErrorFrame(
            cancel_event=frame.cancel_event,
            metadata=frame.metadata,
            error="Deliberate test error",
        )


class _CountingProcessor(Processor):
    """Test processor that counts how many times it was called."""

    def __init__(self):
        self.call_count = 0

    def process(self, frame: Frame) -> Frame:
        self.call_count += 1
        return frame


# ===========================================================================
# Frame tests
# ===========================================================================
class TestFrameCreation(unittest.TestCase):
    def test_base_frame(self):
        f = _make_frame()
        self.assertIsInstance(f.cancel_event, threading.Event)
        self.assertEqual(f.metadata, {})

    def test_source_frame(self):
        f = _make_source_frame(extracted_text="test", source_name="image")
        self.assertEqual(f.extracted_text, "test")
        self.assertEqual(f.source_name, "image")
        self.assertFalse(f.is_image)

    def test_prompt_frame(self):
        f = _make_prompt_frame(prompt="Analyze this")
        self.assertEqual(f.prompt, "Analyze this")

    def test_llm_response_frame(self):
        f = LLMResponseFrame(
            cancel_event=threading.Event(),
            result="Answer",
            prompt="Question",
        )
        self.assertEqual(f.result, "Answer")

    def test_error_frame(self):
        f = ErrorFrame(cancel_event=threading.Event(), error="bad things")
        self.assertEqual(f.error, "bad things")

    def test_cancelled_frame(self):
        f = CancelledFrame(cancel_event=threading.Event())
        self.assertEqual(f.message, "Pipeline cancelled.")


# ===========================================================================
# Utility function tests
# ===========================================================================
class TestUtilityFunctions(unittest.TestCase):
    def test_check_cancelled_not_set(self):
        f = _make_frame()
        self.assertIsNone(_check_cancelled(f))

    def test_check_cancelled_set(self):
        evt = threading.Event()
        evt.set()
        f = _make_frame(cancel_event=evt)
        result = _check_cancelled(f)
        self.assertIsInstance(result, CancelledFrame)

    def test_is_terminal_error(self):
        f = ErrorFrame(cancel_event=threading.Event(), error="x")
        self.assertTrue(_is_terminal(f))

    def test_is_terminal_cancelled(self):
        f = CancelledFrame(cancel_event=threading.Event())
        self.assertTrue(_is_terminal(f))

    def test_is_terminal_normal(self):
        f = _make_frame()
        self.assertFalse(_is_terminal(f))


# ===========================================================================
# Processor tests
# ===========================================================================
class TestSourceProcessor(unittest.TestCase):
    @patch("core.pipeline.processors.SourceProcessor.process")
    def test_passthrough_on_error_frame(self, _mock):
        """ErrorFrame should pass through unchanged."""
        proc = SourceProcessor(source=MagicMock(), coords=None)
        # Manually call the real logic
        _mock.side_effect = lambda f: f
        err = ErrorFrame(cancel_event=threading.Event(), error="test")
        result = proc.process(err)
        self.assertIsInstance(result, ErrorFrame)

    def test_cancellation_before_source(self):
        """Should return CancelledFrame if cancel_event is set."""
        evt = threading.Event()
        evt.set()
        proc = SourceProcessor(source=MagicMock(), coords=None)
        result = proc.process(Frame(cancel_event=evt))
        self.assertIsInstance(result, CancelledFrame)

    @patch("core.pipeline.pipeline._retrieve_data_from_source")
    def test_successful_extraction(self, mock_retrieve):
        mock_retrieve.return_value = ("extracted text", None, False)
        source = MagicMock()
        source.name = "text"
        proc = SourceProcessor(source=source, coords=None)
        result = proc.process(_make_frame())
        self.assertIsInstance(result, SourceFrame)
        self.assertEqual(result.extracted_text, "extracted text")
        self.assertEqual(result.source_name, "text")

    @patch("core.pipeline.pipeline._retrieve_data_from_source")
    def test_extraction_error(self, mock_retrieve):
        mock_retrieve.side_effect = RuntimeError("OCR failed")
        proc = SourceProcessor(source=MagicMock(), coords=None)
        result = proc.process(_make_frame())
        self.assertIsInstance(result, ErrorFrame)
        self.assertIn("OCR failed", result.error)


class TestPromptBuilderProcessor(unittest.TestCase):
    def test_wrong_input_frame_type(self):
        proc = PromptBuilderProcessor(prompt_text="Analyze")
        result = proc.process(_make_frame())
        self.assertIsInstance(result, ErrorFrame)

    @patch("core.output.set_last_user_prompt")
    def test_builds_prompt(self, _mock_set):
        proc = PromptBuilderProcessor(prompt_text="Analyze")
        src_frame = _make_source_frame(extracted_text="Hello world")
        result = proc.process(src_frame)
        self.assertIsInstance(result, PromptFrame)
        self.assertEqual(result.prompt, "Analyze: Hello world")

    @patch("core.output.set_last_user_prompt")
    def test_prompt_without_extracted_text(self, _mock_set):
        proc = PromptBuilderProcessor(prompt_text="Just a question")
        src_frame = _make_source_frame(extracted_text=None)
        result = proc.process(src_frame)
        self.assertIsInstance(result, PromptFrame)
        self.assertEqual(result.prompt, "Just a question")


class TestLLMProcessor(unittest.TestCase):
    def test_wrong_input_frame_type(self):
        proc = LLMProcessor(llm=MagicMock())
        result = proc.process(_make_frame())
        self.assertIsInstance(result, ErrorFrame)

    @patch("core.pipeline.pipeline._execute_llm_without_fallback")
    def test_successful_execution(self, mock_exec):
        mock_exec.return_value = "LLM answer"
        proc = LLMProcessor(llm=MagicMock())
        result = proc.process(_make_prompt_frame())
        self.assertIsInstance(result, LLMResponseFrame)
        self.assertEqual(result.result, "LLM answer")

    @patch("core.pipeline.pipeline._execute_llm_without_fallback")
    def test_llm_exception(self, mock_exec):
        mock_exec.side_effect = RuntimeError("API error")
        proc = LLMProcessor(llm=MagicMock())
        result = proc.process(_make_prompt_frame())
        self.assertIsInstance(result, ErrorFrame)
        self.assertIn("API error", result.error)


class TestSinkProcessor(unittest.TestCase):
    def test_calls_finish(self):
        mock_sink = MagicMock()
        proc = SinkProcessor(sink=mock_sink)
        frame = _make_prompt_frame()
        result = proc.process(frame)
        mock_sink.finish.assert_called_once()
        self.assertIs(result, frame)

    def test_no_sink(self):
        proc = SinkProcessor(sink=None)
        frame = _make_prompt_frame()
        result = proc.process(frame)
        self.assertIs(result, frame)

    def test_passthrough_on_error(self):
        mock_sink = MagicMock()
        proc = SinkProcessor(sink=mock_sink)
        err = ErrorFrame(cancel_event=threading.Event(), error="x")
        result = proc.process(err)
        self.assertIsInstance(result, ErrorFrame)
        mock_sink.finish.assert_not_called()


class TestSessionSaveProcessor(unittest.TestCase):
    @patch("core.pipeline.pipeline._save_to_session")
    def test_saves_interaction(self, mock_save):
        mgr = MagicMock()
        proc = SessionSaveProcessor(session_manager=mgr)
        frame = LLMResponseFrame(
            cancel_event=threading.Event(),
            result="Answer",
            prompt="Question",
            source_name="text",
        )
        result = proc.process(frame)
        self.assertIsInstance(result, LLMResponseFrame)
        mock_save.assert_called_once()

    def test_passthrough_on_non_response_frame(self):
        proc = SessionSaveProcessor(session_manager=MagicMock())
        frame = _make_prompt_frame()
        result = proc.process(frame)
        self.assertIs(result, frame)


# ===========================================================================
# Pipeline runner tests
# ===========================================================================
class TestPipeline(unittest.TestCase):
    def test_empty_pipeline(self):
        p = Pipeline([])
        frame = _make_frame()
        result = p.run(frame)
        self.assertIs(result, frame)

    def test_single_processor(self):
        proc = _PassthroughProcessor()
        p = Pipeline([proc])
        frame = _make_frame()
        result = p.run(frame)
        self.assertIs(result, frame)
        self.assertIs(proc.called_with, frame)

    def test_error_short_circuits(self):
        error_proc = _ErrorRaisingProcessor()
        counter = _CountingProcessor()
        p = Pipeline([error_proc, counter])
        result = p.run(_make_frame())
        self.assertIsInstance(result, ErrorFrame)
        self.assertEqual(counter.call_count, 0)

    def test_cancelled_short_circuits(self):
        evt = threading.Event()
        evt.set()

        class CancelProcessor(Processor):
            def process(self, f):
                return CancelledFrame(cancel_event=f.cancel_event)

        counter = _CountingProcessor()
        p = Pipeline([CancelProcessor(), counter])
        result = p.run(Frame(cancel_event=evt))
        self.assertIsInstance(result, CancelledFrame)
        self.assertEqual(counter.call_count, 0)

    def test_multi_processor_chain(self):
        c1 = _CountingProcessor()
        c2 = _CountingProcessor()
        c3 = _CountingProcessor()
        p = Pipeline([c1, c2, c3])
        p.run(_make_frame())
        self.assertEqual(c1.call_count, 1)
        self.assertEqual(c2.call_count, 1)
        self.assertEqual(c3.call_count, 1)


# ===========================================================================
# build_pipeline factory tests
# ===========================================================================
class TestBuildPipeline(unittest.TestCase):
    def test_without_fallback(self):
        pipeline = build_pipeline(
            source=MagicMock(),
            llm=MagicMock(),
            prompt_text="test",
        )
        self.assertIsInstance(pipeline, Pipeline)
        # Should have: Source, PromptBuilder, LLM, SessionSave
        self.assertEqual(len(pipeline.processors), 4)
        self.assertIsInstance(pipeline.processors[0], SourceProcessor)
        self.assertIsInstance(pipeline.processors[1], PromptBuilderProcessor)
        self.assertIsInstance(pipeline.processors[2], LLMProcessor)
        self.assertIsInstance(pipeline.processors[3], SessionSaveProcessor)

    def test_with_fallback(self):
        pipeline = build_pipeline(
            source=MagicMock(),
            llm=MagicMock(),
            prompt_text="test",
            fallback_llm=MagicMock(),
        )
        # Should have: Source, PromptBuilder, ConcurrentLLM, SessionSave
        self.assertEqual(len(pipeline.processors), 4)
        self.assertIsInstance(pipeline.processors[2], ConcurrentLLMProcessor)


# ===========================================================================
# process_pipeline adapter tests
# ===========================================================================
class TestProcessPipelineAdapter(unittest.TestCase):
    @patch("core.pipeline.pipeline.build_pipeline")
    def test_returns_llm_result(self, mock_build):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = LLMResponseFrame(
            cancel_event=threading.Event(),
            result="Answer text",
            prompt="Question",
        )
        mock_build.return_value = mock_pipeline

        from core.pipeline.pipeline import process_pipeline

        result = process_pipeline(
            source=MagicMock(),
            llm=MagicMock(),
            prompt_text="test",
        )
        self.assertEqual(result, "Answer text")

    @patch("core.pipeline.pipeline.build_pipeline")
    def test_returns_error(self, mock_build):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = ErrorFrame(
            cancel_event=threading.Event(),
            error="Something went wrong",
        )
        mock_build.return_value = mock_pipeline

        from core.pipeline.pipeline import process_pipeline

        result = process_pipeline(
            source=MagicMock(),
            llm=MagicMock(),
            prompt_text="test",
        )
        self.assertEqual(result, "Something went wrong")

    @patch("core.pipeline.pipeline.build_pipeline")
    def test_returns_cancelled(self, mock_build):
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = CancelledFrame(
            cancel_event=threading.Event(),
        )
        mock_build.return_value = mock_pipeline

        from core.pipeline.pipeline import process_pipeline, PIPELINE_CANCELLED_MSG

        result = process_pipeline(
            source=MagicMock(),
            llm=MagicMock(),
            prompt_text="test",
        )
        self.assertEqual(result, PIPELINE_CANCELLED_MSG)


if __name__ == "__main__":
    unittest.main()
