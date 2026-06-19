"""CorrectionPanelWidget — side panel for real-time speech corrections.

Displays fact-check, grammar, and content-suggestion corrections as
colour-coded cards that slide in during audio recording.
"""
import logging
import time

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QPushButton,
)

from core.ui.mixins import DraggableWidgetMixin
from core.ui.signals import ui_signals

logger = logging.getLogger(__name__)

# Badge colours per correction type
_TYPE_STYLES: dict[str, dict[str, str]] = {
    "fact_check": {
        "icon": "\U0001f50d",
        "label": "Fact Check",
        "bg": "rgba(59, 130, 246, 0.15)",
        "border": "rgba(59, 130, 246, 0.5)",
        "badge_bg": "#3b82f6",
    },
    "grammar": {
        "icon": "\u270f\ufe0f",
        "label": "Grammar",
        "bg": "rgba(249, 115, 22, 0.15)",
        "border": "rgba(249, 115, 22, 0.5)",
        "badge_bg": "#f97316",
    },
    "content_suggestion": {
        "icon": "\U0001f4a1",
        "label": "Suggestion",
        "bg": "rgba(16, 185, 129, 0.15)",
        "border": "rgba(16, 185, 129, 0.5)",
        "badge_bg": "#10b981",
    },
}

_CONFIDENCE_COLORS: dict[str, str] = {
    "HIGH": "#22c55e",
    "MEDIUM": "#eab308",
    "LOW": "#ef4444",
}


def _build_card_widget(correction: dict) -> QWidget:
    """Create a styled card widget for a single correction."""
    ctype = correction.get("type", "grammar")
    style = _TYPE_STYLES.get(ctype, _TYPE_STYLES["grammar"])
    confidence = correction.get("confidence", "MEDIUM")
    conf_color = _CONFIDENCE_COLORS.get(confidence, "#eab308")

    card = QWidget()
    card.setObjectName("correctionCard")
    card.setStyleSheet(f"""
        QWidget#correctionCard {{
            background-color: {style['bg']};
            border: 1px solid {style['border']};
            border-left: 4px solid {style['badge_bg']};
            border-radius: 6px;
            padding: 8px;
            margin: 2px 0;
        }}
    """)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(4)

    # --- Header row: badge + confidence ---
    header = QHBoxLayout()
    header.setSpacing(6)

    badge = QLabel(f"{style['icon']} {style['label']}")
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: {style['badge_bg']};
            color: white;
            font-size: 11px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 4px;
        }}
    """)
    header.addWidget(badge)

    header.addStretch()

    conf_dot = QLabel(f"\u25cf {confidence}")
    conf_dot.setStyleSheet(f"""
        QLabel {{
            color: {conf_color};
            font-size: 11px;
            font-weight: bold;
            background: transparent;
            border: none;
        }}
    """)
    header.addWidget(conf_dot)

    layout.addLayout(header)

    # --- Original text (struck-through / dimmed) ---
    original = correction.get("original", "")
    if original:
        orig_label = QLabel(f"\u201c{original}\u201d")
        orig_label.setWordWrap(True)
        orig_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.5);
                font-size: 12px;
                font-style: italic;
                text-decoration: line-through;
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(orig_label)

    # --- Corrected text (bold) ---
    corrected = correction.get("correction", "")
    if corrected:
        corr_label = QLabel(f"\u2192 {corrected}")
        corr_label.setWordWrap(True)
        corr_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.95);
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
        """)
        layout.addWidget(corr_label)

    # --- Explanation (collapsible) ---
    explanation = correction.get("explanation", "")
    if explanation:
        exp_label = QLabel(explanation)
        exp_label.setWordWrap(True)
        exp_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.65);
                font-size: 11px;
                background: transparent;
                border: none;
            }
        """)
        exp_label.setVisible(False)

        toggle_btn = QPushButton("Show details \u25be")
        toggle_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255, 255, 255, 0.5);
                font-size: 10px;
                background: transparent;
                border: none;
                text-align: left;
                padding: 0;
            }
            QPushButton:hover {
                color: rgba(255, 255, 255, 0.8);
            }
        """)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _toggle(checked=False, lbl=exp_label, btn=toggle_btn):
            visible = not lbl.isVisible()
            lbl.setVisible(visible)
            btn.setText("Hide details \u25b4" if visible else "Show details \u25be")

        toggle_btn.clicked.connect(_toggle)
        layout.addWidget(toggle_btn)
        layout.addWidget(exp_label)

    return card


class CorrectionPanelWidget(DraggableWidgetMixin, QWidget):
    """Side panel displaying real-time speech corrections."""

    MAX_CARDS = 20
    AUTO_HIDE_DELAY_MS = 10000  # Auto-hide 10s after last correction

    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Track cards for cleanup
        self._card_widgets: list[QWidget] = []
        self._last_correction_time: float = 0.0

        # --- Main layout ---
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Header ---
        header = QWidget()
        header.setObjectName("correctionHeader")
        header.setStyleSheet("""
            QWidget#correctionHeader {
                background-color: rgba(30, 30, 30, 0.95);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 8, 8)

        title = QLabel("\u26a1 Real-time Corrections")
        title.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.9);
                font-size: 13px;
                font-weight: bold;
                background: transparent;
                border: none;
            }
        """)
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._count_label = QLabel("0")
        self._count_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.6);
                font-size: 11px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 2px 6px;
                border: none;
            }
        """)
        header_layout.addWidget(self._count_label)

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                color: rgba(255, 255, 255, 0.5);
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: rgba(255, 255, 255, 0.9);
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        root_layout.addWidget(header)

        # --- Scrollable body ---
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: rgba(20, 20, 20, 0.92);
                border: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.05);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
                min-height: 20px;
            }
        """)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(8, 8, 8, 8)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()

        self._scroll_area.setWidget(self._cards_container)
        root_layout.addWidget(self._scroll_area)

        # --- Empty state ---
        self._empty_label = QLabel("Corrections will appear here\nas you speak\u2026")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.3);
                font-size: 12px;
                padding: 24px;
                background: transparent;
                border: none;
            }
        """)
        self._cards_layout.insertWidget(0, self._empty_label)

        # Position on right side of screen
        self._update_geometry()

        # Connect signals
        ui_signals.show_correction.connect(self.add_correction)
        ui_signals.clear_corrections.connect(self.clear_corrections)
        ui_signals.toggle_correction_panel.connect(self._toggle_visibility)

        # Auto-hide timer
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

    def _update_geometry(self):
        """Position the panel on the right side of the screen."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        screen_size = screen.size()
        panel_w = min(360, int(screen_size.width() * 0.22))
        panel_h = int(screen_size.height() * 0.5)
        x = screen_size.width() - panel_w - 20
        y = (screen_size.height() - panel_h) // 2
        self.setGeometry(x, y, panel_w, panel_h)

    def add_correction(self, correction: dict):
        """Add a correction card to the panel."""
        # Hide empty state
        self._empty_label.setVisible(False)

        # Build card
        card = _build_card_widget(correction)
        self._card_widgets.append(card)

        # Insert before the stretch at the end
        stretch_index = self._cards_layout.count() - 1
        self._cards_layout.insertWidget(stretch_index, card)

        # Remove oldest if too many
        while len(self._card_widgets) > self.MAX_CARDS:
            oldest = self._card_widgets.pop(0)
            self._cards_layout.removeWidget(oldest)
            oldest.deleteLater()

        # Update count
        self._count_label.setText(str(len(self._card_widgets)))

        # Auto-scroll to newest
        QTimer.singleShot(50, self._scroll_to_bottom)

        # Show panel if hidden
        if not self.isVisible():
            self.show()
            self.raise_()

        # Reset auto-hide timer
        self._last_correction_time = time.time()
        self._auto_hide_timer.stop()

    def clear_corrections(self):
        """Remove all correction cards."""
        for card in self._card_widgets:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._card_widgets.clear()
        self._count_label.setText("0")
        self._empty_label.setVisible(True)

    def schedule_auto_hide(self):
        """Start the auto-hide timer (called when recording stops)."""
        self._auto_hide_timer.start(self.AUTO_HIDE_DELAY_MS)

    def _scroll_to_bottom(self):
        """Scroll to the newest card."""
        vbar = self._scroll_area.verticalScrollBar()
        if vbar:
            vbar.setValue(vbar.maximum())

    def _toggle_visibility(self):
        """Toggle panel visibility."""
        if self.isVisible():
            self.hide()
        else:
            self._update_geometry()
            self.show()
            self.raise_()
