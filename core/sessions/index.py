"""Search index of sessions: embeddings of prompts, responses, transcripts and apps.

Each session's chunks and their embeddings live in ``sessions/<id>/embeddings.json``.
Indexing runs in the background; requests for a session that is already being
indexed are merged into one more pass, so a burst of interactions costs at most
two passes instead of one thread each.
"""

import json
import logging
import os
import threading
from typing import Any

from core.sessions.store import (
    SESSIONS_DIR,
    atomic_json_write,
    read_session,
    session_embeddings_path,
    session_screenshots_dir,
    session_transcription_path,
)

logger = logging.getLogger(__name__)

SEARCHABLE_TYPES = frozenset(
    {"prompt", "response", "transcription", "app_name", "summary", "tag"}
)

_state_guard = threading.Lock()
_running: set[str] = set()  # sessions with an indexing thread
_dirty: set[str] = set()  # sessions changed while their thread was running

# embeddings.json path -> (mtime_ns, size, chunks tagged with session_id)
_embeddings_cache: dict[str, tuple[int, int, list[dict[str, Any]]]] = {}
_cache_guard = threading.Lock()


def _collect_chunks(session_id: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for i, interaction in enumerate(data.get("history", [])):
        prompt = (interaction.get("prompt") or "").strip()
        if prompt:
            chunks.append({"type": "prompt", "index": i, "text": prompt})
        response = (interaction.get("response") or "").strip()
        if response:
            chunks.append({"type": "response", "index": i, "text": response})

    trans_path = session_transcription_path(session_id)
    if os.path.exists(trans_path):
        try:
            with open(trans_path, encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    line = line.strip()
                    if line and not line.startswith("---"):  # skip separators
                        chunks.append(
                            {"type": "transcription", "index": idx, "text": line}
                        )
        except (OSError, ValueError):  # unreadable or not UTF-8
            logger.warning("Cannot read transcription of session %s", session_id)

    screenshots_dir = session_screenshots_dir(session_id)
    if os.path.isdir(screenshots_dir):
        for fname in os.listdir(screenshots_dir):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(screenshots_dir, fname), encoding="utf-8") as sf:
                    sidecar = json.load(sf)
            except (OSError, json.JSONDecodeError):
                continue
            text = " ".join(
                part
                for part in (
                    (sidecar.get("app_name") or "").strip(),
                    (sidecar.get("window_title") or "").strip(),
                )
                if part
            )
            if text:
                chunks.append({"type": "app_name", "index": 0, "text": text})

    tags = data.get("tags", [])
    if tags:
        chunks.append({"type": "tag", "index": 0, "text": " ".join(tags)})
    summary = (data.get("summary") or "").strip()
    if summary:
        chunks.append({"type": "summary", "index": 0, "text": summary})
    return chunks


def _usable(embedding: Any) -> bool:
    """Older versions stored all-zero vectors when embedding failed; redo those."""
    return bool(embedding) and any(v != 0 for v in embedding)


def _existing_embeddings(path: str) -> dict[tuple, list[float]]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            old_chunks = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Ignoring unreadable index %s: %s", path, e)
        return {}
    return {
        (c.get("type"), c.get("index"), c.get("text")): c["embedding"]
        for c in old_chunks
        if _usable(c.get("embedding"))
    }


def index_session_sync(config: dict, session_id: str) -> None:
    """Embed the session's new chunks and save its index (blocking)."""
    from core.llm.embeddings import EmbeddingError, get_embedding_engine

    data = read_session(session_id)
    if not data:
        return
    chunks = _collect_chunks(session_id, data)
    if not chunks:
        return

    emb_path = session_embeddings_path(session_id)
    existing = _existing_embeddings(emb_path)
    missing = []
    for chunk in chunks:
        key = (chunk["type"], chunk["index"], chunk["text"])
        if key in existing:
            chunk["embedding"] = existing[key]
        else:
            missing.append(chunk)

    if missing:
        try:
            vectors = get_embedding_engine(config).embed_texts(
                [c["text"] for c in missing]
            )
        except EmbeddingError as e:
            # Keep the old index; the next pass retries the missing chunks.
            logger.error("Indexing session %s failed: %s", session_id, e)
            return
        for chunk, vector in zip(missing, vectors, strict=True):
            chunk["embedding"] = vector.tolist()

    atomic_json_write(emb_path, chunks)
    logger.info(
        "Indexed %d chunks (%d new) for session %s",
        len(chunks),
        len(missing),
        session_id,
    )


def _index_worker(config: dict, session_id: str) -> None:
    while True:
        try:
            index_session_sync(config, session_id)
        except Exception:
            logger.exception("Indexing session %s failed", session_id)
        with _state_guard:
            if session_id not in _dirty:
                _running.discard(session_id)
                return
            _dirty.discard(session_id)


def schedule_index(config: dict, session_id: str) -> None:
    """Re-index the session in the background (merged with a pass already running)."""
    with _state_guard:
        if session_id in _running:
            _dirty.add(session_id)
            return
        _running.add(session_id)
    threading.Thread(
        target=_index_worker,
        args=(config, session_id),
        daemon=True,
        name=f"index-{session_id[:8]}",
    ).start()


def _load_index(session_id: str, path: str) -> list[dict[str, Any]]:
    try:
        stat = os.stat(path)
    except OSError:
        return []
    with _cache_guard:
        cached = _embeddings_cache.get(path)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
    try:
        with open(path, encoding="utf-8") as f:
            chunks = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Cannot read index %s: %s", path, e)
        return []
    for c in chunks:
        c["session_id"] = session_id
    with _cache_guard:
        _embeddings_cache[path] = (stat.st_mtime_ns, stat.st_size, chunks)
    return chunks


def get_all_embeddings() -> list[dict[str, Any]]:
    """Every session's indexed chunks, each tagged with its ``session_id``.

    Files are re-read only when they change, so repeated searches are cheap.
    Callers must not modify the returned chunks.
    """
    if not os.path.exists(SESSIONS_DIR):
        return []
    all_chunks: list[dict[str, Any]] = []
    for entry in os.listdir(SESSIONS_DIR):
        path = session_embeddings_path(entry)
        if os.path.isfile(path):
            all_chunks.extend(_load_index(entry, path))
    return all_chunks
