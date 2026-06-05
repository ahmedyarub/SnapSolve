"""TextInputWidget — text entry overlay with prompt history."""
import json
import logging
import os
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QTextEdit,
)

from core.ui.mixins import DraggableWidgetMixin, _DragHandleBar
from core.ui.signals import _app_callbacks


class TextInputWidget(DraggableWidgetMixin, QWidget):
    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._bg_opacity = 0.8
        self.setStyleSheet(
            "background-color: rgba(30, 30, 30, 204); border: 2px solid #555; border-radius: 8px;"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 4, 10, 10)

        # Drag Handle Bar
        self.drag_handle = _DragHandleBar(self)
        self.layout.addWidget(self.drag_handle)

        self.text_edit = QTextEdit()
        self.text_edit.setStyleSheet(
            "background-color: rgba(45, 45, 45, 180); color: white; border: none; font-size: 16px; padding: 5px;"
        )
        # Handle Enter key to submit, Shift+Enter for new line, Up/Down for history
        self.text_edit.installEventFilter(self)
        self.layout.addWidget(self.text_edit)

        self.is_processing = False

        # Prompt history — loaded from config, newest entry last
        self._prompt_history: list[str] = self._load_prompt_history()
        # -1 means "not browsing history" (showing the live draft)
        self._history_index: int = -1
        # Stash the in-progress text while the user browses history
        self._draft_text: str = ""

    def _apply_opacity(self, opacity: float):
        """Apply opacity via RGBA backgrounds to the widget, drag handle, and text edit."""
        self._bg_opacity = opacity
        alpha_int = int(opacity * 255)
        self.setStyleSheet(
            f"background-color: rgba(30, 30, 30, {alpha_int});"
            f" border: 2px solid #555; border-radius: 8px;"
        )
        self.drag_handle._apply_opacity(opacity)
        self.text_edit.setStyleSheet(
            f"background-color: rgba(45, 45, 45, {alpha_int}); color: white;"
            f" border: none; font-size: 16px; padding: 5px;"
        )

    @staticmethod
    def _is_return_key_event(event):
        """Check if event is return key event."""
        return event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter

    @staticmethod
    def _is_shift_modifier_pressed(event):
        """Check if shift modifier is pressed."""
        return event.modifiers() & Qt.KeyboardModifier.ShiftModifier

    def _handle_text_submission(self):
        """Handle text submission."""
        text = self.text_edit.toPlainText().strip()
        if text:
            self.text_edit.clear()
            self._add_to_history(text)
            self._history_index = -1
            self._draft_text = ""
            if "text_submit" in _app_callbacks:
                threading.Thread(
                    target=_app_callbacks["text_submit"],
                    args=(text,),
                    daemon=True,
                ).start()

    # --- Prompt history helpers ---

    _HISTORY_FILE = os.path.join("config", "prompt_history.json")

    @staticmethod
    def _load_prompt_history() -> list[str]:
        """Load prompt history from its dedicated JSON file."""
        try:
            if os.path.exists(TextInputWidget._HISTORY_FILE):
                with open(TextInputWidget._HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                return list(history) if isinstance(history, list) else []
        except Exception:
            pass
        return []

    def _save_prompt_history(self) -> None:
        """Persist prompt history to its dedicated JSON file."""
        try:
            os.makedirs(os.path.dirname(self._HISTORY_FILE), exist_ok=True)
            with open(self._HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._prompt_history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to save prompt history: {e}")

    def _add_to_history(self, text: str) -> None:
        """Append *text* to history, deduplicating consecutive entries."""
        if self._prompt_history and self._prompt_history[-1] == text:
            return  # Skip duplicate of the most recent entry
        self._prompt_history.append(text)
        # Cap the list length
        max_items = 100
        try:
            from config.settings import load_config
            max_items = load_config().get("max_prompt_history", 100)
        except Exception:
            pass
        if len(self._prompt_history) > max_items:
            self._prompt_history = self._prompt_history[-max_items:]
        self._save_prompt_history()

    def _navigate_history(self, direction: int) -> bool:
        """Move through history. *direction* is -1 (older / Up) or +1 (newer / Down).

        Returns True if the event was consumed.
        """
        if not self._prompt_history:
            return False

        if self._history_index == -1:
            if direction == 1:
                return False  # Already at newest
            # Stash current draft before entering history
            self._draft_text = self.text_edit.toPlainText()
            self._history_index = len(self._prompt_history)  # one past end

        new_index = self._history_index + direction

        if new_index < 0:
            return True  # Already at oldest — stay put

        if new_index >= len(self._prompt_history):
            # Returned past newest — restore draft
            self._history_index = -1
            self.text_edit.setPlainText(self._draft_text)
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.text_edit.setTextCursor(cursor)
            return True

        self._history_index = new_index
        self.text_edit.setPlainText(self._prompt_history[new_index])
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
        return True

    @staticmethod
    def _is_up_key(event) -> bool:
        return event.key() == Qt.Key.Key_Up

    @staticmethod
    def _is_down_key(event) -> bool:
        return event.key() == Qt.Key.Key_Down

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event):
        if obj is self.text_edit and event.type() == event.Type.KeyPress:
            if self._is_return_key_event(event):
                if self._is_shift_modifier_pressed(event):
                    return False
                else:
                    if not self.is_processing:
                        self._handle_text_submission()
                    return True
            if self._is_up_key(event) and not self._is_shift_modifier_pressed(event):
                if self._navigate_history(-1):
                    return True
            if self._is_down_key(event) and not self._is_shift_modifier_pressed(event):
                if self._navigate_history(1):
                    return True
        return super().eventFilter(obj, event)

    def update_position(self):
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        h = 100  # Fixed initial height
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

    def set_processing_state(self, is_processing):
        self.is_processing = is_processing
        self.text_edit.setEnabled(not is_processing)
        if not is_processing:
            self.text_edit.setFocus()

    def set_ocr_text(self, text: str):
        """Populate the text box with OCR'd text.

        If the text box already has content, appends the new text with a
        double-newline separator to preserve user edits.
        """
        current = self.text_edit.toPlainText()
        if current.strip():
            self.text_edit.setPlainText(current + "\n\n" + text)
        else:
            self.text_edit.setPlainText(text)
        # Move cursor to end
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
