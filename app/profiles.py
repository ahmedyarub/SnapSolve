"""The active profile: choosing it at startup and switching it while the app runs."""

import logging
import threading

from app.config_validation import profile_problems
from app.context import DEFAULT_PROMPT_TEXT, AppContext
from app.engine_init import (
    build_correction_engine,
    build_llm_engines,
    build_ocr_engine,
    warm_up_llms,
)
from app.feedback import show_status
from config.settings import load_profiles, load_prompts, update_config_file

logger = logging.getLogger(__name__)


def find_profile(profiles: list[dict], profile_id: str | None) -> dict:
    """The profile with ``profile_id``, else the first one (or an empty profile)."""
    return next(
        (p for p in profiles if p.get("id") == profile_id),
        profiles[0] if profiles else {},
    )


def prompt_text_for(profile: dict, prompts: list[dict]) -> str:
    prompt_id = profile.get("prompt_id", "default")
    prompt = next(
        (p for p in prompts if p.get("id") == prompt_id), prompts[0] if prompts else {}
    )
    return prompt.get("text", DEFAULT_PROMPT_TEXT)


def apply_profile_engines(ctx: AppContext, profile: dict, prompts: list[dict]) -> None:
    """Build the profile's engines and make them (and the profile) current.

    The OCR engine is kept when the OCR type is unchanged: loading PaddleOCR
    takes seconds. Requests wait on ``ctx.engines_lock`` meanwhile.
    """
    old_ocr_type = ctx.profile.get("ocr_engine") if ctx.ocr_engine else None
    new_ocr_type = profile.get("ocr_engine", "none")
    ocr_engine = (
        ctx.ocr_engine
        if old_ocr_type == new_ocr_type
        else build_ocr_engine(profile, ctx.config)
    )
    llm, fallback = build_llm_engines(profile, ctx.config, ctx.session_manager)
    correction = build_correction_engine(
        profile, ctx.config, ctx.session_manager, prompts
    )

    with ctx.engines_lock:
        if ctx.correction_engine and ctx.correction_engine is not correction:
            ctx.correction_engine.stop()
        ctx.profile = dict(profile)
        ctx.prompt_text = prompt_text_for(profile, prompts)
        ctx.ocr_engine = ocr_engine
        ctx.llm_engine, ctx.fallback_llm_engine = llm, fallback
        ctx.correction_engine = correction

        from core.sources import get_active_source_instance

        source = get_active_source_instance()
        if hasattr(source, "ocr_engine"):
            source.ocr_engine = ocr_engine


def switch_profile(ctx: AppContext, profile_id: str) -> None:
    """Make ``profile_id`` the active profile (validated, engines rebuilt, saved).

    Runs in the background; the current profile stays active if the new one is
    invalid or its engines fail to start.
    """
    if profile_id == ctx.profile.get("id"):
        return

    def work() -> None:
        profiles = load_profiles()
        profile = next((p for p in profiles if p.get("id") == profile_id), None)
        if profile is None:
            show_status(ctx.config, f"Unknown profile: {profile_id}", auto_close=5000)
            return
        problems = profile_problems(profile)
        if problems:
            show_status(
                ctx.config,
                f"Cannot switch to {profile.get('name', profile_id)}:\n"
                + "\n".join(problems),
                auto_close=8000,
            )
            publish_profiles(ctx)  # put the selector back
            return

        name = profile.get("name", profile_id)
        show_status(ctx.config, f"Switching to {name}...")
        try:
            apply_profile_engines(ctx, profile, load_prompts())
        except Exception as e:
            logger.exception("Switching to profile %s failed", profile_id)
            show_status(ctx.config, f"Could not switch to {name}: {e}", auto_close=8000)
            publish_profiles(ctx)
            return

        ctx.config["active_profile_id"] = profile_id
        update_config_file({"active_profile_id": profile_id})
        publish_profiles(ctx)
        from core.output import set_chat_sessions_btn_state

        set_chat_sessions_btn_state(ctx.profile.get("enable_chat_sessions", True))
        warm_up_llms(ctx.config, ctx.llm_engine, ctx.fallback_llm_engine)
        show_status(ctx.config, f"Profile: {name}", auto_close=2500)

    threading.Thread(target=work, daemon=True, name="switch-profile").start()


def publish_profiles(ctx: AppContext) -> None:
    """Tell the panel which profiles exist and which one is active."""
    from core.output import set_profile_choices

    profiles = load_profiles()
    set_profile_choices(
        [(p.get("id", ""), p.get("name", p.get("id", ""))) for p in profiles],
        ctx.profile.get("id", ""),
    )
