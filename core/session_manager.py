"""The current chat session: history, transcription file, corrections and context.

Storage, the timeline and the search index live in :mod:`core.sessions`; the
static methods here delegate to them so existing callers keep working.
"""

import logging
import os
import shutil
import time
import uuid
from datetime import datetime
from typing import Any


def _init_qt_gl_sharing() -> None:
    """Load Qt WebEngine and enable GL context sharing before anything else."""
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return
    if not QApplication.instance():
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


_init_qt_gl_sharing()

from core.sessions import index, store, timeline  # noqa: E402
from core.sessions.store import (  # noqa: E402, F401  (re-exported for callers)
    DATE_FORMAT,
    SESSIONS_DIR,
    session_dir_path,
    session_transcription_path,
)

logger = logging.getLogger(__name__)

# Older name, still imported by core.periodic_screenshots.
_session_screenshots_dir = store.session_screenshots_dir


def _default_context_config() -> dict[str, Any]:
    return {
        "include_transcribed_text": False,
        "include_previous_questions": False,
        "include_previous_answers": False,
        "project_folder": "",
    }


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.save_images = config.get("save_images", True)
        self.save_transcriptions = config.get("save_transcriptions", True)
        self.speaker_name = config.get("speaker_name", "interviewer")
        self.current_session_id: str | None = None
        self.title: str | None = None
        self.transcription_file: str | None = None

        os.makedirs(store.SESSIONS_DIR, exist_ok=True)
        self._init_session()

    # ------------------------------------------------------------------ #
    #  Current session lifecycle
    # ------------------------------------------------------------------ #

    def _init_session(self):
        """Resume the session the config asks for, or start a new one."""
        if self.config.get("continue_last"):
            last = store.latest_session_id()
            if last:
                self._activate(last, "Resumed last session")
        elif self.config.get("continue_session"):
            self._load_session(self.config["continue_session"])

        if not self.current_session_id:
            self.start_new_session()

    def _activate(self, session_id: str, verb: str) -> None:
        store.get_session_dir(session_id)  # migrates a legacy session
        self.current_session_id = session_id
        self.title = None
        store.ensure_session_dirs(session_id)
        self.transcription_file = (
            session_transcription_path(session_id) if self.save_transcriptions else None
        )
        logger.info("%s: %s", verb, session_id)

    def start_new_session(self) -> str:
        """Starts a completely new session and returns its ID."""
        self._activate(str(uuid.uuid4()), "Started new session")
        assert self.current_session_id is not None
        return self.current_session_id

    def _load_session(self, session_id: str):
        if store.get_session_dir(session_id) is None:
            logger.warning("Session %s not found. Starting a new session.", session_id)
            return
        self._activate(session_id, "Resumed session")

    def cleanup(self):
        """Index the current session one last time."""
        if self.current_session_id:
            self.index_session(self.current_session_id)
        self.transcription_file = None

    # ------------------------------------------------------------------ #
    #  Reading
    # ------------------------------------------------------------------ #

    def _current_data(self) -> dict[str, Any]:
        if not self.current_session_id:
            return {}
        return store.read_session(self.current_session_id) or {}

    def get_history(self) -> list[dict[str, Any]]:
        """Returns the history of the current session."""
        data = self._current_data()
        self.title = data.get("title", self.title)
        return data.get("history", [])

    def get_context_config(self) -> dict[str, Any]:
        """Returns the context configuration for the current session."""
        return self._current_data().get("context") or _default_context_config()

    def get_corrections(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """Return stored corrections for a session."""
        sid = session_id or self.current_session_id
        if not sid:
            return []
        return (store.read_session(sid) or {}).get("corrections", [])

    def get_full_transcription(self) -> str | None:
        """Returns the full contents of the active session's transcription file, if it exists."""
        if not self.transcription_file or not os.path.exists(self.transcription_file):
            return None
        try:
            with open(self.transcription_file, encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else None
        except OSError as e:
            logger.error("Failed to read transcription file: %s", e)
            return None

    # ------------------------------------------------------------------ #
    #  Writing (all through store.update_session, under the session lock)
    # ------------------------------------------------------------------ #

    def set_context_config(self, context_config: dict[str, Any]):
        """Sets and saves the context configuration."""
        if not self.current_session_id:
            return
        try:
            store.update_session(
                self.current_session_id,
                lambda d: d.__setitem__("context", dict(context_config)),
            )
        except OSError as e:
            logger.error("Failed to set context config: %s", e)

    def append_corrections(self, corrections: list[dict[str, Any]]):
        """Append real-time corrections to the current session."""
        if not self.current_session_id or not corrections:
            return
        try:
            store.update_session(
                self.current_session_id,
                lambda d: d.setdefault("corrections", []).extend(corrections),
            )
            logger.info(
                "Appended %d corrections to session %s",
                len(corrections),
                self.current_session_id,
            )
        except OSError as e:
            logger.error("Failed to append corrections: %s", e)

    def import_context(
        self,
        source_session_id: str,
        import_transcribed_text: bool,
        import_questions: bool,
        import_answers: bool,
    ):
        """Imports selected historical items from source_session_id into current session."""
        if not self.current_session_id or source_session_id == self.current_session_id:
            return
        source_data = store.read_session(source_session_id)
        if not source_data:
            return

        imported = []
        for turn in source_data.get("history", []):
            new_turn = {
                "timestamp": time.time(),
                "source": "import",
                "speaker_name": turn.get("speaker_name", self.speaker_name),
            }
            if import_questions and "prompt" in turn:
                new_turn["prompt"] = turn["prompt"]
            if import_answers and "response" in turn:
                new_turn["response"] = turn["response"]
            if import_transcribed_text and "extracted_text" in turn:
                new_turn["extracted_text"] = turn["extracted_text"]
            if {"prompt", "response", "extracted_text"} & new_turn.keys():
                imported.append(new_turn)

        if imported:
            store.update_session(
                self.current_session_id,
                lambda d: self._stamp(d).setdefault("history", []).extend(imported),
            )

    def _stamp(self, data: dict[str, Any]) -> dict[str, Any]:
        """Refresh the fields every history write updates."""
        sid = self.current_session_id
        assert sid is not None
        if self.title and not data.get("title"):
            data["title"] = self.title
        data["speaker_name"] = self.speaker_name
        data.setdefault("tags", [])
        data["transcription_file"] = (
            "transcription.txt"
            if os.path.exists(session_transcription_path(sid))
            else None
        )
        data["updated_at"] = time.time()
        return data

    def _save_images(
        self, image_path: str | list[str], interaction_index: int
    ) -> list[str]:
        assert self.current_session_id is not None
        images_dir = store.session_images_dir(self.current_session_id)
        os.makedirs(images_dir, exist_ok=True)
        paths = [image_path] if isinstance(image_path, str) else image_path
        saved = []
        for i, p in enumerate(paths):
            if not os.path.exists(p):
                continue
            ext = os.path.splitext(p)[1] or ".png"
            suffix = f"_{i}" if len(paths) > 1 else ""
            image_filename = f"interaction_{interaction_index}{suffix}{ext}"
            try:
                shutil.copy2(p, os.path.join(images_dir, image_filename))
                saved.append(os.path.join("images", image_filename))
            except OSError as e:
                logger.warning("Failed to save image %s: %s", p, e)
        return saved

    def append_interaction(
        self,
        prompt: str,
        image_path: str | list[str] | None,
        response: str,
        extracted_text: str | None,
        source_name: str = "text",
    ):
        """Appends a new interaction to the current session."""
        sid = self.current_session_id
        if not sid:
            return

        # The transcript gets the AI response only for audio input.
        if (
            self.save_transcriptions
            and self.transcription_file
            and (
                source_name == "audio"
                or (extracted_text and "audio" in source_name.lower())
            )
        ):
            self._save_transcription_to_file(response)

        def change(data: dict[str, Any]) -> None:
            history = data.setdefault("history", [])
            if not history and prompt and not data.get("title"):
                # First interaction names the session: first line, 50 chars.
                self.title = prompt.strip().split("\n")[0][:50]
            interaction: dict[str, Any] = {
                "timestamp": time.time(),
                "prompt": prompt,
                "response": response,
                "extracted_text": extracted_text,
                "source": source_name,
                "speaker_name": self.speaker_name,
            }
            if image_path and self.save_images:
                # Inside the lock, so two interactions never pick the same file name.
                saved = self._save_images(image_path, len(history))
                if saved:
                    interaction["image"] = saved[0] if len(saved) == 1 else saved
            history.append(interaction)
            self._stamp(data)

        try:
            store.update_session(sid, change)
        except OSError as e:
            logger.error("Failed to save session data: %s", e)
            return

        # Index the session after interaction so it becomes searchable
        self.index_session(sid)

    def append_transcription_segment(
        self, segment_text: str, speaker_name: str | None = None
    ):
        """Appends a completed transcription segment, prefixed with ``[speaker]``."""
        if (
            not self.save_transcriptions
            or not self.transcription_file
            or not segment_text
        ):
            return
        name = speaker_name or self.speaker_name
        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                f.write(f"[{name}] {segment_text}\n")
        except OSError as e:
            logger.error("Failed to append transcription segment to file: %s", e)

    def _save_transcription_to_file(self, response: str):
        """Save AI response to transcription file with speaker attribution."""
        if not self.transcription_file:
            return
        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n--- AI Response ({timestamp}) ---\n")
                f.write(f"{response}\n\n--- [{self.speaker_name}] ---\n")
        except OSError as e:
            logger.error("Failed to save transcription to file: %s", e)

    # ------------------------------------------------------------------ #
    #  Indexing
    # ------------------------------------------------------------------ #

    def index_session_sync(self, session_id: str):
        """Generates and saves embeddings for the session (blocking)."""
        index.index_session_sync(self.config, session_id)

    def index_session(self, session_id: str):
        """Re-indexes the session in the background."""
        index.schedule_index(self.config, session_id)

    # ------------------------------------------------------------------ #
    #  Any session (delegates kept for existing callers)
    # ------------------------------------------------------------------ #

    get_session_dir = staticmethod(store.get_session_dir)
    load_session_data = staticmethod(store.read_session)
    list_all_sessions = staticmethod(store.list_sessions)
    count_empty_sessions = staticmethod(store.count_empty_sessions)
    delete_empty_sessions = staticmethod(store.delete_empty_sessions)
    rename_session = staticmethod(store.rename_session)
    set_session_tags = staticmethod(store.set_session_tags)
    delete_session = staticmethod(store.delete_session)
    get_timeline_events = staticmethod(timeline.get_timeline_events)
    get_all_embeddings = staticmethod(index.get_all_embeddings)
