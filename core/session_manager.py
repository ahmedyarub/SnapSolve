# Force PyQt6 WebEngine and GL sharing to initialize before anything else
try:
    import PyQt6.QtWebEngineWidgets
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication
    if not QApplication.instance():
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
except ImportError:
    pass

import json
import os
import shutil
import tempfile
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

SESSIONS_DIR = "sessions"

# Legacy shared directories (kept for migration compatibility)
LEGACY_IMAGES_DIR = os.path.join(SESSIONS_DIR, "images")
LEGACY_TRANSCRIPTIONS_DIR = os.path.join(SESSIONS_DIR, "transcriptions")

DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"

logger = logging.getLogger(__name__)


def _session_dir(session_id: str) -> str:
    """Return the per-session directory path: sessions/<session_id>/"""
    return os.path.join(SESSIONS_DIR, session_id)


def _session_json_path(session_id: str) -> str:
    """Return the session JSON path: sessions/<session_id>/session.json"""
    return os.path.join(_session_dir(session_id), "session.json")


def _session_images_dir(session_id: str) -> str:
    """Return the per-session images directory: sessions/<session_id>/images/"""
    return os.path.join(_session_dir(session_id), "images")


def _session_transcription_path(session_id: str) -> str:
    """Return the per-session transcription file: sessions/<session_id>/transcription.txt"""
    return os.path.join(_session_dir(session_id), "transcription.txt")


def _session_screenshots_dir(session_id: str) -> str:
    """Return the per-session screenshots directory: sessions/<session_id>/screenshots/"""
    return os.path.join(_session_dir(session_id), "screenshots")


def _has_screenshots(session_id: str) -> bool:
    """Return True if the session has at least one captured screenshot."""
    screenshots_dir = _session_screenshots_dir(session_id)
    if not os.path.isdir(screenshots_dir):
        return False
    return any(f.endswith(".png") for f in os.listdir(screenshots_dir))

def _legacy_session_json_path(session_id: str) -> str:
    """Return the legacy flat-file session path: sessions/<session_id>.json"""
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def _atomic_json_write(path: str, data: Any) -> None:
    """Write JSON data to *path* atomically.

    Writes to a temporary file in the same directory, then uses
    ``os.replace()`` to atomically swap it into place.  This prevents
    data corruption if the process is killed (e.g. via ``os._exit()``) in
    the middle of a write — either the old file remains intact or the new
    file is fully committed.
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


def _migrate_legacy_session(session_id: str) -> bool:
    """Migrate a legacy flat-file session into the new per-session folder structure.

    Moves ``sessions/<uuid>.json`` → ``sessions/<uuid>/session.json`` and
    relocates any referenced images from the shared ``sessions/images/`` directory
    into the per-session ``sessions/<uuid>/images/`` folder.

    Returns True if migration was performed, False if no legacy file found.
    """
    legacy_path = _legacy_session_json_path(session_id)
    if not os.path.exists(legacy_path):
        return False

    new_dir = _session_dir(session_id)
    new_images = _session_images_dir(session_id)
    new_json = _session_json_path(session_id)

    # Already migrated (both exist — shouldn't happen, but be safe)
    if os.path.exists(new_json):
        return False

    try:
        os.makedirs(new_dir, exist_ok=True)
        os.makedirs(new_images, exist_ok=True)

        # Read legacy data
        with open(legacy_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Relocate referenced images
        for interaction in data.get("history", []):
            old_image = interaction.get("image")
            if old_image and os.path.exists(old_image):
                image_filename = os.path.basename(old_image)
                new_image_path = os.path.join(new_images, image_filename)
                try:
                    shutil.move(old_image, new_image_path)
                    # Store relative path from session dir
                    interaction["image"] = os.path.join("images", image_filename)
                except Exception as e:
                    logger.warning(f"[SessionManager] Failed to migrate image {old_image}: {e}")

        # Write to new location
        _atomic_json_write(new_json, data)

        # Remove legacy file
        try:
            os.remove(legacy_path)
        except OSError as e:
            logger.warning(f"[SessionManager] Failed to remove legacy file {legacy_path}: {e}")

        logger.info(f"[SessionManager] Migrated legacy session {session_id} to folder structure")
        return True

    except Exception as e:
        logger.error(f"[SessionManager] Failed to migrate session {session_id}: {e}")
        return False


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.save_images = config.get("save_images", True)
        self.save_transcriptions = config.get("save_transcriptions", True)
        self.speaker_name = config.get("speaker_name", "interviewer")
        self.current_session_id: Optional[str] = None
        self.title: Optional[str] = None
        self.transcription_file: Optional[str] = None

        # Ensure base sessions directory exists
        os.makedirs(SESSIONS_DIR, exist_ok=True)

        self._init_session()

    def _init_session(self):
        """Initializes a session based on config or starts a new one."""
        if self.config.get("continue_last"):
            self._load_last_session()
        elif self.config.get("continue_session"):
            self._load_session(self.config["continue_session"])

        if not self.current_session_id:
            self.start_new_session()

    def _ensure_session_dirs(self, session_id: str):
        """Create the per-session directory structure."""
        os.makedirs(_session_dir(session_id), exist_ok=True)
        os.makedirs(_session_images_dir(session_id), exist_ok=True)
        os.makedirs(_session_screenshots_dir(session_id), exist_ok=True)

    def start_new_session(self) -> str:
        """Starts a completely new session and returns its ID."""
        self.current_session_id = str(uuid.uuid4())
        self.title = None

        # Close old transcription file if open
        self._close_transcription_file()

        # Create per-session directory structure
        self._ensure_session_dirs(self.current_session_id)

        # Setup new transcription file inside session folder
        if self.save_transcriptions:
            self.transcription_file = _session_transcription_path(self.current_session_id)
            logger.debug(
                f"[SessionManager] Created new transcription file: {self.transcription_file}"
            )

        print(f"[SessionManager] Started new session: {self.current_session_id}")
        return self.current_session_id

    def _load_session(self, session_id: str):
        # Try new-style path first, then legacy
        new_path = _session_json_path(session_id)
        legacy_path = _legacy_session_json_path(session_id)

        if os.path.exists(new_path) or os.path.exists(legacy_path):
            # Migrate if legacy
            if not os.path.exists(new_path) and os.path.exists(legacy_path):
                _migrate_legacy_session(session_id)

            self.current_session_id = session_id

            # Ensure session dirs exist
            self._ensure_session_dirs(session_id)

            # Setup transcription file inside session folder
            if self.save_transcriptions:
                self.transcription_file = _session_transcription_path(session_id)
                logger.debug(
                    f"[SessionManager] Resumed session, transcription file: {self.transcription_file}"
                )

            print(f"[SessionManager] Resumed session: {session_id}")
        else:
            print(
                f"[SessionManager] Session {session_id} not found. Starting new session."
            )

    def _load_last_session(self):
        # Scan for new-style sessions (folders with session.json)
        sessions = []

        if not os.path.exists(SESSIONS_DIR):
            return

        for entry in os.listdir(SESSIONS_DIR):
            entry_path = os.path.join(SESSIONS_DIR, entry)

            # New-style: directory with session.json
            session_json = os.path.join(entry_path, "session.json")
            if os.path.isdir(entry_path) and os.path.exists(session_json):
                sessions.append((entry, os.path.getmtime(session_json)))
                continue

            # Legacy: <uuid>.json file
            if entry.endswith(".json") and os.path.isfile(entry_path):
                session_id = entry.replace(".json", "")
                sessions.append((session_id, os.path.getmtime(entry_path)))

        if not sessions:
            return

        # Sort by modification time, newest first
        sessions.sort(key=lambda x: x[1], reverse=True)

        last_session_id = sessions[0][0]
        self.current_session_id = last_session_id

        # Migrate if legacy
        legacy_path = _legacy_session_json_path(last_session_id)
        if not os.path.exists(_session_json_path(last_session_id)) and os.path.exists(legacy_path):
            _migrate_legacy_session(last_session_id)

        # Ensure session dirs exist
        self._ensure_session_dirs(last_session_id)

        # Setup transcription file inside session folder
        if self.save_transcriptions:
            self.transcription_file = _session_transcription_path(last_session_id)
            logger.debug(
                f"[SessionManager] Resumed last session, transcription file: {self.transcription_file}"
            )

        print(f"[SessionManager] Resumed last session: {self.current_session_id}")

    def _default_context_config(self) -> Dict[str, Any]:
        return {
            "include_transcribed_text": False,
            "include_previous_questions": False,
            "include_previous_answers": False,
            "project_folder": ""
        }

    def get_context_config(self) -> Dict[str, Any]:
        """Returns the context configuration for the current session."""
        if not self.current_session_id:
            return self._default_context_config()

        path = _session_json_path(self.current_session_id)
        if not os.path.exists(path):
            return self._default_context_config()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("context", self._default_context_config())
        except (json.JSONDecodeError, IOError):
            return self._default_context_config()

    def set_context_config(self, context_config: Dict[str, Any]):
        """Sets and saves the context configuration."""
        if not self.current_session_id:
            return
            
        path = _session_json_path(self.current_session_id)
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
                
        data["context"] = context_config
        # We must preserve everything else
        if "id" not in data: data["id"] = self.current_session_id
        if "history" not in data: data["history"] = []
        
        try:
            _atomic_json_write(path, data)
        except IOError as e:
            logger.error(f"[SessionManager] Failed to set context config: {e}")

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
            
        source_data = self.load_session_data(source_session_id)
        if not source_data:
            return
            
        source_history = source_data.get("history", [])
        current_history = self.get_history()
        
        for turn in source_history:
            new_turn = {
                "timestamp": time.time(),
                "source": "import",
                "speaker_name": turn.get("speaker_name", self.speaker_name)
            }
            if import_questions and "prompt" in turn:
                new_turn["prompt"] = turn["prompt"]
            if import_answers and "response" in turn:
                new_turn["response"] = turn["response"]
            if import_transcribed_text and "extracted_text" in turn:
                new_turn["extracted_text"] = turn["extracted_text"]
                
            if "prompt" in new_turn or "response" in new_turn or "extracted_text" in new_turn:
                current_history.append(new_turn)
                
        self._save_session_data(current_history)

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns the history of the current session."""
        if not self.current_session_id:
            return []

        path = _session_json_path(self.current_session_id)
        if not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.title = data.get("title")
                return data.get("history", [])
        except (json.JSONDecodeError, IOError):
            return []

    def append_interaction(
        self,
        prompt: str,
        image_path: Optional[str | List[str]],
        response: str,
        extracted_text: Optional[str],
        source_name: str = "text",
    ):
        """Appends a new interaction to the current session."""
        history = self.get_history()

        # Set title if it's the first interaction
        if not history and prompt:
            # Simple title generation: take the first 50 chars of the prompt
            self.title = prompt.strip().split("\n")[0][:50]

        interaction: Dict[str, Any] = {
            "timestamp": time.time(),
            "prompt": prompt,
            "response": response,
            "extracted_text": extracted_text,
            "source": source_name,
            "speaker_name": self.speaker_name,
        }

        if image_path and self.save_images:
            assert self.current_session_id is not None
            images_dir = _session_images_dir(self.current_session_id)
            os.makedirs(images_dir, exist_ok=True)

            paths_to_save = [image_path] if isinstance(image_path, str) else image_path
            saved_images = []

            for i, p in enumerate(paths_to_save):
                if os.path.exists(p):
                    ext = os.path.splitext(p)[1] or ".png"
                    suffix = f"_{i}" if len(paths_to_save) > 1 else ""
                    image_filename = f"interaction_{len(history)}{suffix}{ext}"
                    new_image_path = os.path.join(images_dir, image_filename)
                    try:
                        shutil.copy2(p, new_image_path)
                        saved_images.append(os.path.join("images", image_filename))
                    except Exception as e:
                        print(f"[SessionManager] Warning: failed to save image: {e}")

            if saved_images:
                if len(saved_images) == 1:
                    interaction["image"] = saved_images[0]
                else:
                    interaction["image"] = saved_images

        # Ensure transcription is saved to text file only for audio inputs
        if (
            self.save_transcriptions
            and self.transcription_file
            and (
                source_name == "audio"
                or (extracted_text and "audio" in source_name.lower())
            )
        ):
            self._save_transcription_to_file(prompt, response, extracted_text)

        history.append(interaction)
        self._save_session_data(history)

    def append_transcription_segment(self, segment_text: str, speaker_name: Optional[str] = None):
        """Appends a completed transcription segment to the active transcription file.

        Prefixes the segment with ``[speaker_name]`` for attribution.
        """
        if (
            not self.save_transcriptions
            or not self.transcription_file
            or not segment_text
        ):
            logger.debug(
                f"[SessionManager] Cannot append segment. save_trans={self.save_transcriptions}, "
                f"file={self.transcription_file}, text='{segment_text}'"
            )
            return

        name = speaker_name or self.speaker_name
        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                f.write(f"[{name}] {segment_text}\n")
            logger.debug(
                f"[SessionManager] Appended segment to {self.transcription_file}: "
                f"'[{name}] {segment_text}'"
            )
        except IOError as e:
            print(
                f"[SessionManager] Failed to append transcription segment to file: {e}"
            )
            logger.error(
                f"[SessionManager] Failed to append transcription segment to file: {e}"
            )

    def _save_transcription_to_file(
        self, _prompt: str, response: str, _extracted_text: Optional[str]
    ):
        """Save AI response to transcription file with speaker attribution."""
        if not self.transcription_file:
            logger.debug(
                "[SessionManager] Cannot save interaction. transcription_file is None."
            )
            return

        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n--- AI Response ({timestamp}) ---\n")
                f.write(f"{response}\n\n--- [{self.speaker_name}] ---\n")
            logger.debug(
                f"[SessionManager] Saved AI response to {self.transcription_file}"
            )
        except IOError as e:
            print(f"[SessionManager] Failed to save transcription to file: {e}")
            logger.error(f"[SessionManager] Failed to save transcription to file: {e}")

    def _save_session_data(self, history: List[Dict[str, Any]]):
        if not self.current_session_id:
            return

        path = _session_json_path(self.current_session_id)

        # Ensure session directory exists
        self._ensure_session_dirs(self.current_session_id)

        # Preserve existing name/tags/context from file if present
        existing_name = None
        existing_tags: List[str] = []
        existing_context = self._default_context_config()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                    existing_name = existing.get("name")
                    existing_tags = existing.get("tags", [])
                    existing_context = existing.get("context", existing_context)
            except (json.JSONDecodeError, IOError):
                pass

        data = {
            "id": self.current_session_id,
            "title": self.title,
            "name": existing_name,
            "tags": existing_tags,
            "speaker_name": self.speaker_name,
            "transcription_file": "transcription.txt" if self.transcription_file and os.path.exists(self.transcription_file) else None,
            "updated_at": time.time(),
            "context": existing_context,
            "history": history,
        }

        try:
            _atomic_json_write(path, data)
        except IOError as e:
            print(f"[SessionManager] Failed to save session data: {e}")

    def _close_transcription_file(self):
        # Python handles file closing automatically, but we can reset the path
        if self.transcription_file:
            logger.debug(
                f"[SessionManager] Closing transcription file tracking for: {self.transcription_file}"
            )
        self.transcription_file = None

    def get_full_transcription(self) -> Optional[str]:
        """Returns the full contents of the active session's transcription file, if it exists."""
        if not self.transcription_file or not os.path.exists(self.transcription_file):
            return None
            
        try:
            with open(self.transcription_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return content if content else None
        except IOError as e:
            logger.error(f"[SessionManager] Failed to read transcription file: {e}")
            return None

    def cleanup(self):
        """Perform any necessary cleanup."""
        if self.current_session_id:
            self.index_session(self.current_session_id)
        self._close_transcription_file()

    @staticmethod
    def list_all_sessions() -> List[Dict[str, Any]]:
        """Returns lightweight metadata for all non-empty sessions, sorted by updated_at descending.

        Scans for both new-style (folder-based) and legacy (flat-file) sessions.
        Legacy sessions are transparently migrated on access.
        """
        sessions = SessionManager._list_all_sessions_unfiltered()

        # Filter out empty sessions (no interactions and no screenshots)
        sessions = [
            s for s in sessions
            if s["interaction_count"] > 0
            or _has_screenshots(s["id"])
        ]

        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions

    @staticmethod
    def count_empty_sessions() -> int:
        """Return the number of empty sessions (no interactions and no screenshots)."""
        all_sessions = SessionManager._list_all_sessions_unfiltered()
        return sum(
            1 for s in all_sessions
            if s["interaction_count"] == 0 and not _has_screenshots(s["id"])
        )

    @staticmethod
    def delete_empty_sessions() -> int:
        """Delete all empty sessions and return the count of deleted sessions."""
        all_sessions = SessionManager._list_all_sessions_unfiltered()
        empty_ids = [
            s["id"] for s in all_sessions
            if s["interaction_count"] == 0 and not _has_screenshots(s["id"])
        ]
        deleted = 0
        for sid in empty_ids:
            if SessionManager.delete_session(sid):
                deleted += 1
        return deleted

    @staticmethod
    def _list_all_sessions_unfiltered() -> List[Dict[str, Any]]:
        """Returns lightweight metadata for ALL sessions (including empty ones).

        Scans for both new-style (folder-based) and legacy (flat-file) sessions.
        Legacy sessions are transparently migrated on access.
        """
        sessions = []
        seen_ids: set[str] = set()

        if not os.path.exists(SESSIONS_DIR):
            return sessions

        for entry in os.listdir(SESSIONS_DIR):
            entry_path = os.path.join(SESSIONS_DIR, entry)

            # New-style: directory with session.json
            session_json = os.path.join(entry_path, "session.json")
            if os.path.isdir(entry_path) and os.path.exists(session_json):
                try:
                    with open(session_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session_id = data.get("id", entry)
                    seen_ids.add(session_id)
                    sessions.append({
                        "id": session_id,
                        "title": data.get("title"),
                        "name": data.get("name"),
                        "tags": data.get("tags", []),
                        "speaker_name": data.get("speaker_name", "interviewer"),
                        "updated_at": data.get("updated_at", 0),
                        "interaction_count": len(data.get("history", [])),
                    })
                except (json.JSONDecodeError, IOError):
                    continue
                continue

            # Legacy: <uuid>.json file
            if not entry.endswith(".json") or not os.path.isfile(entry_path):
                continue

            session_id = entry.replace(".json", "")
            if session_id in seen_ids:
                continue

            # Attempt migration
            _migrate_legacy_session(session_id)

            # After migration, try to read from new location
            migrated_path = _session_json_path(session_id)
            read_path = migrated_path if os.path.exists(migrated_path) else entry_path

            try:
                with open(read_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                seen_ids.add(session_id)
                sessions.append({
                    "id": data.get("id", session_id),
                    "title": data.get("title"),
                    "name": data.get("name"),
                    "tags": data.get("tags", []),
                    "speaker_name": data.get("speaker_name", "interviewer"),
                    "updated_at": data.get("updated_at", 0),
                    "interaction_count": len(data.get("history", [])),
                })
            except (json.JSONDecodeError, IOError):
                continue

        return sessions

    @staticmethod
    def load_session_data(session_id: str) -> Optional[Dict[str, Any]]:
        """Loads full session JSON including history.

        Checks new-style path first, falls back to legacy, and migrates if needed.
        """
        # Try new-style path first
        new_path = _session_json_path(session_id)
        if os.path.exists(new_path):
            try:
                with open(new_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

        # Fall back to legacy
        legacy_path = _legacy_session_json_path(session_id)
        if os.path.exists(legacy_path):
            # Migrate, then read from new location
            _migrate_legacy_session(session_id)
            migrated_path = _session_json_path(session_id)
            read_path = migrated_path if os.path.exists(migrated_path) else legacy_path
            try:
                with open(read_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

        return None

    @staticmethod
    def rename_session(session_id: str, new_name: str):
        """Updates the name field of a session."""
        path = _session_json_path(session_id)

        # Fall back to legacy path
        if not os.path.exists(path):
            legacy = _legacy_session_json_path(session_id)
            if os.path.exists(legacy):
                _migrate_legacy_session(session_id)

        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["name"] = new_name
            _atomic_json_write(path, data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[SessionManager] Failed to rename session {session_id}: {e}")

    @staticmethod
    def set_session_tags(session_id: str, tags: List[str]):
        """Updates the tags field of a session."""
        path = _session_json_path(session_id)

        # Fall back to legacy path
        if not os.path.exists(path):
            legacy = _legacy_session_json_path(session_id)
            if os.path.exists(legacy):
                _migrate_legacy_session(session_id)

        if not os.path.exists(path):
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["tags"] = tags
            _atomic_json_write(path, data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[SessionManager] Failed to set tags for session {session_id}: {e}")

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """Deletes a session and all its associated files. Returns True if deleted successfully."""
        session_dir = _session_dir(session_id)

        # New-style: delete entire session folder
        if os.path.isdir(session_dir):
            try:
                shutil.rmtree(session_dir)
                logger.info(f"[SessionManager] Deleted session folder: {session_id}")
                return True
            except OSError as e:
                logger.error(f"[SessionManager] Failed to delete session folder {session_id}: {e}")
                return False

        # Legacy: delete flat JSON file and referenced images
        legacy_path = _legacy_session_json_path(session_id)
        if not os.path.exists(legacy_path):
            return False

        # Remove referenced images from legacy shared folder
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for interaction in data.get("history", []):
                image_path = interaction.get("image")
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except OSError as img_err:
                        logger.warning(
                            f"[SessionManager] Failed to delete image {image_path}: {img_err}"
                        )
        except (json.JSONDecodeError, IOError):
            pass  # Still attempt to delete the session file

        # Remove session JSON file
        try:
            os.remove(legacy_path)
            logger.info(f"[SessionManager] Deleted legacy session: {session_id}")
            return True
        except OSError as e:
            logger.error(f"[SessionManager] Failed to delete session {session_id}: {e}")
            return False

    @staticmethod
    def _parse_screenshot_timestamp(filename: str) -> Optional[float]:
        """Parse a screenshot filename like ``2026-06-06_10-30-15.png`` to epoch seconds.

        Returns ``None`` if the filename does not match the expected format.
        """
        stem = os.path.splitext(filename)[0]
        try:
            dt = datetime.strptime(stem, DATE_FORMAT)
            return dt.timestamp()
        except ValueError:
            return None

    @staticmethod
    def get_timeline_events(session_id: str) -> List[Dict[str, Any]]:
        """Return chronologically sorted timeline events for a session.

        Each event dict contains:

        * ``type`` — ``"screenshot"`` | ``"interaction"`` | ``"transcription_separator"``
        * ``timestamp`` — float (epoch seconds)
        * ``data`` — type-specific payload dict

        Screenshot data::

            {"filename": "2026-06-06_10-30-15.png", "path": "<absolute path>"}

        Interaction data::

            {"index": 0, "source": "text"|"audio"|"image", "prompt_excerpt": "...",
             "has_image": True/False, "image_count": 1}

        Transcription separator data::

            {"line": "--- [interviewer] ---"}
        """
        events: List[Dict[str, Any]] = []

        # 1. Screenshots
        screenshots_dir = _session_screenshots_dir(session_id)
        if os.path.isdir(screenshots_dir):
            for fname in os.listdir(screenshots_dir):
                if not fname.lower().endswith(".png"):
                    continue
                ts = SessionManager._parse_screenshot_timestamp(fname)
                if ts is not None:
                    abs_path = os.path.abspath(os.path.join(screenshots_dir, fname))
                    data: Dict[str, Any] = {
                        "filename": fname,
                        "path": abs_path,
                    }

                    # Load window metadata from JSON sidecar if available
                    sidecar_name = os.path.splitext(fname)[0] + ".json"
                    sidecar_path = os.path.join(screenshots_dir, sidecar_name)
                    if os.path.isfile(sidecar_path):
                        try:
                            with open(sidecar_path, "r", encoding="utf-8") as sf:
                                sidecar = json.load(sf)
                            data["app_name"] = sidecar.get("app_name", "")
                            data["process_name"] = sidecar.get("process_name", "")
                            data["window_title"] = sidecar.get("window_title", "")
                            data["exe_path"] = sidecar.get("exe_path", "")
                        except (json.JSONDecodeError, IOError):
                            pass

                    events.append({
                        "type": "screenshot",
                        "timestamp": ts,
                        "data": data,
                    })

        # 2. Interactions from session.json
        session_data = SessionManager.load_session_data(session_id)
        if session_data:
            for idx, interaction in enumerate(session_data.get("history", [])):
                ts = interaction.get("timestamp", 0)
                source = interaction.get("source", "text")
                prompt = interaction.get("prompt", "")

                images = interaction.get("image", [])
                if isinstance(images, str):
                    images = [images] if images else []

                if source == "text":
                    if interaction.get("speaker_name"):
                        source = "audio"
                    elif len(images) > 1:
                        source = "image_multi"
                    elif len(images) == 1:
                        source = "image"
                elif source == "image" and len(images) > 1:
                    source = "image_multi"
                prompt_clean = prompt.replace("\n", " ").strip()
                excerpt = prompt_clean[:80] + ("..." if len(prompt_clean) > 80 else "")

                images = interaction.get("image", [])
                if isinstance(images, str):
                    images = [images] if images else []

                events.append({
                    "type": "interaction",
                    "timestamp": ts,
                    "data": {
                        "index": idx,
                        "source": source,
                        "prompt_excerpt": excerpt,
                        "has_image": len(images) > 0,
                        "image_count": len(images),
                    },
                })

        # 3. Transcription separators (timestamps inferred from position)
        trans_path = _session_transcription_path(session_id)
        if os.path.isfile(trans_path):
            try:
                with open(trans_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith("--- ") and stripped.endswith(" ---"):
                            # Try to extract timestamp from AI Response lines
                            if "AI Response" in stripped:
                                # Format: --- AI Response (2026-06-06 10:30:15) ---
                                import re
                                m = re.search(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\)", stripped)
                                if m:
                                    try:
                                        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                                        events.append({
                                            "type": "transcription_separator",
                                            "timestamp": dt.timestamp(),
                                            "data": {"line": stripped},
                                        })
                                    except ValueError:
                                        pass
            except IOError:
                pass

        # Sort by timestamp
        events.sort(key=lambda e: e["timestamp"])
        return events

    def index_session_sync(self, session_id: str):
        """Generates and saves embeddings for the session synchronously."""
        try:
            from core.llm.embeddings import get_embedding_engine
            engine = get_embedding_engine(self.config)
            
            data = self.load_session_data(session_id)
            if not data:
                return
                
            chunks = []
            history = data.get("history", [])
            
            # Extract prompts and responses
            for i, interaction in enumerate(history):
                prompt = interaction.get("prompt", "").strip()
                if prompt:
                    chunks.append({"type": "prompt", "index": i, "text": prompt})
                    
                response = interaction.get("response", "").strip()
                if response:
                    chunks.append({"type": "response", "index": i, "text": response})
            
            # Extract transcription lines
            trans_path = _session_transcription_path(session_id)
            if os.path.exists(trans_path):
                try:
                    with open(trans_path, "r", encoding="utf-8") as f:
                        for idx, line in enumerate(f):
                            line = line.strip()
                            # Skip separator lines
                            if line.startswith("---") or not line:
                                continue
                            chunks.append({"type": "transcription", "index": idx, "text": line})
                except Exception:
                    pass
            
            # Extract app names from screenshots
            screenshots_dir = _session_screenshots_dir(session_id)
            if os.path.isdir(screenshots_dir):
                for fname in os.listdir(screenshots_dir):
                    if not fname.endswith(".json"):
                        continue
                    sidecar_path = os.path.join(screenshots_dir, fname)
                    try:
                        with open(sidecar_path, "r", encoding="utf-8") as sf:
                            sidecar = json.load(sf)
                        app_name = sidecar.get("app_name", "").strip()
                        window_title = sidecar.get("window_title", "").strip()
                        text = ""
                        if app_name: text += app_name
                        if window_title: text += " " + window_title
                        if text:
                            chunks.append({"type": "app_name", "index": 0, "text": text.strip()})
                    except Exception:
                        pass
            
            # Extract tags and summaries
            tags = data.get("tags", [])
            if tags:
                chunks.append({"type": "tag", "index": 0, "text": " ".join(tags)})
                
            summary = data.get("summary", "").strip()
            if summary:
                chunks.append({"type": "summary", "index": 0, "text": summary})
            
            if not chunks:
                return
                
            texts = [c["text"] for c in chunks]
            embeddings = engine.embed_texts(texts)
            
            for i, chunk in enumerate(chunks):
                chunk["embedding"] = embeddings[i].tolist()
                
            emb_path = os.path.join(_session_dir(session_id), "embeddings.json")
            _atomic_json_write(emb_path, chunks)
            logger.info(f"[SessionManager] Indexed {len(chunks)} chunks for session {session_id}")
            
        except Exception as e:
            logger.error(f"[SessionManager] Failed to index session {session_id}: {e}")

    def index_session(self, session_id: str):
        """Generates and saves embeddings for the session in a background thread."""
        import threading
        thread = threading.Thread(target=self.index_session_sync, args=(session_id,), daemon=True)
        thread.start()

    @staticmethod
    def get_all_embeddings() -> List[Dict[str, Any]]:
        """Loads all embeddings.json files into memory. Used for semantic search."""
        all_chunks = []
        if not os.path.exists(SESSIONS_DIR):
            return all_chunks
            
        for entry in os.listdir(SESSIONS_DIR):
            session_dir = os.path.join(SESSIONS_DIR, entry)
            emb_path = os.path.join(session_dir, "embeddings.json")
            if os.path.isdir(session_dir) and os.path.exists(emb_path):
                try:
                    with open(emb_path, "r", encoding="utf-8") as f:
                        chunks = json.load(f)
                    for c in chunks:
                        c["session_id"] = entry
                    all_chunks.extend(chunks)
                except Exception:
                    pass
                    
        return all_chunks
