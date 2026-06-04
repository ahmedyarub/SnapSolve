import json
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QGroupBox, QMessageBox, QCompleter
)
from PyQt6.QtCore import Qt
from ui.session_browser import select_session

_RECENT_FOLDERS_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "recent_folders.json")
_MAX_RECENT_FOLDERS = 20


def _load_recent_folders() -> list[str]:
    """Load recent project folder paths from disk."""
    try:
        with open(_RECENT_FOLDERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data[:_MAX_RECENT_FOLDERS]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _save_recent_folders(folders: list[str]):
    """Persist recent project folder paths to disk."""
    try:
        with open(_RECENT_FOLDERS_FILE, "w", encoding="utf-8") as f:
            json.dump(folders[:_MAX_RECENT_FOLDERS], f, indent=2)
    except OSError:
        pass


def _add_recent_folder(folder: str):
    """Add a folder to the recent list (most recent first, no duplicates)."""
    if not folder or not folder.strip():
        return
    folder = folder.strip()
    folders = _load_recent_folders()
    if folder in folders:
        folders.remove(folder)
    folders.insert(0, folder)
    _save_recent_folders(folders[:_MAX_RECENT_FOLDERS])


class ContextManagerDialog(QDialog):
    def __init__(self, session_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Context Manager — SnapSolve")
        self.setMinimumWidth(400)
        self.session_manager = session_manager

        self.config = self.session_manager.get_context_config()

        # UI widgets (defined before _build_ui)
        self.cb_transcribed = None
        self.cb_questions = None
        self.cb_answers = None
        self.folder_input = None
        self.folder_completer = None
        self.btn_browse = None
        self.btn_import = None
        self.btn_save = None
        self.btn_cancel = None

        self._build_ui()
        self._apply_dark_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Categories
        cat_group = QGroupBox("Context Categories")
        cat_layout = QVBoxLayout(cat_group)

        self.cb_transcribed = QCheckBox("Include Transcribed Text")
        self.cb_transcribed.setChecked(self.config.get("include_transcribed_text", False))
        cat_layout.addWidget(self.cb_transcribed)

        self.cb_questions = QCheckBox("Include Previous Questions")
        self.cb_questions.setChecked(self.config.get("include_previous_questions", False))
        cat_layout.addWidget(self.cb_questions)

        self.cb_answers = QCheckBox("Include Previous Answers")
        self.cb_answers.setChecked(self.config.get("include_previous_answers", False))
        cat_layout.addWidget(self.cb_answers)

        layout.addWidget(cat_group)

        # Project Folder
        folder_group = QGroupBox("Project Folder (Local Context)")
        folder_layout = QHBoxLayout(folder_group)
        self.folder_input = QLineEdit(self.config.get("project_folder", ""))
        self.folder_input.setPlaceholderText("Select project directory...")

        # Autocomplete from recent folder paths
        recent_folders = _load_recent_folders()
        self.folder_completer = QCompleter(recent_folders, self)
        self.folder_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.folder_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.folder_input.setCompleter(self.folder_completer)

        self.btn_browse = QPushButton("Browse")
        self.btn_browse.setAutoDefault(False)
        self.btn_browse.clicked.connect(self._browse_folder)
        folder_layout.addWidget(self.folder_input)
        folder_layout.addWidget(self.btn_browse)
        layout.addWidget(folder_group)

        # Import
        import_group = QGroupBox("Import Context")
        import_layout = QVBoxLayout(import_group)
        import_label = QLabel("Select a previous session to import the checked categories above.")
        import_label.setWordWrap(True)
        import_label.setStyleSheet("color: #8b95a7;")
        import_layout.addWidget(import_label)
        self.btn_import = QPushButton("📥 Import from Session...")
        self.btn_import.setAutoDefault(False)
        self.btn_import.clicked.connect(self._import_session)
        import_layout.addWidget(self.btn_import)
        layout.addWidget(import_group)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_save = QPushButton("Save")
        self.btn_save.setAutoDefault(False)
        self.btn_save.setStyleSheet("background-color: #61afef; color: #282c34; font-weight: bold;")
        self.btn_save.clicked.connect(self._save_and_close)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _browse_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Project Folder", self.folder_input.text())
        if dir_path:
            self.folder_input.setText(dir_path)

    def _import_session(self):
        session_id = select_session(self)
        if not session_id:
            return

        import_trans = self.cb_transcribed.isChecked()
        import_q = self.cb_questions.isChecked()
        import_a = self.cb_answers.isChecked()

        if not (import_trans or import_q or import_a):
            QMessageBox.information(self, "Import", "No categories selected to import.")
            return

        self.session_manager.import_context(
            source_session_id=session_id,
            import_transcribed_text=import_trans,
            import_questions=import_q,
            import_answers=import_a
        )
        QMessageBox.information(self, "Success", "Context successfully imported from session.")

    def _save_and_close(self):
        self.config["include_transcribed_text"] = self.cb_transcribed.isChecked()
        self.config["include_previous_questions"] = self.cb_questions.isChecked()
        self.config["include_previous_answers"] = self.cb_answers.isChecked()
        self.config["project_folder"] = self.folder_input.text()

        # Save folder to recent list for autocomplete
        _add_recent_folder(self.folder_input.text())

        self.session_manager.set_context_config(self.config)
        self.accept()

    def _apply_dark_theme(self):
        self.setStyleSheet('''
            QDialog { background-color: #282c34; color: #abb2bf; }
            QGroupBox { border: 1px solid #3e4451; border-radius: 6px; margin-top: 1ex; padding: 10px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #61afef; }
            QPushButton { background-color: #3e4451; color: #abb2bf; border: none; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #4b5263; }
            QLineEdit { background-color: #1e2127; color: #abb2bf; border: 1px solid #3e4451; border-radius: 4px; padding: 4px; }
            QCheckBox { color: #abb2bf; spacing: 8px; font-size: 13px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #3e4451; border-radius: 3px; background-color: #1e2127; }
            QCheckBox::indicator:checked { background-color: #61afef; border-color: #61afef; image: url(none); }
        ''')
