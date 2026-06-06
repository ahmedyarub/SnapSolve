import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut, QDesktopServices
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTextEdit,
    QTextBrowser,
    QLineEdit,
    QLabel,
    QMenu,
    QInputDialog,
    QMessageBox,
    QStatusBar,
    QWidget,
    QApplication,
    QAbstractItemView,
    QPushButton,
)

from core.output import _PopupWebPage
from core.session_manager import SessionManager
from ui.timeline_widget import SessionTimelineWidget


_PANE_HEADER_HEIGHT = 28


class _CollapsiblePane(QWidget):
    """A widget with a header bar and a collapsible content area.

    When collapsed, the pane shrinks to just the header bar and signals
    the parent splitter to reclaim the freed space.
    """

    def __init__(
        self,
        title: str,
        color: str,
        content_widget: QWidget,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._content_widget = content_widget
        self._collapsed = False
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(_PANE_HEADER_HEIGHT)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 2, 4, 2)
        h_layout.setSpacing(6)

        self._label = QLabel(title)
        self._label.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color};"
            " padding: 2px 0; background: transparent;"
        )
        h_layout.addWidget(self._label)
        h_layout.addStretch()

        self._btn = QPushButton("▼")
        self._btn.setFixedSize(20, 20)
        self._btn.setToolTip("Collapse / Expand")
        self._btn.setStyleSheet("""
            QPushButton {
                background-color: #282c34; color: #8b95a7;
                border: 1px solid #333840; border-radius: 3px;
                font-size: 9px; font-weight: bold;
            }
            QPushButton:hover { background-color: #3e4451; color: #61afef; }
        """)
        self._btn.clicked.connect(self.toggle)
        h_layout.addWidget(self._btn)

        layout.addWidget(header)
        layout.addWidget(content_widget)

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._content_widget.hide()
            self.setFixedHeight(_PANE_HEADER_HEIGHT)
            self._btn.setText("▶")
        else:
            self._content_widget.show()
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self._btn.setText("▼")

    @property
    def collapsed(self) -> bool:
        return self._collapsed


class _ImageLabel(QLabel):
    """A QLabel that correctly scales its pixmap while maintaining aspect ratio,
    without artificially forcing the layout to grow."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pixmap: Optional[QPixmap] = None

    def setPixmap(self, p: QPixmap) -> None:
        self._pixmap = p
        self.update()

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            super().paintEvent(event)


# --- Tag badge colors (cycled for variety) ---
_TAG_COLORS = [
    "#e06c75", "#61afef", "#98c379", "#d19a66", "#c678dd",
    "#56b6c2", "#e5c07b", "#be5046", "#7ec8e3", "#c3e88d",
]


def _tag_color(tag: str) -> str:
    """Deterministic color for a tag string."""
    return _TAG_COLORS[hash(tag) % len(_TAG_COLORS)]


class SessionBrowserDialog(QDialog):
    """Maximized dialog for browsing past sessions, prompts, and formatted responses."""

    def __init__(self, parent: Optional[QWidget] = None, selection_mode: bool = False):
        super().__init__(parent)
        self.selection_mode = selection_mode
        title = "Select Session — SnapSolve" if selection_mode else "Session Browser — SnapSolve"
        self.setWindowTitle(title)

        # Standard window with minimize/maximize/close + always on top
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # Load app icon (same as system tray)
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            self.setWindowIcon(QIcon())

        # Instance attributes
        self._sessions_meta: list[dict] = []
        self._loaded_sessions: dict[str, dict] = {}
        self._current_session_id: Optional[str] = None
        self._response_loaded = False
        self._pending_response_js: list[str] = []
        self._response_page: _PopupWebPage | None = None
        self.selected_session_id: Optional[str] = None
        self._empty_count: int = 0
        self.btn_delete_empty: QPushButton | None = None
        self.timeline: SessionTimelineWidget | None = None
        self.screenshot_label: QLabel | None = None
        self.screenshot_pane: _CollapsiblePane | None = None
        self.prompt_pane: _CollapsiblePane | None = None
        self.response_pane: _CollapsiblePane | None = None

        # Build UI
        self._build_ui()
        self._apply_dark_theme()
        self._load_sessions()

    # ------------------------------------------------------------------ #
    #  UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Filter bar ---
        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(12, 8, 12, 4)
        filter_icon = QLabel("🔍")
        filter_icon.setStyleSheet("font-size: 16px; background: transparent;")
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by tag or session name…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(filter_icon)
        filter_bar.addWidget(self.filter_input)

        # "Delete Empty Sessions" button
        self.btn_delete_empty = QPushButton("🗑️ Delete Empty")
        self.btn_delete_empty.setToolTip(
            "Delete all sessions with no interactions and no screenshots"
        )
        self.btn_delete_empty.setStyleSheet("""
            QPushButton {
                background-color: #3e4451; color: #e06c75; font-weight: bold;
                border: 1px solid #e06c75; border-radius: 4px; padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4b5263; }
            QPushButton:disabled { color: #636d83; border-color: #636d83; }
        """)
        self.btn_delete_empty.clicked.connect(self._handle_delete_empty_sessions)
        filter_bar.addWidget(self.btn_delete_empty)

        root_layout.addLayout(filter_bar)

        # --- Main horizontal splitter ---
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: session tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setAnimated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        if self.selection_mode:
            self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.h_splitter.addWidget(self.tree)

        # Delete key shortcut
        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.tree)
        delete_shortcut.activated.connect(self._handle_delete_selected)

        # Right: vertical splitter with 3 collapsible panes
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Screenshot pane ──
        self.screenshot_label = _ImageLabel()
        self.screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screenshot_label.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #333840; border-radius: 4px;"
        )
        self.screenshot_label.setScaledContents(False)
        self.screenshot_label.setWordWrap(True)
        self.screenshot_label.setText(
            '<span style="color:#636d83; font-style:italic;">'
            'Select a screenshot from the timeline</span>'
        )
        self.screenshot_pane = _CollapsiblePane(
            "📸 Screenshot", "#d19a66", self.screenshot_label
        )
        self.v_splitter.addWidget(self.screenshot_pane)

        # ── Prompt pane ──
        self.prompt_view = QTextBrowser()
        self.prompt_view.setOpenLinks(False)
        self.prompt_view.anchorClicked.connect(QDesktopServices.openUrl)
        self.prompt_view.setReadOnly(True)
        self.prompt_pane = _CollapsiblePane(
            "📝 Prompt", "#61afef", self.prompt_view
        )
        self.v_splitter.addWidget(self.prompt_pane)

        # ── Response pane ──
        response_wrapper = QWidget()
        response_wrapper_layout = QVBoxLayout(response_wrapper)
        response_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        response_wrapper_layout.setSpacing(0)
        self.response_view = QWebEngineView()
        self._response_page = _PopupWebPage(self.response_view)
        self.response_view.setPage(self._response_page)
        self.response_view.settings().setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._response_page.setBackgroundColor(QColor(30, 30, 30))
        self.response_view.loadFinished.connect(self._on_response_loaded)
        response_wrapper_layout.addWidget(self.response_view)
        self.response_pane = _CollapsiblePane(
            "💬 Response", "#98c379", response_wrapper
        )
        self.v_splitter.addWidget(self.response_pane)

        # Default split: 25% screenshot, 25% prompt, 50% response
        self.v_splitter.setSizes([200, 200, 400])

        self.h_splitter.addWidget(self.v_splitter)

        # Default split: 30% tree, 70% content
        self.h_splitter.setSizes([350, 850])

        # --- Outer vertical splitter: content above, timeline below ---
        self.outer_v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.outer_v_splitter.addWidget(self.h_splitter)

        # Timeline widget
        self.timeline = SessionTimelineWidget()
        self.timeline.screenshotSelected.connect(self._on_timeline_screenshot_selected)
        self.timeline.interactionSelected.connect(self._on_timeline_interaction_selected)
        self.outer_v_splitter.addWidget(self.timeline)

        # Default split: 70% content, 30% timeline
        self.outer_v_splitter.setSizes([600, 280])

        root_layout.addWidget(self.outer_v_splitter, stretch=1)

        # --- Status bar and Optional Select Button ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "QStatusBar { background: #21252b; color: #636d83; font-size: 12px;"
            " border-top: 1px solid #333840; padding: 2px 8px; }"
        )
        bottom_layout.addWidget(self.status_bar, stretch=1)
        
        if self.selection_mode:
            self.btn_select = QPushButton("✔️ Select Session")
            self.btn_select.setStyleSheet("""
                QPushButton {
                    background-color: #61afef; color: #282c34; font-weight: bold;
                    border: none; border-radius: 4px; padding: 6px 16px; margin: 4px;
                }
                QPushButton:hover { background-color: #528bff; }
                QPushButton:disabled { background-color: #3e4451; color: #abb2bf; }
            """)
            self.btn_select.setEnabled(False)
            self.btn_select.clicked.connect(self._accept_selection)
            bottom_layout.addWidget(self.btn_select)

        root_layout.addLayout(bottom_layout)

        # Load the popup.html for response rendering
        assets_dir = Path(__file__).parent.parent / "core" / "web_assets"
        popup_html = assets_dir / "popup.html"
        self.response_view.setUrl(QUrl.fromLocalFile(str(popup_html)))

    # ------------------------------------------------------------------ #
    #  Dark theme
    # ------------------------------------------------------------------ #

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #282c34;
                color: #abb2bf;
            }
            QSplitter::handle {
                background-color: #333840;
            }
            QSplitter::handle:horizontal { width: 3px; }
            QSplitter::handle:vertical   { height: 3px; }
            QTreeWidget {
                background-color: #21252b;
                color: #abb2bf;
                border: none;
                font-size: 13px;
                padding: 4px;
            }
            QTreeWidget::item {
                padding: 4px 6px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #2c313a;
                color: #e5c07b;
            }
            QTreeWidget::item:hover {
                background-color: #2c313a;
            }
            QTextEdit {
                background-color: #1e2127;
                color: #c8ccd4;
                border: 1px solid #333840;
                border-radius: 6px;
                font-family: 'Consolas', 'Fira Code', 'Courier New', monospace;
                font-size: 13px;
                padding: 8px;
                selection-background-color: #3e4451;
            }
            QLineEdit {
                background-color: #21252b;
                color: #abb2bf;
                border: 1px solid #333840;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                selection-background-color: #3e4451;
            }
            QLineEdit:focus {
                border-color: #528bff;
            }
            QWebEngineView {
                border: 1px solid #333840;
                border-radius: 6px;
            }
            /* Scrollbar styling */
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 8px;
            }
            QScrollBar::handle:horizontal {
                background: #555;
                border-radius: 4px;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }
        """)

    # ------------------------------------------------------------------ #
    #  Data loading
    # ------------------------------------------------------------------ #

    def _load_sessions(self):
        self._sessions_meta = SessionManager.list_all_sessions()
        self._empty_count = SessionManager.count_empty_sessions()
        self._populate_tree()

    def _populate_tree(self, filter_text: str = ""):
        self.tree.clear()
        filter_lower = filter_text.strip().lower()

        total_prompts = 0
        visible_sessions = 0

        for idx, meta in enumerate(self._sessions_meta):
            # Filter logic: match on name, title, or tags
            if filter_lower:
                searchable = " ".join([
                    meta.get("name") or "",
                    meta.get("title") or "",
                    " ".join(meta.get("tags", [])),
                ]).lower()
                if filter_lower not in searchable:
                    continue

            visible_sessions += 1

            # Build root item text
            dt = datetime.fromtimestamp(meta["updated_at"])
            date_str = dt.strftime("%Y-%m-%d  %H:%M")
            display_name = meta.get("name") or meta.get("title") or "(untitled)"
            root_text = f"📁  {date_str}  —  {display_name}"

            root_item = QTreeWidgetItem([root_text])
            root_item.setData(0, Qt.ItemDataRole.UserRole, meta["id"])
            root_item.setData(0, Qt.ItemDataRole.UserRole + 1, "session")

            # Font for root items
            font = QFont()
            font.setBold(True)
            font.setPointSize(10)
            root_item.setFont(0, font)

            if meta["interaction_count"] == 0:
                root_item.setForeground(0, QColor("#636d83"))

            # Add tag badges as a tooltip and suffix
            tags = meta.get("tags", [])
            if tags:
                tag_parts = []
                for t in tags:
                    tag_parts.append(f"[{t}]")
                root_item.setText(0, root_text + "  " + " ".join(tag_parts))
                root_item.setToolTip(0, "Tags: " + ", ".join(tags))

                # Color the tag text
                for t in tags:
                    color = _tag_color(t)
                    # We'll use the foreground of the item for tag visualization
                    # Since QTreeWidgetItem doesn't support rich text natively,
                    # tags are shown in brackets. Use tooltip for full info.
                    root_item.setToolTip(0, "Tags: " + ", ".join(tags))

            self.tree.addTopLevelItem(root_item)

            # Load interaction excerpts (lazy — only populate children for first load)
            self._populate_session_children(root_item, meta["id"])
            total_prompts += meta["interaction_count"]

            # Expand only the latest session (first in sorted order)
            if idx == 0 and not filter_lower:
                root_item.setExpanded(True)

        self.status_bar.showMessage(
            f"{visible_sessions} sessions  •  {total_prompts} prompts"
            f"  •  {self._empty_count} empty (hidden)"
        )
        if self.btn_delete_empty is not None:
            self.btn_delete_empty.setEnabled(self._empty_count > 0)

    def _populate_session_children(self, root_item: QTreeWidgetItem, session_id: str):
        """Add prompt excerpt children to a session root item."""
        data = self._get_session_data(session_id)
        if not data:
            return

        history = data.get("history", [])
        for i, interaction in enumerate(history):
            prompt = interaction.get("prompt", "")
            excerpt = prompt.replace("\n", " ").strip()[:100]
            if len(prompt.strip()) > 100:
                excerpt += "…"
            if not excerpt:
                excerpt = "(empty prompt)"

            # Source type icon
            source = interaction.get("source", "text")
            
            # Retroactive fix for old sessions
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

            from ui.timeline_widget import _EVENT_ICONS
            icon = _EVENT_ICONS.get(source, "💬")

            child = QTreeWidgetItem([f"{icon}  {excerpt}"])
            child.setData(0, Qt.ItemDataRole.UserRole, session_id)
            child.setData(0, Qt.ItemDataRole.UserRole + 1, "prompt")
            child.setData(0, Qt.ItemDataRole.UserRole + 2, i)

            child_font = QFont()
            child_font.setPointSize(9)
            child.setFont(0, child_font)
            child.setForeground(0, QColor("#8b95a7"))

            root_item.addChild(child)

    def _get_session_data(self, session_id: str) -> Optional[dict]:
        """Get session data, using cache."""
        if session_id not in self._loaded_sessions:
            data = SessionManager.load_session_data(session_id)
            if data:
                self._loaded_sessions[session_id] = data
        return self._loaded_sessions.get(session_id)

    # ------------------------------------------------------------------ #
    #  Tree interaction
    # ------------------------------------------------------------------ #

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous: QTreeWidgetItem):
        if current is None:
            return

        item_type = current.data(0, Qt.ItemDataRole.UserRole + 1)
        if item_type != "prompt":
            # Clicked a session root — load timeline + clear panels
            session_id = current.data(0, Qt.ItemDataRole.UserRole)
            if session_id and self.timeline:
                self._current_session_id = session_id
                self.timeline.load_session(session_id)
            self.prompt_view.clear()
            self._render_response("")
            return

        session_id = current.data(0, Qt.ItemDataRole.UserRole)
        prompt_index = current.data(0, Qt.ItemDataRole.UserRole + 2)

        data = self._get_session_data(session_id)
        if not data:
            return

        history = data.get("history", [])
        if prompt_index < 0 or prompt_index >= len(history):
            return

        interaction = history[prompt_index]

        # Show speaker name in prompt header
        speaker = interaction.get("speaker_name", "")
        prompt_text = interaction.get("prompt", "")

        import os
        from core.session_manager import _session_dir
        import html

        # Build prompt display with metadata
        display_parts = []
        if speaker:
            display_parts.append(f"<b>[{html.escape(speaker)}]</b>")

        source = interaction.get("source", "text")
        if source != "text":
            display_parts.append(f"<i>({html.escape(source)})</i>")

        images_data = interaction.get("image", [])
        if isinstance(images_data, str):
            images_data = [images_data] if images_data else []

        for img in images_data:
            abs_image_path = os.path.abspath(os.path.join(_session_dir(session_id), img))
            abs_image_path_fwd = abs_image_path.replace(os.sep, '/')
            file_url = f"file:///{abs_image_path_fwd}"
            display_parts.append(f"📎 <a href='{file_url}' style='color: #61afef;'>{html.escape(img)}</a>")

        transcription_file = data.get("transcription_file")
        if transcription_file:
            abs_trans_path = os.path.abspath(os.path.join(_session_dir(session_id), transcription_file))
            if os.path.exists(abs_trans_path):
                trans_url = f"file:///{abs_trans_path.replace(os.sep, '/')}"
                display_parts.append(f"📝 <a href='{trans_url}' style='color: #98c379;'>{html.escape(transcription_file)}</a>")

        header = "  ".join(display_parts)
        prompt_html = html.escape(prompt_text).replace("\n", "<br>")

        full_prompt = f'''
        <div style="font-family: monospace; font-size: 13px;">
            <div style="margin-bottom: 8px;">{header}</div>
            <div style="border-top: 1px solid #555; margin-bottom: 8px;"></div>
            <div>{prompt_html}</div>
        </div>
        ''' if header else f'<div style="font-family: monospace; font-size: 13px;">{prompt_html}</div>'

        for img in images_data:
            abs_image_path = os.path.abspath(os.path.join(_session_dir(session_id), img))
            abs_image_path_fwd = abs_image_path.replace(os.sep, '/')
            
            from PyQt6.QtGui import QImageReader
            reader = QImageReader(abs_image_path)
            size = reader.size()
            
            # Default to a reasonable width if read fails
            img_w = size.width() if size.width() > 0 else 800
            
            # Scale down to fit the panel nicely, but keep it large ("expanded")
            display_width = min(img_w, 750) 
            
            full_prompt += f"<br><br><img src='{abs_image_path_fwd}' width='{display_width}'>"

        self.prompt_view.setHtml(full_prompt)
        self._render_response(interaction.get("response", ""))

        # Navigate the timeline to this interaction's timestamp
        if self.timeline and session_id:
            if self._current_session_id != session_id:
                self._current_session_id = session_id
                self.timeline.load_session(session_id)
            self.timeline.navigate_to_interaction(prompt_index)

        if self.selection_mode:
            self.btn_select.setEnabled(True)

    def _on_tree_double_click(self, item: QTreeWidgetItem, column: int):
        if not self.selection_mode:
            return
            
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        session_id = item.data(0, Qt.ItemDataRole.UserRole)
        if session_id:
            self.selected_session_id = session_id
            self.accept()
            
    def _accept_selection(self):
        current = self.tree.currentItem()
        if current:
            self.selected_session_id = current.data(0, Qt.ItemDataRole.UserRole)
            if self.selected_session_id:
                self.accept()

    def _render_response(self, markdown_text: str):
        """Render markdown response in the QWebEngineView using popup.html's updateContent."""
        js_text = json.dumps(markdown_text)
        js_code = f"updateContent({js_text});"

        if self._response_loaded:
            self.response_view.page().runJavaScript(js_code)
        else:
            self._pending_response_js.clear()
            self._pending_response_js.append(js_code)

    def _on_response_loaded(self, ok: bool):
        self._response_loaded = True
        for js in self._pending_response_js:
            self.response_view.page().runJavaScript(js)
        self._pending_response_js.clear()

    # ------------------------------------------------------------------ #
    #  Timeline signal handlers
    # ------------------------------------------------------------------ #

    def _on_timeline_screenshot_selected(self, path: str):
        """Display a full-resolution screenshot in the dedicated screenshot pane."""
        import os
        from datetime import datetime

        if not self.screenshot_label:
            return

        abs_path = os.path.abspath(path)
        pix = QPixmap(abs_path)
        if pix.isNull():
            self.screenshot_label.setText(
                '<span style="color:#e06c75;">Failed to load screenshot</span>'
            )
            return

        self.screenshot_label.setPixmap(pix)

        # Update pane header with timestamp
        fname = os.path.basename(path)
        stem = os.path.splitext(fname)[0]
        try:
            dt = datetime.strptime(stem, "%Y-%m-%d_%H-%M-%S")
            time_str = dt.strftime("%H:%M:%S")
        except ValueError:
            time_str = fname

        if self.screenshot_pane:
            self.screenshot_pane._label.setText(f"📸 Screenshot at {time_str}")

    def _on_timeline_interaction_selected(self, index: int):
        """Select the corresponding prompt child in the tree when an event marker is clicked."""
        if not self._current_session_id:
            return

        # Find the session root item
        for i in range(self.tree.topLevelItemCount()):
            root_item = self.tree.topLevelItem(i)
            if root_item is None:
                continue
            sid = root_item.data(0, Qt.ItemDataRole.UserRole)
            if sid != self._current_session_id:
                continue

            # Find the child at the given interaction index
            if index < root_item.childCount():
                child = root_item.child(index)
                # Expand parent and select child (block signals to avoid loop)
                root_item.setExpanded(True)
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(child)
                self.tree.blockSignals(False)
                # Manually trigger the selection handler
                self._on_tree_selection(child, None)
            break

    # ------------------------------------------------------------------ #
    #  Context menu (rename / tags)
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item is None:
            return

        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if item_type != "session":
            # For prompt items, find the parent session
            parent = item.parent()
            if parent and parent.data(0, Qt.ItemDataRole.UserRole + 1) == "session":
                item = parent
            else:
                return

        session_id = item.data(0, Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #21252b;
                color: #abb2bf;
                border: 1px solid #333840;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c313a;
                color: #e5c07b;
            }
        """)

        rename_action = menu.addAction("✏️  Rename Session")
        tags_action = menu.addAction("🏷️  Edit Tags")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️  Delete Session")

        # Check if multiple sessions are selected
        selected_session_ids = self._get_selected_session_ids()
        if len(selected_session_ids) > 1:
            delete_action.setText(f"🗑️  Delete {len(selected_session_ids)} Sessions")

        action = menu.exec(self.tree.viewport().mapToGlobal(position))

        if action == rename_action:
            self._handle_rename(session_id, item)
        elif action == tags_action:
            self._handle_edit_tags(session_id, item)
        elif action == delete_action:
            if len(selected_session_ids) > 1:
                self._handle_delete_sessions(selected_session_ids)
            else:
                self._handle_delete_sessions([session_id])

    def _handle_rename(self, session_id: str, tree_item: QTreeWidgetItem):
        data = self._get_session_data(session_id)
        current_name = ""
        if data:
            current_name = data.get("name") or data.get("title") or ""

        new_name, ok = QInputDialog.getText(
            self, "Rename Session", "New name:", text=current_name
        )
        if ok and new_name.strip():
            SessionManager.rename_session(session_id, new_name.strip())
            # Invalidate cache
            self._loaded_sessions.pop(session_id, None)
            # Refresh tree
            self._load_sessions()

    def _handle_edit_tags(self, session_id: str, tree_item: QTreeWidgetItem):
        data = self._get_session_data(session_id)
        current_tags = []
        if data:
            current_tags = data.get("tags", [])

        tags_str, ok = QInputDialog.getText(
            self,
            "Edit Tags",
            "Tags (comma-separated):",
            text=", ".join(current_tags),
        )
        if ok:
            new_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            SessionManager.set_session_tags(session_id, new_tags)
            # Invalidate cache
            self._loaded_sessions.pop(session_id, None)
            # Refresh tree
            self._load_sessions()

    # ------------------------------------------------------------------ #
    #  Delete
    # ------------------------------------------------------------------ #

    def _get_selected_session_ids(self) -> list[str]:
        """Get unique session IDs from all selected tree items."""
        session_ids: list[str] = []
        seen: set[str] = set()
        for item in self.tree.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "session":
                sid = item.data(0, Qt.ItemDataRole.UserRole)
            else:
                parent = item.parent()
                if parent:
                    sid = parent.data(0, Qt.ItemDataRole.UserRole)
                else:
                    continue
            if sid and sid not in seen:
                seen.add(sid)
                session_ids.append(sid)
        return session_ids

    def _handle_delete_selected(self):
        """Handle Delete key press — delete all selected sessions."""
        session_ids = self._get_selected_session_ids()
        if session_ids:
            self._handle_delete_sessions(session_ids)

    def _handle_delete_sessions(self, session_ids: list[str]):
        """Delete one or more sessions with confirmation."""
        count = len(session_ids)
        if count == 0:
            return

        if count == 1:
            data = self._get_session_data(session_ids[0])
            name = ""
            if data:
                name = data.get("name") or data.get("title") or session_ids[0][:8]
            msg = f"Delete session \"{name}\" and all its contents?\n\nThis action cannot be undone."
        else:
            msg = f"Delete {count} selected sessions and all their contents?\n\nThis action cannot be undone."

        reply = QMessageBox.warning(
            self,
            "Confirm Deletion",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        for sid in session_ids:
            if SessionManager.delete_session(sid):
                self._loaded_sessions.pop(sid, None)
                deleted += 1

        # Clear panels and refresh
        self.prompt_view.clear()
        self._render_response("")
        self._load_sessions()
        self.status_bar.showMessage(f"Deleted {deleted} session(s)", 5000)

    def _handle_delete_empty_sessions(self):
        """Delete all empty sessions (no interactions and no screenshots)."""
        if self._empty_count == 0:
            return

        reply = QMessageBox.warning(
            self,
            "Delete Empty Sessions",
            f"Delete {self._empty_count} empty session(s) with no interactions"
            f" and no screenshots?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = SessionManager.delete_empty_sessions()
        self._loaded_sessions.clear()
        self.prompt_view.clear()
        self._render_response("")
        self._load_sessions()
        self.status_bar.showMessage(f"Deleted {deleted} empty session(s)", 5000)

    # ------------------------------------------------------------------ #
    #  Filter
    # ------------------------------------------------------------------ #

    def _apply_filter(self, text: str):
        self._populate_tree(filter_text=text)
        # Expand all when filtering
        if text.strip():
            for i in range(self.tree.topLevelItemCount()):
                self.tree.topLevelItem(i).setExpanded(True)

    # ------------------------------------------------------------------ #
    #  Show maximized
    # ------------------------------------------------------------------ #

    # noinspection PyPep8Naming
    def showEvent(self, event):
        super().showEvent(event)
        if not self.isMaximized():
            self.showMaximized()


def open_session_browser(parent: Optional[QWidget] = None):
    """Create and show the session browser dialog."""
    dialog = SessionBrowserDialog(parent)
    dialog.exec()

def select_session(parent: Optional[QWidget] = None) -> Optional[str]:
    """Open the browser in selection mode and return the selected session ID."""
    dialog = SessionBrowserDialog(parent, selection_mode=True)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selected_session_id
    return None
