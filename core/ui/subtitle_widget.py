"""SubtitleLabel and SubtitleWidget — real-time transcription subtitle overlay."""
import logging
import threading
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
)

from core.ui.mixins import DraggableWidgetMixin
from core.ui.signals import _app_callbacks


class SubtitleLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.creation_time = 0

    # noinspection PyPep8Naming
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            text = self.text()
            if "text_submit" in _app_callbacks:
                try:
                    threading.Thread(
                        target=_app_callbacks["text_submit"],
                        args=(text,),
                        daemon=True,
                    ).start()
                except Exception as e:
                    print(f"Error submitting subtitle text: {e}")


class SubtitleWidget(DraggableWidgetMixin, QWidget):
    """Widget for displaying real-time transcription subtitles with fading effects."""

    def __init__(self):
        super().__init__()
        self._init_draggable()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        # Remove WA_TranslucentBackground to ensure proper rendering
        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Use a more visible background for debugging
        self.setStyleSheet(
            "background-color: transparent; border: 1px solid rgba(255, 0, 0, 0.3);"
        )

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)

        # Store subtitle labels with their creation time
        self.subtitle_labels = []
        self.max_subtitles = 5  # Maximum number of subtitle lines to show
        self.fade_duration = (
            15000  # Duration for fade effect in milliseconds (15 seconds)
        )

        # Timer for updating fade effects
        self.fade_timer = QTimer(self)
        self.fade_timer.timeout.connect(self.update_fade_effects)
        self.fade_timer.start(100)  # Update every 100ms

        # Position settings
        self.target_position = None
        self.update_position()

    def update_position(self):
        """Position widget at bottom center of screen."""
        screen = QApplication.primaryScreen().size()
        w = int(screen.width() * 0.6)
        self.setFixedWidth(w)
        self.adjustSize()
        h = self.height()
        x = (screen.width() - w) // 2
        y = screen.height() - h - 50
        self.setGeometry(x, y, w, h)

        # Debug logging
        logger = logging.getLogger(__name__)
        logger.info(f"Subtitle widget position updated: ({x}, {y}), size: ({w}, {h})")

    def get_subtitle_text(self, index: int) -> str:
        """Get the text of a subtitle by index (1 is newest)."""
        if index <= 0 or index > len(self.subtitle_labels):
            return ""
        return self.subtitle_labels[-index].text()

    def add_subtitle(self, text: str):
        """Add a new subtitle line."""
        logger = logging.getLogger(__name__)
        logger.info(f"Adding subtitle: {text}")
        logger.info(f"Subtitle widget visible: {self.isVisible()}")
        logger.info(f"Subtitle widget position: {self.pos()}, size: {self.size()}")

        # Update the creation time of existing subtitles so they fade out relative to the newest one
        current_time = time.time()
        for i, existing_label in enumerate(reversed(self.subtitle_labels)):
            # Give older subtitles an artificial age bump so they look older
            existing_label.creation_time = current_time - (i + 1) * 2.0

        # Create new subtitle label
        label = SubtitleLabel(text)
        label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: rgba(255, 255, 255, 1.0);
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)

        # Store with creation time
        label.creation_time = time.time()
        self.subtitle_labels.append(label)

        # Add to layout
        self.layout.addWidget(label)

        # Remove oldest if we have too many
        if len(self.subtitle_labels) > self.max_subtitles:
            oldest = self.subtitle_labels.pop(0)
            self.layout.removeWidget(oldest)
            oldest.deleteLater()

        # Force layout update before adjusting size
        self.layout.activate()

        # Update widget size
        self.adjustSize()
        self.update_position()

        # Ensure widget has minimum height
        if self.height() == 0:
            self.setMinimumHeight(50)
            self.adjustSize()

        # Show if hidden
        if not self.isVisible():
            logger.info("Subtitle widget was hidden, attempting to show it")
            self.show()
            self.raise_()  # Bring to front
            self.activateWindow()  # Force window activation
            self.repaint()  # Force repaint
            logger.info(
                f"After show(), widget visible: {self.isVisible()}, size: {self.size()}"
            )

    def update_last_subtitle(self, text: str, append: bool = False):
        """Update the text of the most recent subtitle instead of creating a new one."""
        logger = logging.getLogger(__name__)
        logger.info(f"update_last_subtitle called with text: {text}, append: {append}")

        if not self.subtitle_labels:
            # No existing subtitles, create a new one
            logger.info("No existing subtitles, creating new one")
            self.add_subtitle(text)
            return

        # Update the last subtitle's text
        last_label = self.subtitle_labels[-1]

        # Reset the creation time of the active subtitle so it doesn't fade while being updated
        last_label.creation_time = time.time()

        if append:
            # Append to existing text
            current_text = last_label.text()
            new_text = current_text + " " + text
            last_label.setText(new_text)
            logger.info(f"Appended to last subtitle: {new_text}")
        else:
            # Replace existing text
            last_label.setText(text)
            logger.info(f"Updated last subtitle to: {text}")

        # Force layout update and size adjustment
        self.layout.activate()
        self.adjustSize()
        self.update_position()

        # Ensure widget is visible
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            self.repaint()

    def clear_subtitles(self):
        """Clear all subtitles."""
        for label in self.subtitle_labels:
            self.layout.removeWidget(label)
            label.deleteLater()
        self.subtitle_labels.clear()
        self.hide()

    def update_fade_effects(self):
        """Update opacity of subtitle labels based on their age."""
        current_time = time.time()

        for i, label in enumerate(self.subtitle_labels):
            # Calculate age in seconds
            age = current_time - label.creation_time

            # Calculate opacity based on position and age
            # Newer subtitles (higher index) are more opaque
            # Older subtitles fade out more gradually
            position_factor = (
                (i + 1) / len(self.subtitle_labels) if self.subtitle_labels else 1
            )

            # More gradual fading - start fading after 5 seconds, complete fade by fade_duration
            fade_start = 5.0  # Start fading after 5 seconds
            if age < fade_start:
                age_factor = 1.0  # Full opacity for first 5 seconds
            else:
                age_factor = max(
                    0.3,
                    1.0
                    - ((age - fade_start) / ((self.fade_duration / 1000) - fade_start)),
                )

            # Combine factors, but ensure minimum visibility
            opacity = min(0.95, max(0.4, position_factor * age_factor))

            # The newest subtitle should always be fully visible if it's less than fade_start old
            if i == len(self.subtitle_labels) - 1 and age < fade_start:
                opacity = 0.95

            # Update label style with new opacity
            label.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(0, 0, 0, {opacity * 0.7:.3f});
                    color: rgba(255, 255, 255, {opacity:.3f});
                    padding: 8px 12px;
                    border-radius: 4px;
                    font-size: 16px;
                    font-weight: bold;
                }}
            """)

        # Remove very old subtitles
        if self.subtitle_labels:
            oldest_age = current_time - self.subtitle_labels[0].creation_time
            if (
                oldest_age > (self.fade_duration / 1000) * 2
            ):  # Remove after 2x fade duration
                oldest = self.subtitle_labels.pop(0)
                self.layout.removeWidget(oldest)
                oldest.deleteLater()
                self.adjustSize()
                self.update_position()
