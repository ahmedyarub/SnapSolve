"""Exporting a session as Markdown (for reading/sharing) or JSON (complete data)."""

import json
import os
from datetime import datetime
from typing import Any

from core.sessions.store import read_session, session_transcription_path

EXPORT_FORMATS = ("md", "json")


def _when(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _transcription(session_id: str) -> str | None:
    path = session_transcription_path(session_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except (OSError, ValueError):
        return None


def export_markdown(session_id: str) -> str | None:
    """The session as a Markdown document, or None if it does not exist."""
    data = read_session(session_id)
    if data is None:
        return None
    title = data.get("name") or data.get("title") or session_id
    lines = [f"# {title}", ""]
    meta = [f"- Session: `{session_id}`"]
    if data.get("updated_at"):
        meta.append(f"- Last updated: {_when(data['updated_at'])}")
    if data.get("tags"):
        meta.append("- Tags: " + ", ".join(data["tags"]))
    lines += [*meta, ""]

    for number, turn in enumerate(data.get("history", []), start=1):
        heading = f"## {number}. {turn.get('source', 'text').capitalize()}"
        when = _when(turn.get("timestamp"))
        lines += [f"{heading} ({when})" if when else heading, ""]
        if turn.get("prompt"):
            lines += ["**Question**", "", turn["prompt"].strip(), ""]
        if turn.get("extracted_text") and turn.get("extracted_text") != turn.get(
            "prompt"
        ):
            lines += [
                "**Captured text**",
                "",
                "```",
                turn["extracted_text"].strip(),
                "```",
                "",
            ]
        if turn.get("response"):
            lines += ["**Answer**", "", turn["response"].strip(), ""]

    corrections = data.get("corrections") or []
    if corrections:
        lines += ["## Corrections", ""]
        lines += [f"- {json.dumps(c, ensure_ascii=False)}" for c in corrections]
        lines.append("")

    transcription = _transcription(session_id)
    if transcription:
        lines += ["## Transcript", "", "```", transcription, "```", ""]
    return "\n".join(lines)


def export_json(session_id: str) -> str | None:
    """The full session data plus its transcript, as JSON."""
    data: dict[str, Any] | None = read_session(session_id)
    if data is None:
        return None
    data["transcription"] = _transcription(session_id)
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_session(session_id: str, fmt: str = "md") -> str | None:
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Unknown export format {fmt!r} (use one of {EXPORT_FORMATS})")
    return export_markdown(session_id) if fmt == "md" else export_json(session_id)
