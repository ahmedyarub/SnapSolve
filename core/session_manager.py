import json
import os
import shutil
import uuid
import time
from typing import List, Dict, Any, Optional

SESSIONS_DIR = "sessions"
IMAGES_DIR = os.path.join(SESSIONS_DIR, "images")


class SessionManager:
    def __init__(self, config: dict):
        self.config = config
        self.save_images = config.get("save_images", False)
        self.current_session_id = None
        self.title = None

        # Ensure directories exist
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        os.makedirs(IMAGES_DIR, exist_ok=True)

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
        self._save_session_data([])
        print(f"[SessionManager] Started new session: {self.current_session_id}")
        return self.current_session_id

    def _load_session(self, session_id: str):
        path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(path):
            self.current_session_id = session_id
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

        history.append(interaction)
        self._save_session_data(history)

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
