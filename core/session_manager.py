import json
import os
import shutil
import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

SESSIONS_DIR = "sessions"
IMAGES_DIR = os.path.join(SESSIONS_DIR, "images")
TRANSCRIPTIONS_DIR = os.path.join(SESSIONS_DIR, "transcriptions")

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.save_images = config.get("save_images", False)
        self.save_transcriptions = config.get("save_transcriptions", True)
        self.current_session_id = None
        self.title = None
        self.transcription_file = None

        # Ensure directories exist
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)

        self._init_session()

    def _init_session(self):
        """Initializes a session based on config or starts a new one."""
        if self.config.get("continue_last"):
            self._load_last_session()
        elif self.config.get("continue_session"):
            self._load_session(self.config["continue_session"])

        if not self.current_session_id:
            self.start_new_session()

    def start_new_session(self) -> str:
        """Starts a completely new session and returns its ID."""
        self.current_session_id = str(uuid.uuid4())
        self.title = None

        # Close old transcription file if open
        self._close_transcription_file()

        # Setup new transcription file
        if self.save_transcriptions:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"transcription_{timestamp}.txt"
            self.transcription_file = os.path.join(TRANSCRIPTIONS_DIR, filename)
            logger.debug(
                f"[SessionManager] Created new transcription file: {self.transcription_file}"
            )

        self._save_session_data([])
        print(f"[SessionManager] Started new session: {self.current_session_id}")
        return self.current_session_id

    def _load_session(self, session_id: str):
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(path):
            self.current_session_id = session_id

            # Setup new transcription file for resumed session to append new transcriptions
            if self.save_transcriptions:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"transcription_resumed_{session_id}_{timestamp}.txt"
                self.transcription_file = os.path.join(TRANSCRIPTIONS_DIR, filename)
                logger.debug(
                    f"[SessionManager] Resumed session, created transcription file: {self.transcription_file}"
                )

            print(f"[SessionManager] Resumed session: {session_id}")
        else:
            print(
                f"[SessionManager] Session {session_id} not found. Starting new session."
            )

    def _load_last_session(self):
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        if not files:
            return

        # Sort by modification time, newest first
        files.sort(
            key=lambda x: os.path.getmtime(os.path.join(SESSIONS_DIR, x)), reverse=True
        )

        last_file = files[0]
        self.current_session_id = last_file.replace(".json", "")

        # Setup new transcription file for resumed session to append new transcriptions
        if self.save_transcriptions:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = (
                f"transcription_resumed_{self.current_session_id}_{timestamp}.txt"
            )
            self.transcription_file = os.path.join(TRANSCRIPTIONS_DIR, filename)
            logger.debug(
                f"[SessionManager] Resumed last session, created transcription file: {self.transcription_file}"
            )

        print(f"[SessionManager] Resumed last session: {self.current_session_id}")

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns the history of the current session."""
        if not self.current_session_id:
            return []

        path = os.path.join(SESSIONS_DIR, f"{self.current_session_id}.json")
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
        image_path: Optional[str],
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

        interaction = {
            "timestamp": time.time(),
            "prompt": prompt,
            "response": response,
            "extracted_text": extracted_text,
            "source": source_name,
        }

        if image_path and self.save_images and os.path.exists(image_path):
            # Copy image to sessions/images
            ext = os.path.splitext(image_path)[1] or ".png"
            image_filename = f"{uuid.uuid4()}{ext}"
            new_image_path = os.path.join(IMAGES_DIR, image_filename)
            try:
                shutil.copy2(image_path, new_image_path)
                interaction["image"] = new_image_path
            except Exception as e:
                print(f"[SessionManager] Warning: failed to save image: {e}")

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

    def append_transcription_segment(self, segment_text: str):
        """Appends a completed transcription segment to the active transcription file."""
        if (
            not self.save_transcriptions
            or not self.transcription_file
            or not segment_text
        ):
            logger.debug(
                f"[SessionManager] Cannot append segment. save_trans={self.save_transcriptions}, file={self.transcription_file}, text='{segment_text}'"
            )
            return

        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                # We simply append the completed segment text on a new line
                f.write(f"{segment_text}\n")
            logger.debug(
                f"[SessionManager] Appended segment to {self.transcription_file}: '{segment_text}'"
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
        """Legacy method to save interactions. We don't write the user prompt here if it's handled segment-by-segment."""
        if not self.transcription_file:
            logger.debug(
                "[SessionManager] Cannot save interaction. transcription_file is None."
            )
            return

        try:
            with open(self.transcription_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Add a visual separator and the AI response
                f.write(f"\n--- AI Response ({timestamp}) ---\n")
                f.write(f"{response}\n\n--- User ---\n")
            logger.debug(
                f"[SessionManager] Saved AI response to {self.transcription_file}"
            )
        except IOError as e:
            print(f"[SessionManager] Failed to save transcription to file: {e}")
            logger.error(f"[SessionManager] Failed to save transcription to file: {e}")

    def _save_session_data(self, history: List[Dict[str, Any]]):
        if not self.current_session_id:
            return

        path = os.path.join(SESSIONS_DIR, f"{self.current_session_id}.json")
        data = {
            "id": self.current_session_id,
            "title": self.title,
            "updated_at": time.time(),
            "history": history,
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except IOError as e:
            print(f"[SessionManager] Failed to save session data: {e}")

    def _close_transcription_file(self):
        # Python handles file closing automatically, but we can reset the path
        if self.transcription_file:
            logger.debug(
                f"[SessionManager] Closing transcription file tracking for: {self.transcription_file}"
            )
        self.transcription_file = None

    def cleanup(self):
        """Perform any necessary cleanup."""
        self._close_transcription_file()
