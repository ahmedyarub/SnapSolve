"""Chronological timeline of a session: screenshots, interactions, AI-response markers."""

import json
import os
import re
from datetime import datetime
from typing import Any

from core.sessions.store import (
    DATE_FORMAT,
    read_session,
    session_screenshots_dir,
    session_transcription_path,
)

_AI_RESPONSE_TIME = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\)")
_SIDECAR_FIELDS = ("app_name", "process_name", "window_title", "exe_path")


def parse_screenshot_timestamp(filename: str) -> float | None:
    """Parse a screenshot filename like ``2026-06-06_10-30-15.png`` to epoch seconds.

    Returns ``None`` if the filename does not match the expected format.
    """
    stem = os.path.splitext(filename)[0]
    try:
        return datetime.strptime(stem, DATE_FORMAT).timestamp()
    except ValueError:
        return None


def _screenshot_events(session_id: str) -> list[dict[str, Any]]:
    screenshots_dir = session_screenshots_dir(session_id)
    if not os.path.isdir(screenshots_dir):
        return []
    events = []
    for fname in os.listdir(screenshots_dir):
        if not fname.lower().endswith(".png"):
            continue
        ts = parse_screenshot_timestamp(fname)
        if ts is None:
            continue
        data: dict[str, Any] = {
            "filename": fname,
            "path": os.path.abspath(os.path.join(screenshots_dir, fname)),
        }
        # Window metadata from the JSON sidecar, if any
        sidecar_path = os.path.join(
            screenshots_dir, os.path.splitext(fname)[0] + ".json"
        )
        if os.path.isfile(sidecar_path):
            try:
                with open(sidecar_path, encoding="utf-8") as sf:
                    sidecar = json.load(sf)
                for field in _SIDECAR_FIELDS:
                    data[field] = sidecar.get(field, "")
            except (OSError, json.JSONDecodeError):
                pass
        events.append({"type": "screenshot", "timestamp": ts, "data": data})
    return events


def _interaction_source(interaction: dict[str, Any], image_count: int) -> str:
    source = interaction.get("source", "text")
    if source == "text":
        if interaction.get("speaker_name"):
            return "audio"
        if image_count > 1:
            return "image_multi"
        if image_count == 1:
            return "image"
    elif source == "image" and image_count > 1:
        return "image_multi"
    return source


def _interaction_events(session_id: str) -> list[dict[str, Any]]:
    session_data = read_session(session_id)
    if not session_data:
        return []
    events = []
    for idx, interaction in enumerate(session_data.get("history", [])):
        images = interaction.get("image", [])
        if isinstance(images, str):
            images = [images] if images else []
        prompt_clean = (interaction.get("prompt") or "").replace("\n", " ").strip()
        excerpt = prompt_clean[:80] + ("..." if len(prompt_clean) > 80 else "")
        events.append(
            {
                "type": "interaction",
                "timestamp": interaction.get("timestamp", 0),
                "data": {
                    "index": idx,
                    "source": _interaction_source(interaction, len(images)),
                    "prompt_excerpt": excerpt,
                    "has_image": len(images) > 0,
                    "image_count": len(images),
                },
            }
        )
    return events


def _transcription_events(session_id: str) -> list[dict[str, Any]]:
    """AI-response separators in the transcription (``--- AI Response (ts) ---``)."""
    trans_path = session_transcription_path(session_id)
    if not os.path.isfile(trans_path):
        return []
    events = []
    try:
        with open(trans_path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not (
                    stripped.startswith("--- ")
                    and stripped.endswith(" ---")
                    and "AI Response" in stripped
                ):
                    continue
                m = _AI_RESPONSE_TIME.search(stripped)
                if not m:
                    continue
                try:
                    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                events.append(
                    {
                        "type": "transcription_separator",
                        "timestamp": dt.timestamp(),
                        "data": {"line": stripped},
                    }
                )
    except (OSError, ValueError):  # unreadable or not UTF-8
        pass
    return events


def get_timeline_events(session_id: str) -> list[dict[str, Any]]:
    """Chronologically sorted timeline events for a session.

    Each event has ``type`` (``"screenshot"`` | ``"interaction"`` |
    ``"transcription_separator"``), ``timestamp`` (epoch seconds) and ``data``:

    * screenshot: ``{"filename", "path", "app_name", "process_name", "window_title", "exe_path"}``
    * interaction: ``{"index", "source", "prompt_excerpt", "has_image", "image_count"}``
    * transcription separator: ``{"line": "--- AI Response (...) ---"}``
    """
    events = (
        _screenshot_events(session_id)
        + _interaction_events(session_id)
        + _transcription_events(session_id)
    )
    events.sort(key=lambda e: e["timestamp"])
    return events
