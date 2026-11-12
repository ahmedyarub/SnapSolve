"""Session storage: paths, legacy migration, and locked read-modify-write of session.json.

Several threads write the same session file: the pipeline (new interactions), the
correction engine, the UI (context settings, names, tags) and the indexer reads
it. Every write goes through :func:`update_session`, which re-reads the file under
a per-session lock, applies the change and writes it back atomically, so no
writer can overwrite another's change.
"""

import copy
import json
import logging
import os
import shutil
import tempfile
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

SESSIONS_DIR = "sessions"

# Legacy shared directories (kept for migration compatibility)
LEGACY_IMAGES_DIR = os.path.join(SESSIONS_DIR, "images")
LEGACY_TRANSCRIPTIONS_DIR = os.path.join(SESSIONS_DIR, "transcriptions")

DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"


# --------------------------------------------------------------------------- #
#  Paths
# --------------------------------------------------------------------------- #


def session_dir_path(session_id: str) -> str:
    """Return the per-session directory path: sessions/<session_id>/"""
    return os.path.join(SESSIONS_DIR, session_id)


def session_json_path(session_id: str) -> str:
    """Return the session JSON path: sessions/<session_id>/session.json"""
    return os.path.join(session_dir_path(session_id), "session.json")


def session_images_dir(session_id: str) -> str:
    """Return the per-session images directory: sessions/<session_id>/images/"""
    return os.path.join(session_dir_path(session_id), "images")


def session_transcription_path(session_id: str) -> str:
    """Return the per-session transcription file: sessions/<session_id>/transcription.txt"""
    return os.path.join(session_dir_path(session_id), "transcription.txt")


def session_screenshots_dir(session_id: str) -> str:
    """Return the per-session screenshots directory: sessions/<session_id>/screenshots/"""
    return os.path.join(session_dir_path(session_id), "screenshots")


def session_embeddings_path(session_id: str) -> str:
    return os.path.join(session_dir_path(session_id), "embeddings.json")


def legacy_session_json_path(session_id: str) -> str:
    """Return the legacy flat-file session path: sessions/<session_id>.json"""
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def ensure_session_dirs(session_id: str) -> None:
    """Create the per-session directory structure."""
    os.makedirs(session_images_dir(session_id), exist_ok=True)
    os.makedirs(session_screenshots_dir(session_id), exist_ok=True)


def has_screenshots(session_id: str) -> bool:
    """Return True if the session has at least one captured screenshot."""
    screenshots_dir = session_screenshots_dir(session_id)
    if not os.path.isdir(screenshots_dir):
        return False
    return any(f.endswith(".png") for f in os.listdir(screenshots_dir))


def has_transcription(session_id: str) -> bool:
    """Return True if the session has a non-empty transcription file."""
    trans_path = session_transcription_path(session_id)
    return os.path.isfile(trans_path) and os.path.getsize(trans_path) > 0


# --------------------------------------------------------------------------- #
#  Low-level I/O
# --------------------------------------------------------------------------- #


def atomic_json_write(path: str, data: Any) -> None:
    """Write JSON data to *path* atomically.

    Writes to a temporary file in the same directory, then uses ``os.replace()``
    to swap it into place, so a crash leaves either the old or the new file.
    """
    dir_name = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        os.replace(tmp_path, path)
    except BaseException:
        # Clean up the temp file on any failure (including KeyboardInterrupt).
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


_locks: dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()

# path -> (mtime_ns, size, parsed JSON). Readers get deep copies.
_read_cache: dict[str, tuple[int, int, dict[str, Any]]] = {}
_cache_guard = threading.Lock()


def session_lock(session_id: str) -> threading.RLock:
    """The lock that serialises writes to one session's files."""
    with _locks_guard:
        lock = _locks.get(session_id)
        if lock is None:
            lock = _locks[session_id] = threading.RLock()
        return lock


def _read_json_cached(path: str) -> dict[str, Any] | None:
    try:
        stat = os.stat(path)
    except OSError:
        return None
    with _cache_guard:
        cached = _read_cache.get(path)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return copy.deepcopy(cached[2])
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Cannot read session file %s: %s", path, e)
        return None
    if not isinstance(data, dict):
        return None
    with _cache_guard:
        _read_cache[path] = (stat.st_mtime_ns, stat.st_size, data)
    return copy.deepcopy(data)


def _forget_cached(path: str) -> None:
    with _cache_guard:
        _read_cache.pop(path, None)


# --------------------------------------------------------------------------- #
#  Legacy migration
# --------------------------------------------------------------------------- #


def migrate_legacy_session(session_id: str) -> bool:
    """Move a legacy ``sessions/<id>.json`` into ``sessions/<id>/session.json``.

    Images referenced from the shared ``sessions/images/`` folder move into the
    session's own ``images/`` folder. Returns True if a migration was performed.
    """
    legacy_path = legacy_session_json_path(session_id)
    new_json = session_json_path(session_id)
    with session_lock(session_id):
        if not os.path.exists(legacy_path) or os.path.exists(new_json):
            return False
        try:
            new_images = session_images_dir(session_id)
            os.makedirs(new_images, exist_ok=True)

            with open(legacy_path, encoding="utf-8") as f:
                data = json.load(f)

            for interaction in data.get("history", []):
                old_image = interaction.get("image")
                if isinstance(old_image, str) and os.path.exists(old_image):
                    image_filename = os.path.basename(old_image)
                    try:
                        shutil.move(old_image, os.path.join(new_images, image_filename))
                        interaction["image"] = os.path.join("images", image_filename)
                    except OSError as e:
                        logger.warning("Failed to migrate image %s: %s", old_image, e)

            atomic_json_write(new_json, data)
            try:
                os.remove(legacy_path)
            except OSError as e:
                logger.warning("Failed to remove legacy file %s: %s", legacy_path, e)
            logger.info("Migrated legacy session %s to folder structure", session_id)
            return True
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to migrate session %s: %s", session_id, e)
            return False


# --------------------------------------------------------------------------- #
#  Read / write
# --------------------------------------------------------------------------- #


def read_session(session_id: str) -> dict[str, Any] | None:
    """The full session JSON (a private copy), migrating a legacy file first."""
    path = session_json_path(session_id)
    if not os.path.exists(path) and os.path.exists(
        legacy_session_json_path(session_id)
    ):
        migrate_legacy_session(session_id)
    return _read_json_cached(path)


def update_session(
    session_id: str, change: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    """Apply ``change`` to the stored session under its lock and save it.

    ``change`` mutates the dict in place. A missing or unreadable file starts
    from an empty session. Returns the saved data.
    """
    with session_lock(session_id):
        data = read_session(session_id) or {}
        change(data)
        data.setdefault("id", session_id)
        data.setdefault("history", [])
        path = session_json_path(session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        atomic_json_write(path, data)
        _forget_cached(path)
        return data


def get_session_dir(session_id: str) -> str | None:
    """The session's directory, migrating a legacy session; None if it doesn't exist."""
    path = session_dir_path(session_id)
    if os.path.exists(path):
        return path
    if os.path.exists(legacy_session_json_path(session_id)):
        migrate_legacy_session(session_id)
        return path
    return None


def rename_session(session_id: str, new_name: str) -> None:
    if read_session(session_id) is None:
        return
    update_session(session_id, lambda d: d.__setitem__("name", new_name))


def set_session_tags(session_id: str, tags: list[str]) -> None:
    if read_session(session_id) is None:
        return
    update_session(session_id, lambda d: d.__setitem__("tags", list(tags)))


def delete_session(session_id: str) -> bool:
    """Delete a session and all its files. Returns True if something was deleted."""
    with session_lock(session_id):
        _forget_cached(session_json_path(session_id))
        session_dir = session_dir_path(session_id)
        if os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.info("Deleted session folder: %s", session_id)
                return True
            except OSError as e:
                logger.error("Failed to delete session folder %s: %s", session_id, e)
                return False

        # Legacy: flat JSON file plus images in the shared folder
        legacy_path = legacy_session_json_path(session_id)
        if not os.path.exists(legacy_path):
            return False
        try:
            with open(legacy_path, encoding="utf-8") as f:
                data = json.load(f)
            for interaction in data.get("history", []):
                image_path = interaction.get("image")
                if isinstance(image_path, str) and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError as img_err:
                        logger.warning(
                            "Failed to delete image %s: %s", image_path, img_err
                        )
        except (OSError, json.JSONDecodeError):
            pass  # Still attempt to delete the session file
        try:
            os.remove(legacy_path)
            logger.info("Deleted legacy session: %s", session_id)
            return True
        except OSError as e:
            logger.error("Failed to delete session %s: %s", session_id, e)
            return False


# --------------------------------------------------------------------------- #
#  Listing
# --------------------------------------------------------------------------- #


def _summary(session_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id", session_id),
        "title": data.get("title"),
        "name": data.get("name"),
        "tags": data.get("tags", []),
        "speaker_name": data.get("speaker_name", "interviewer"),
        "updated_at": data.get("updated_at", 0),
        "interaction_count": len(data.get("history", [])),
    }


def list_sessions_unfiltered() -> list[dict[str, Any]]:
    """Lightweight metadata for ALL sessions, including empty ones.

    Legacy flat-file sessions are migrated on the way.
    """
    sessions: list[dict[str, Any]] = []
    if not os.path.exists(SESSIONS_DIR):
        return sessions
    seen: set[str] = set()
    for entry in os.listdir(SESSIONS_DIR):
        entry_path = os.path.join(SESSIONS_DIR, entry)
        if os.path.isdir(entry_path):
            if os.path.exists(os.path.join(entry_path, "session.json")):
                data = read_session(entry)
                if data is not None:
                    sessions.append(_summary(entry, data))
                    seen.add(entry)
            continue
        if entry.endswith(".json") and os.path.isfile(entry_path):
            session_id = entry[: -len(".json")]
            if session_id in seen:
                continue
            data = read_session(session_id)
            if data is not None:
                sessions.append(_summary(session_id, data))
                seen.add(session_id)
    return sessions


def _is_empty(summary: dict[str, Any]) -> bool:
    return (
        summary["interaction_count"] == 0
        and not has_screenshots(summary["id"])
        and not has_transcription(summary["id"])
    )


def list_sessions() -> list[dict[str, Any]]:
    """Metadata for all non-empty sessions, newest first."""
    sessions = [s for s in list_sessions_unfiltered() if not _is_empty(s)]
    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    return sessions


def count_empty_sessions() -> int:
    return sum(1 for s in list_sessions_unfiltered() if _is_empty(s))


def delete_empty_sessions() -> int:
    """Delete every empty session; return how many were deleted."""
    empty = [s["id"] for s in list_sessions_unfiltered() if _is_empty(s)]
    return sum(1 for sid in empty if delete_session(sid))


def latest_session_id() -> str | None:
    """The most recently modified session (folder or legacy file), if any."""
    if not os.path.exists(SESSIONS_DIR):
        return None
    candidates: list[tuple[str, float]] = []
    for entry in os.listdir(SESSIONS_DIR):
        entry_path = os.path.join(SESSIONS_DIR, entry)
        session_json = os.path.join(entry_path, "session.json")
        if os.path.isdir(entry_path) and os.path.exists(session_json):
            candidates.append((entry, os.path.getmtime(session_json)))
        elif entry.endswith(".json") and os.path.isfile(entry_path):
            candidates.append((entry[: -len(".json")], os.path.getmtime(entry_path)))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[1])[0]
