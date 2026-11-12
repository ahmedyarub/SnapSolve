"""Text input pipeline handler."""

import logging

from app.context import AppContext
from app.feedback import run_request, status_callback
from app.handlers.capture import (
    llm_unavailable,
    process_capture_result,
    setup_capture_sinks,
)
from core.pipeline import process_pipeline
from core.sources import TextSource

logger = logging.getLogger(__name__)


def execute_text_pipeline(
    ctx: AppContext,
    prompt_text: str,
    status_update,
    text: str | None = None,
    image_paths: list[str] | None = None,
    source_name: str = "text",
    post_action=None,
):
    """Send ``text`` (default: ``prompt_text``) through the LLM pipeline.

    Runs on the request's worker thread; returns the answer, or None.
    """
    if text is None:
        text = prompt_text
    if llm_unavailable(ctx):
        return None

    with ctx.engines_lock:  # a profile switch waits until this request is set up
        llm, fallback_llm = ctx.llm_engine, ctx.fallback_llm_engine
        chat_sessions = ctx.profile.get("enable_chat_sessions", True)
        sink, popup_sink, show_headers = setup_capture_sinks(ctx)

    temp_source = TextSource()
    temp_source._source_name = source_name
    assert llm is not None

    result = process_pipeline(
        source=temp_source,
        llm=llm,
        prompt_text=prompt_text,
        status_callback=status_update,
        session_manager=ctx.session_manager,
        enable_chat_sessions=chat_sessions,
        sink=sink,
        fallback_llm=fallback_llm,
        text=text,
        image_paths=image_paths,
        cancel_event=ctx.cancel_event,
        max_retries=ctx.config.get("llm_max_retries", 3),
        base_delay=ctx.config.get("llm_retry_base_delay", 5),
    )

    if hasattr(sink, "finish"):
        sink.finish()

    if ctx.cancel_event.is_set():
        logger.info("Text processing was cancelled.")
        return None

    process_capture_result(ctx, result, show_headers, popup_sink)

    if post_action:
        try:
            post_action(result)
        except Exception:
            logger.exception("Error in post_action")
    return result


def handle_text_submit(
    ctx: AppContext, text: str, source_name="text", post_action=None
):
    """Handle text input submission."""
    logger.info("Processing text input (%d chars)", len(text))
    status_update = status_callback(ctx.config)
    run_request(
        ctx,
        lambda: execute_text_pipeline(
            ctx, text, status_update, source_name=source_name, post_action=post_action
        ),
        "text input",
    )
