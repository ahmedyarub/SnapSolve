"""Session timeline widget — screenpipe-inspired visual timeline.

Shows periodic screenshots as a filmstrip, event markers for different
interaction types, a draggable playhead, and contextual transcription display.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QEvent, Qt, QRect, QRectF, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_ICON_SIZE = 20  # px — icon drawn inside app track spans
_SNAPSOLVE_APP_NAME = "SnapSolve"


# ── Colour palette ──────────────────────────────────────────────────────
_BG_DARK = "#1a1d23"
_BG_PANEL = "#21252b"
_BG_SURFACE = "#282c34"
_BORDER = "#333840"
_TEXT_DIM = "#636d83"
_TEXT_MID = "#8b95a7"
_TEXT_BRIGHT = "#abb2bf"
_ACCENT_BLUE = "#61afef"
_ACCENT_GREEN = "#98c379"
_ACCENT_ORANGE = "#d19a66"
_ACCENT_PURPLE = "#c678dd"
_ACCENT_CYAN = "#56b6c2"
_ACCENT_RED = "#e06c75"
_PLAYHEAD_RED = "#e06c75"

# Event marker colours keyed by interaction source
_EVENT_COLORS = {
    "audio": _ACCENT_ORANGE,
    "image": _ACCENT_BLUE,
    "image_multi": _ACCENT_PURPLE,
    "text": _ACCENT_CYAN,
    "transcription_separator": _ACCENT_GREEN,
}

# Event marker icons keyed by interaction source
_EVENT_ICONS = {
    "audio": "🎤",
    "image": "🖼️",
    "image_multi": "📑",
    "text": "💬",
    "transcription_separator": "📜",
}

# ── Constants ────────────────────────────────────────────────────────────
_THUMB_WIDTH = 160
_THUMB_HEIGHT = 100
_THUMB_GAP = 6
_THUMB_RADIUS = 6
_MARKER_TRACK_HEIGHT = 36
_APP_TRACK_HEIGHT = 28
_RULER_HEIGHT = 28
_MIN_FILMSTRIP_WIDTH = 200
_PLAYHEAD_WIDTH = 2
_THUMBNAIL_CACHE_SIZE = 200
_HEADER_HEIGHT = 32
_TRANSCRIPTION_HEIGHT = 120
_ZOOM_MIN = 0.25
_ZOOM_MAX = 4.0
_ZOOM_STEP = 0.15

# Colour palette for app name spans — index 0 (red) is reserved for SnapSolve
_APP_COLORS = [
    "#e06c75", "#61afef", "#98c379", "#d19a66", "#c678dd",
    "#56b6c2", "#e5c07b", "#be5046", "#7ec8e3", "#c3e88d",
    "#ff75a0", "#8da0cb", "#a1d99b", "#fdae6b", "#bcbddc",
]
_SNAPSOLVE_COLOR = _APP_COLORS[0]  # red — always reserved for SnapSolve
_OTHER_APP_COLORS = _APP_COLORS[1:]  # palette for all other apps


class _ThumbnailCache:
    """Simple LRU-ish cache for scaled QPixmaps."""

    def __init__(self, max_size: int = _THUMBNAIL_CACHE_SIZE) -> None:
        self._cache: dict[str, QPixmap] = {}
        self._order: list[str] = []
        self._max_size = max_size

    def get(self, path: str) -> Optional[QPixmap]:
        if path in self._cache:
            # Move to end (most-recently-used)
            self._order.remove(path)
            self._order.append(path)
            return self._cache[path]
        return None

    def put(self, path: str, pixmap: QPixmap) -> None:
        if path in self._cache:
            self._order.remove(path)
        elif len(self._cache) >= self._max_size:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[path] = pixmap
        self._order.append(path)

    def clear(self) -> None:
        self._cache.clear()
        self._order.clear()


# ═════════════════════════════════════════════════════════════════════════
# Filmstrip Widget
# ═════════════════════════════════════════════════════════════════════════


class _FilmstripWidget(QWidget):
    """Horizontally scrollable strip of screenshot thumbnails."""

    thumbnailClicked = pyqtSignal(int)  # index into screenshot events

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._screenshots: list[dict] = []  # list of event dicts (type="screenshot")
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._cache = _ThumbnailCache()
        self._hovered_index: int = -1
        self._selected_index: int = -1
        self.setMouseTracking(True)
        self.setMinimumHeight(_THUMB_HEIGHT + 28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_screenshots(
        self,
        screenshots: list[dict],
        time_start: float,
        time_end: float,
        total_width: int,
    ) -> None:
        self._screenshots = screenshots
        self._time_start = time_start
        self._time_end = time_end
        self._selected_index = -1
        self._hovered_index = -1
        self._cache.clear()
        self.setFixedWidth(total_width)
        self.update()

    def set_selected_index(self, index: int) -> None:
        self._selected_index = index
        self.update()

    def _time_to_x(self, ts: float) -> int:
        if self._time_end <= getattr(self, "_time_start", 0):
            return _THUMB_GAP
        frac = (ts - self._time_start) / (self._time_end - self._time_start)
        return int(_THUMB_GAP + frac * (self.width() - 2 * _THUMB_GAP))

    def _thumb_rect(self, index: int) -> QRect:
        ss = self._screenshots[index]
        center_x = self._time_to_x(ss["timestamp"])
        x = int(center_x - _THUMB_WIDTH / 2)
        return QRect(x, 4, _THUMB_WIDTH, _THUMB_HEIGHT)

    def _load_thumbnail(self, path: str) -> QPixmap:
        cached = self._cache.get(path)
        if cached is not None:
            return cached
        pix = QPixmap(path)
        if pix.isNull():
            # Placeholder
            pix = QPixmap(_THUMB_WIDTH, _THUMB_HEIGHT)
            pix.fill(QColor(_BG_DARK))
        else:
            pix = pix.scaled(
                _THUMB_WIDTH, _THUMB_HEIGHT,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Centre-crop to exact thumbnail size
            if pix.width() > _THUMB_WIDTH or pix.height() > _THUMB_HEIGHT:
                x_off = (pix.width() - _THUMB_WIDTH) // 2
                y_off = (pix.height() - _THUMB_HEIGHT) // 2
                pix = pix.copy(x_off, y_off, _THUMB_WIDTH, _THUMB_HEIGHT)
        self._cache.put(path, pix)
        return pix

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(_BG_DARK))

        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i, ss in enumerate(self._screenshots):
            rect = self._thumb_rect(i)

            # Check if in visible area
            if rect.right() < event.rect().left() - 10:
                continue
            if rect.left() > event.rect().right() + 10:
                break

            path = ss["data"]["path"]
            pix = self._load_thumbnail(path)

            is_selected = i == self._selected_index
            is_hovered = i == self._hovered_index

            # Glow effect for selected/hovered
            if is_selected or is_hovered:
                glow_color = QColor(_ACCENT_BLUE if is_selected else _TEXT_MID)
                glow_color.setAlpha(60 if is_selected else 35)
                glow_rect = rect.adjusted(-3, -3, 3, 3)
                glow_path = QPainterPath()
                glow_path.addRoundedRect(QRectF(glow_rect), _THUMB_RADIUS + 2, _THUMB_RADIUS + 2)
                painter.fillPath(glow_path, glow_color)

            # Thumbnail with rounded corners
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(rect), _THUMB_RADIUS, _THUMB_RADIUS)
            painter.save()
            painter.setClipPath(clip_path)
            painter.drawPixmap(rect, pix)

            # Dark gradient overlay at bottom for timestamp legibility
            gradient = QLinearGradient(rect.left(), rect.bottom() - 24, rect.left(), rect.bottom())
            gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
            gradient.setColorAt(1.0, QColor(0, 0, 0, 160))
            painter.fillRect(QRect(rect.left(), rect.bottom() - 24, rect.width(), 24), gradient)
            painter.restore()

            # Border
            border_color = QColor(_ACCENT_BLUE) if is_selected else QColor(_BORDER)
            if is_hovered and not is_selected:
                border_color = QColor(_TEXT_MID)
            pen = QPen(border_color, 2 if is_selected else 1)
            painter.setPen(pen)
            painter.drawRoundedRect(QRectF(rect), _THUMB_RADIUS, _THUMB_RADIUS)

            # Timestamp label (inside thumbnail, bottom)
            ts = ss["timestamp"]
            time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            painter.setPen(QColor(255, 255, 255, 200))
            label_rect = QRect(rect.left() + 4, rect.bottom() - 18, rect.width() - 8, 16)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, time_str)

        painter.end()

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event) -> None:
        old = self._hovered_index
        self._hovered_index = self._hit_test(event.pos())
        if old != self._hovered_index:
            self.update()

        # Tooltip
        if self._hovered_index >= 0:
            ss = self._screenshots[self._hovered_index]
            ts = datetime.fromtimestamp(ss["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            app = ss.get("data", {}).get("app_name", "")
            tip = f"Screenshot at {ts}"
            if app:
                tip += f" \u2014 {app}"
            QToolTip.showText(event.globalPosition().toPoint(), tip)
        else:
            QToolTip.hideText()

    # noinspection PyPep8Naming
    def mousePressEvent(self, event) -> None:
        idx = self._hit_test(event.pos())
        if idx >= 0:
            self._selected_index = idx
            self.thumbnailClicked.emit(idx)
            self.update()

    # noinspection PyPep8Naming
    def leaveEvent(self, event) -> None:
        self._hovered_index = -1
        self.update()

    def _hit_test(self, pos) -> int:
        for i in range(len(self._screenshots) - 1, -1, -1):
            if self._thumb_rect(i).contains(pos):
                return i
        return -1

    # noinspection PyPep8Naming
    def sizeHint(self) -> QSize:
        return QSize(self.width(), _THUMB_HEIGHT + 28)


# ═════════════════════════════════════════════════════════════════════════
# App Track Widget
# ═════════════════════════════════════════════════════════════════════════


class _AppIconCache:
    """On-disk + in-memory cache for application icons.

    Icons are extracted from the executable path using ``QFileIconProvider``
    and saved as 32×32 PNGs in ``config/icon_cache/<process_name>.png``.
    Subsequent loads read from disk and keep a ``QPixmap`` in memory.
    """

    _CACHE_DIR = os.path.join("config", "icon_cache")
    _DISK_SIZE = 32  # saved PNG resolution
    _SNAPSOLVE_ICON = os.path.join("assets", "icon.png")

    def __init__(self) -> None:
        self._memory: dict[str, QPixmap] = {}  # process_name -> QPixmap
        self._provider = QFileIconProvider()
        os.makedirs(self._CACHE_DIR, exist_ok=True)

    def get_icon(self, process_name: str, exe_path: str, size: int = _ICON_SIZE) -> Optional[QPixmap]:
        """Return a *size×size* ``QPixmap`` for *process_name*, or ``None``."""
        if not process_name:
            return None

        key = process_name.lower()

        # 1. In-memory cache hit
        if key in self._memory:
            return self._memory[key]

        # 2. SnapSolve uses the bundled app icon, not the Python exe icon
        if key == "snapsolve" and os.path.isfile(self._SNAPSOLVE_ICON):
            pm = QPixmap(self._SNAPSOLVE_ICON)
            if not pm.isNull():
                scaled = pm.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._memory[key] = scaled
                return scaled

        # 3. On-disk cache hit
        disk_path = os.path.join(self._CACHE_DIR, f"{key}.png")
        if os.path.isfile(disk_path):
            pm = QPixmap(disk_path)
            if not pm.isNull():
                scaled = pm.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._memory[key] = scaled
                return scaled

        # 4. Extract from exe path
        if exe_path and os.path.isfile(exe_path):
            try:
                from PyQt6.QtCore import QFileInfo  # noqa: PLC0415

                file_info = QFileInfo(exe_path)
                icon = self._provider.icon(file_info)
                if not icon.isNull():
                    pm = icon.pixmap(self._DISK_SIZE, self._DISK_SIZE)
                    if not pm.isNull():
                        # Save to disk cache
                        pm.save(disk_path, "PNG")
                        scaled = pm.scaled(
                            size, size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        self._memory[key] = scaled
                        logger.debug("Cached icon for %s -> %s", process_name, disk_path)
                        return scaled
            except Exception as exc:
                logger.debug("Failed to extract icon for %s: %s", process_name, exc)

        return None


class _AppSpan:
    """A contiguous time span where the same application was focused."""

    def __init__(self, app_name: str, start_ts: float, end_ts: float,
                 window_title: str, exe_path: str) -> None:
        self.app_name = app_name
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.window_title = window_title  # from the last screenshot in the span
        self.exe_path = exe_path


class _AppTrackWidget(QWidget):
    """Horizontal track showing coloured spans for each active application."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._spans: list[_AppSpan] = []
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._total_width: int = _MIN_FILMSTRIP_WIDTH
        self._hovered_index: int = -1
        self._icon_cache = _AppIconCache()
        self._icons: dict[str, Optional[QPixmap]] = {}  # app_name -> resolved pixmap
        self._app_colors: dict[str, str] = {}  # app_name -> hex colour
        self.setMouseTracking(True)
        self.setFixedHeight(_APP_TRACK_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(
        self,
        screenshots: list[dict],
        time_start: float,
        time_end: float,
        total_width: int,
    ) -> None:
        """Build app spans from screenshot events and update layout."""
        self._time_start = time_start
        self._time_end = time_end
        self._total_width = max(_MIN_FILMSTRIP_WIDTH, total_width)
        self.setFixedWidth(self._total_width)
        self._hovered_index = -1
        self._spans = self._build_spans(screenshots)

        # Fill gaps — extend each span to meet the next, making the track
        # continuous with no breaks between apps.
        for i in range(len(self._spans) - 1):
            self._spans[i].end_ts = self._spans[i + 1].start_ts
        if self._spans:
            self._spans[-1].end_ts = self._time_end

        # Assign sequential colours — red is reserved for SnapSolve
        self._app_colors.clear()
        colour_idx = 0
        for span in self._spans:
            if span.app_name not in self._app_colors:
                if span.app_name == _SNAPSOLVE_APP_NAME:
                    self._app_colors[span.app_name] = _SNAPSOLVE_COLOR
                else:
                    self._app_colors[span.app_name] = _OTHER_APP_COLORS[
                        colour_idx % len(_OTHER_APP_COLORS)
                    ]
                    colour_idx += 1

        # Pre-resolve icons for each unique app
        self._icons.clear()
        for span in self._spans:
            if span.app_name not in self._icons:
                self._icons[span.app_name] = self._icon_cache.get_icon(
                    span.app_name, span.exe_path
                )

        self.update()

    @staticmethod
    def _build_spans(screenshots: list[dict]) -> list[_AppSpan]:
        """Merge adjacent screenshots with the same app_name into spans."""
        spans: list[_AppSpan] = []
        for ss in screenshots:
            data = ss.get("data", {})
            app = data.get("app_name", "")
            if not app:
                continue
            ts = ss["timestamp"]
            title = data.get("window_title", "")
            exe_path = data.get("exe_path", "")
            if spans and spans[-1].app_name == app:
                # Extend the current span
                spans[-1].end_ts = ts
                spans[-1].window_title = title
            else:
                spans.append(_AppSpan(app, ts, ts, title, exe_path))
        return spans

    def _time_to_x(self, ts: float) -> int:
        if self._time_end <= self._time_start:
            return _THUMB_GAP
        frac = (ts - self._time_start) / (self._time_end - self._time_start)
        return int(_THUMB_GAP + frac * (self._total_width - 2 * _THUMB_GAP))

    def _span_rect(self, index: int) -> QRect:
        span = self._spans[index]
        x1 = self._time_to_x(span.start_ts)
        x2 = self._time_to_x(span.end_ts)
        w = max(x2 - x1, 2)  # ensure at least 2px so the span is visible
        return QRect(x1, 2, w, _APP_TRACK_HEIGHT - 4)

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(_BG_DARK))

        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        fm = QFontMetrics(font)

        for i, span in enumerate(self._spans):
            rect = self._span_rect(i)

            # Skip off-screen spans
            if rect.right() < event.rect().left() - 10:
                continue
            if rect.left() > event.rect().right() + 10:
                break

            is_hovered = i == self._hovered_index
            color = QColor(self._app_colors.get(span.app_name, _APP_COLORS[0]))

            # Span background
            bg_color = QColor(color)
            bg_color.setAlpha(100 if is_hovered else 60)
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 4, 4)
            painter.fillPath(path, bg_color)

            # Border
            border_color = QColor(color)
            border_color.setAlpha(200 if is_hovered else 120)
            painter.setPen(QPen(border_color, 1.5 if is_hovered else 1))
            painter.drawRoundedRect(QRectF(rect), 4, 4)

            # App icon (if available)
            icon = self._icons.get(span.app_name)
            text_x_offset = 4
            if icon and not icon.isNull():
                icon_y = rect.top() + (rect.height() - _ICON_SIZE) // 2
                icon_x = rect.left() + 3
                painter.drawPixmap(icon_x, icon_y, icon)
                text_x_offset = 3 + _ICON_SIZE + 3  # icon padding + icon + gap

            # App name text (clipped to span width)
            text_color = QColor(color)
            text_color.setAlpha(255 if is_hovered else 200)
            painter.setPen(text_color)
            text_rect = rect.adjusted(text_x_offset, 0, -4, 0)
            if text_rect.width() > 8:  # only draw text if there's room
                elided = fm.elidedText(span.app_name, Qt.TextElideMode.ElideRight, text_rect.width())
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.end()

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event) -> None:
        old = self._hovered_index
        self._hovered_index = self._hit_test(event.pos())
        if old != self._hovered_index:
            self.update()

        if self._hovered_index >= 0:
            span = self._spans[self._hovered_index]
            t1 = datetime.fromtimestamp(span.start_ts).strftime("%H:%M:%S")
            t2 = datetime.fromtimestamp(span.end_ts).strftime("%H:%M:%S")
            title = span.window_title
            # Wrap long window titles
            if len(title) > 80:
                title = title[:77] + "..."
            tip = f"\U0001f4bb {span.app_name}  [{t1} \u2013 {t2}]"
            if title:
                tip += f"\n{title}"
            QToolTip.showText(event.globalPosition().toPoint(), tip)
        else:
            QToolTip.hideText()

    # noinspection PyPep8Naming
    def leaveEvent(self, event) -> None:
        self._hovered_index = -1
        self.update()

    def _hit_test(self, pos) -> int:
        for i in range(len(self._spans)):
            if self._span_rect(i).contains(pos):
                return i
        return -1


# ═════════════════════════════════════════════════════════════════════════
# Event Track Widget
# ═════════════════════════════════════════════════════════════════════════


class _EventTrackWidget(QWidget):
    """Horizontal track with coloured markers for each session event."""

    eventClicked = pyqtSignal(dict)  # the event dict

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._events: list[dict] = []  # non-screenshot events
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._total_width: int = _MIN_FILMSTRIP_WIDTH
        self._hovered_index: int = -1
        self.setMouseTracking(True)
        self.setFixedHeight(_MARKER_TRACK_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_events(self, events: list[dict], time_start: float, time_end: float, total_width: int) -> None:
        self._events = events
        self._time_start = time_start
        self._time_end = time_end
        self._total_width = max(_MIN_FILMSTRIP_WIDTH, total_width)
        self.setFixedWidth(self._total_width)
        self._hovered_index = -1
        self.update()

    def _time_to_x(self, ts: float) -> int:
        if self._time_end <= self._time_start:
            return _THUMB_GAP
        frac = (ts - self._time_start) / (self._time_end - self._time_start)
        return int(_THUMB_GAP + frac * (self._total_width - 2 * _THUMB_GAP))

    def _marker_rect(self, index: int) -> QRect:
        ev = self._events[index]
        x = self._time_to_x(ev["timestamp"])
        return QRect(x - 12, 2, 24, _MARKER_TRACK_HEIGHT - 4)

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(_BG_PANEL))

        # Horizontal centre line
        y_mid = self.height() // 2
        pen = QPen(QColor(_BORDER), 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawLine(0, y_mid, self.width(), y_mid)

        font = QFont("Segoe UI Emoji", 11)
        painter.setFont(font)

        for i, ev in enumerate(self._events):
            x = self._time_to_x(ev["timestamp"])

            # Determine colour and icon
            source = ev.get("data", {}).get("source", "text")
            ev_type = ev["type"]
            if ev_type == "transcription_separator":
                color_key = "transcription_separator"
            else:
                color_key = source

            color = QColor(_EVENT_COLORS.get(color_key, _ACCENT_BLUE))
            icon = _EVENT_ICONS.get(color_key, "●")

            is_hovered = i == self._hovered_index

            # Marker dot
            dot_radius = 6 if is_hovered else 4
            color_with_alpha = QColor(color)
            if is_hovered:
                color_with_alpha.setAlpha(255)
            else:
                color_with_alpha.setAlpha(200)

            # Glow for hovered
            if is_hovered:
                glow = QColor(color)
                glow.setAlpha(60)
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x - 10, y_mid - 10, 20, 20)

            # Vertical tick line
            tick_pen = QPen(color_with_alpha, 1)
            painter.setPen(tick_pen)
            painter.drawLine(x, 2, x, self.height() - 2)

            # Marker circle
            painter.setBrush(QBrush(color_with_alpha))
            painter.setPen(QPen(QColor(_BG_DARK), 1.5))
            painter.drawEllipse(x - dot_radius, y_mid - dot_radius, dot_radius * 2, dot_radius * 2)

            # Icon above marker
            icon_rect = QRect(x - 10, 1, 20, 16)
            painter.setPen(QColor(255, 255, 255, 220 if is_hovered else 160))
            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, icon)

        painter.end()

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event) -> None:
        old = self._hovered_index
        self._hovered_index = self._hit_test(event.pos())
        if old != self._hovered_index:
            self.update()

        if self._hovered_index >= 0:
            ev = self._events[self._hovered_index]
            ts = datetime.fromtimestamp(ev["timestamp"]).strftime("%H:%M:%S")
            ev_type = ev["type"]
            if ev_type == "interaction":
                src = ev["data"].get("source", "text")
                icon = _EVENT_ICONS.get(src, "●")
                excerpt = ev["data"].get("prompt_excerpt", "")
                # Wrap long excerpts for readability
                if len(excerpt) > 60:
                    mid = excerpt.rfind(" ", 0, 60)
                    if mid > 20:
                        excerpt = excerpt[:mid] + "\n" + excerpt[mid + 1:]
                tip = f"{icon}  {src.capitalize()} prompt  [{ts}]\n\n{excerpt}" if excerpt else f"{icon}  {src.capitalize()} [{ts}]"
            elif ev_type == "transcription_separator":
                line = ev["data"].get("line", "")
                tip = f"📜  Transcription  [{ts}]\n{line}"
            else:
                tip = f"[{ts}] {ev_type}"
            QToolTip.showText(event.globalPosition().toPoint(), tip)
        else:
            QToolTip.hideText()

    # noinspection PyPep8Naming
    def mousePressEvent(self, event) -> None:
        idx = self._hit_test(event.pos())
        if idx >= 0:
            self.eventClicked.emit(self._events[idx])

    # noinspection PyPep8Naming
    def leaveEvent(self, event) -> None:
        self._hovered_index = -1
        self.update()

    def _hit_test(self, pos) -> int:
        for i in range(len(self._events)):
            if self._marker_rect(i).contains(pos):
                return i
        return -1


# ═════════════════════════════════════════════════════════════════════════
# Time Ruler Widget
# ═════════════════════════════════════════════════════════════════════════


class _TimeRulerWidget(QWidget):
    """Horizontal time axis with tick marks, labels, and click-to-seek.

    This widget also handles playhead positioning: clicking anywhere on
    the ruler moves the playhead to that time, and dragging slides it.
    """

    playheadMoved = pyqtSignal(float)  # timestamp

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._total_width: int = _MIN_FILMSTRIP_WIDTH
        self._dragging: bool = False
        self.setFixedHeight(_RULER_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_time_range(self, time_start: float, time_end: float, total_width: int) -> None:
        self._time_start = time_start
        self._time_end = time_end
        self._total_width = max(_MIN_FILMSTRIP_WIDTH, total_width)
        self.setFixedWidth(self._total_width)
        self.update()

    def _time_to_x(self, ts: float) -> int:
        if self._time_end <= self._time_start:
            return _THUMB_GAP
        frac = (ts - self._time_start) / (self._time_end - self._time_start)
        return int(_THUMB_GAP + frac * (self._total_width - 2 * _THUMB_GAP))

    def _x_to_time(self, x: int) -> float:
        if self._total_width <= 2 * _THUMB_GAP:
            return self._time_start
        frac = (x - _THUMB_GAP) / (self._total_width - 2 * _THUMB_GAP)
        frac = max(0.0, min(1.0, frac))
        return self._time_start + frac * (self._time_end - self._time_start)

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(_BG_PANEL))

        if self._time_end <= self._time_start:
            painter.end()
            return

        duration = self._time_end - self._time_start

        # Choose tick interval based on duration
        if duration < 120:
            tick_interval = 10  # 10 seconds
        elif duration < 600:
            tick_interval = 30  # 30 seconds
        elif duration < 3600:
            tick_interval = 60  # 1 minute
        elif duration < 7200:
            tick_interval = 300  # 5 minutes
        else:
            tick_interval = 600  # 10 minutes

        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Top border
        painter.setPen(QPen(QColor(_BORDER), 1))
        painter.drawLine(0, 0, self.width(), 0)

        # Tick marks
        first_tick = int(self._time_start // tick_interval + 1) * tick_interval
        ts = first_tick
        while ts <= self._time_end:
            x = self._time_to_x(ts)

            # Major tick
            painter.setPen(QPen(QColor(_TEXT_DIM), 1))
            painter.drawLine(x, 0, x, 8)

            # Label
            time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
            if tick_interval >= 60:
                time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
            tw = fm.horizontalAdvance(time_str)
            painter.setPen(QColor(_TEXT_DIM))
            painter.drawText(x - tw // 2, 22, time_str)

            ts += tick_interval

        # Seek hint
        painter.setPen(QColor(_TEXT_DIM))
        hint_font = QFont("Segoe UI", 7)
        hint_font.setItalic(True)
        painter.setFont(hint_font)
        painter.drawText(4, 22, "click to seek")

        painter.end()

    # noinspection PyPep8Naming
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            ts = self._x_to_time(int(event.position().x()))
            self.playheadMoved.emit(ts)

    # noinspection PyPep8Naming
    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            ts = self._x_to_time(int(event.position().x()))
            self.playheadMoved.emit(ts)

    # noinspection PyPep8Naming
    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False


# ═════════════════════════════════════════════════════════════════════════
# Transcription Context Panel
# ═════════════════════════════════════════════════════════════════════════


class _TranscriptionPanel(QFrame):
    """Shows transcription segments near the current playhead position.

    Each line is clickable — clicking emits ``lineClicked`` with the
    approximate timestamp so the parent can navigate the timeline.
    """

    lineClicked = pyqtSignal(float)  # timestamp of the clicked line

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._transcription_lines: list[tuple[float, str]] = []  # (timestamp, text)
        self._current_time: float = 0.0
        self._collapsed: bool = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG_SURFACE};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        header = QWidget()
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl = QLabel("📜 Transcription Context  (click a line to jump)")
        lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                font-weight: bold;
                color: {_ACCENT_GREEN};
                background: transparent;
                border: none;
                padding: 2px 0;
            }}
        """)
        h_layout.addWidget(lbl)
        h_layout.addStretch()
        
        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setToolTip("Collapse / Expand")
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {_TEXT_MID};
                border: none;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {_ACCENT_GREEN};
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        h_layout.addWidget(self._toggle_btn)
        
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {_BG_DARK};
                color: {_TEXT_BRIGHT};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-family: 'Consolas', 'Fira Code', monospace;
                font-size: 11px;
                padding: 2px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 2px 4px;
                border-radius: 3px;
            }}
            QListWidget::item:hover {{
                background-color: #2c313a;
                color: {_ACCENT_GREEN};
            }}
            QListWidget::item:selected {{
                background-color: #2c313a;
                color: {_ACCENT_GREEN};
            }}
        """)
        self._list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._list.hide()
            self.setMaximumHeight(30)
            self._toggle_btn.setText("▶")
        else:
            self._list.show()
            self.setMaximumHeight(16777215)
            self._toggle_btn.setText("▼")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Emit the timestamp of the clicked transcription line."""
        ts = item.data(Qt.ItemDataRole.UserRole)
        if ts is not None:
            self.lineClicked.emit(ts)

    def set_transcription_lines_with_timestamps(
        self, lines: list[tuple[float, str]]
    ) -> None:
        """Directly set timestamped transcription lines."""
        self._transcription_lines = lines
        self._list.clear()

        if not lines:
            self._list.addItem("No transcription data available.")
        else:
            for ts, text in lines:
                time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                item = QListWidgetItem(f"[{time_str}]  {text}")
                item.setToolTip(f"Click to jump to {time_str}")
                item.setData(Qt.ItemDataRole.UserRole, ts)
                self._list.addItem(item)

    def navigate_to_time(self, timestamp: float) -> None:
        """Highlight and scroll to the closest previous transcription segment."""
        self._current_time = timestamp
        if not self._transcription_lines:
            return

        # Find closest previous sentence
        best_idx = 0
        for i, (ts, text) in enumerate(self._transcription_lines):
            if ts <= timestamp:
                best_idx = i
            else:
                break
        
        item = self._list.item(best_idx)
        if item:
            self._list.setCurrentItem(item)
            self._list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)


# ═════════════════════════════════════════════════════════════════════════
# Playhead Overlay Widget
# ═════════════════════════════════════════════════════════════════════════


class _PlayheadOverlay(QWidget):
    """Purely visual overlay that draws a vertical playhead line.

    Mouse events pass through to the underlying widgets (filmstrip,
    event track). The ruler handles click-to-seek / drag.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._playhead_time: float = 0.0
        # Purely visual — let mouse events fall through
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_time_range(self, time_start: float, time_end: float) -> None:
        self._time_start = time_start
        self._time_end = time_end
        self.update()

    def set_playhead_time(self, ts: float) -> None:
        self._playhead_time = ts
        self.update()

    def _time_to_x(self, ts: float) -> int:
        if self._time_end <= self._time_start:
            return 0
        frac = (ts - self._time_start) / (self._time_end - self._time_start)
        return int(_THUMB_GAP + frac * (self.width() - 2 * _THUMB_GAP))

    # noinspection PyPep8Naming
    def paintEvent(self, event) -> None:
        if self._time_end <= self._time_start:
            return

        x = self._time_to_x(self._playhead_time)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Playhead line
        pen = QPen(QColor(_PLAYHEAD_RED), _PLAYHEAD_WIDTH)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, self.height())

        # Top triangle indicator
        painter.setBrush(QBrush(QColor(_PLAYHEAD_RED)))
        painter.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.moveTo(x - 5, 0)
        path.lineTo(x + 5, 0)
        path.lineTo(x, 7)
        path.closeSubpath()
        painter.drawPath(path)

        # Time label near playhead
        ts_str = datetime.fromtimestamp(self._playhead_time).strftime("%H:%M:%S")
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(ts_str)

        label_x = x + 6
        if label_x + tw + 4 > self.width():
            label_x = x - tw - 10

        # Label background
        label_bg = QRect(label_x - 2, 2, tw + 4, 14)
        painter.setBrush(QBrush(QColor(_PLAYHEAD_RED)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(label_bg, 3, 3)

        # Label text
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(label_x, 13, ts_str)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════
# Main Timeline Widget
# ═════════════════════════════════════════════════════════════════════════


class SessionTimelineWidget(QWidget):
    """Screenpipe-inspired session timeline with filmstrip, event markers,
    time ruler, and transcription context."""

    screenshotSelected = pyqtSignal(str)     # absolute path to full-res screenshot
    interactionSelected = pyqtSignal(int)    # interaction index in history

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._session_id: Optional[str] = None
        self._all_events: list[dict] = []
        self._screenshot_events: list[dict] = []
        self._marker_events: list[dict] = []
        self._time_start: float = 0.0
        self._time_end: float = 1.0
        self._collapsed: bool = False
        self._zoom: float = 1.0
        self._base_total_width: int = 800  # width at zoom=1.0

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header bar with toggle ──
        header = QWidget()
        header.setObjectName("timeline_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 4, 12, 4)
        header_layout.setSpacing(8)

        self._title_label = QLabel("⏱️ Session Timeline")
        self._title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                font-weight: bold;
                color: {_ACCENT_BLUE};
                background: transparent;
            }}
        """)
        header_layout.addWidget(self._title_label)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {_TEXT_DIM};
                background: transparent;
            }}
        """)
        header_layout.addWidget(self._info_label)
        header_layout.addStretch()

        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedSize(24, 24)
        self._toggle_btn.setToolTip("Collapse / Expand timeline")
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_BG_SURFACE};
                color: {_TEXT_MID};
                border: 1px solid {_BORDER};
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3e4451;
                color: {_ACCENT_BLUE};
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._toggle_btn)

        root.addWidget(header)

        # ── Collapsible content ──
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Scroll area for horizontally scrollable timeline tracks
        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(False)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {_BG_DARK};
                border: none;
            }}
            QScrollBar:horizontal {{
                background: {_BG_DARK};
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: #555;
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
        """)

        # Inner container for aligned tracks
        self._tracks_container = QWidget()
        tracks_layout = QVBoxLayout(self._tracks_container)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(0)

        # Filmstrip
        self._filmstrip = _FilmstripWidget()
        self._filmstrip.thumbnailClicked.connect(self._on_thumbnail_clicked)
        tracks_layout.addWidget(self._filmstrip)

        # App track (between filmstrip and event markers)
        self._app_track = _AppTrackWidget()
        tracks_layout.addWidget(self._app_track)

        # Event markers
        self._event_track = _EventTrackWidget()
        self._event_track.eventClicked.connect(self._on_event_clicked)
        tracks_layout.addWidget(self._event_track)

        # Time ruler (also handles click-to-seek / drag)
        self._ruler = _TimeRulerWidget()
        self._ruler.playheadMoved.connect(self._on_ruler_seek)
        tracks_layout.addWidget(self._ruler)

        self._scroll.setWidget(self._tracks_container)
        content_layout.addWidget(self._scroll)

        # Allow dragging playhead anywhere
        self._tracks_container.installEventFilter(self)
        self._filmstrip.installEventFilter(self)
        self._app_track.installEventFilter(self)
        self._event_track.installEventFilter(self)
        self._ruler.installEventFilter(self)

        # Playhead overlay (purely visual — mouse events pass through)
        self._playhead = _PlayheadOverlay(self._tracks_container)
        self._playhead.hide()

        # Transcription context panel (fixed height, no splitter)
        self._transcription_panel = _TranscriptionPanel()
        self._transcription_panel.lineClicked.connect(self._on_transcription_line_clicked)
        self._transcription_panel.setFixedHeight(_TRANSCRIPTION_HEIGHT)
        content_layout.addWidget(self._transcription_panel)

        root.addWidget(self._content)

        # Placeholder for empty state
        self._placeholder = QLabel("No timeline data — enable periodic screenshots to build a visual history")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"""
            QLabel {{
                color: {_TEXT_DIM};
                font-size: 12px;
                font-style: italic;
                padding: 20px;
                background: transparent;
            }}
        """)
        self._placeholder.hide()
        root.addWidget(self._placeholder)

    # noinspection PyPep8Naming
    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            if getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                if obj in (self._tracks_container, self._filmstrip, self._app_track, self._event_track, self._ruler):
                    pos = event.position().toPoint()
                    if obj != self._tracks_container:
                        pos = obj.mapTo(self._tracks_container, pos)
                    playhead_x = self._playhead._time_to_x(self._playhead._playhead_time)
                    if abs(pos.x() - playhead_x) <= 12:
                        self._dragging_playhead = True
                        return True
        elif event.type() == QEvent.Type.MouseMove:
            if getattr(self, "_dragging_playhead", False):
                pos = event.position().toPoint()
                if obj != self._tracks_container:
                    pos = obj.mapTo(self._tracks_container, pos)
                ts = self._ruler._x_to_time(pos.x())
                ts = max(self._time_start, min(self._time_end, ts))
                self._playhead.set_playhead_time(ts)
                self._on_playhead_moved(ts)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
                if getattr(self, "_dragging_playhead", False):
                    self._dragging_playhead = False
                    return True
        return super().eventFilter(obj, event)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            SessionTimelineWidget {{
                background-color: {_BG_PANEL};
                border-top: 1px solid {_BORDER};
            }}
            #timeline_header {{
                background-color: {_BG_SURFACE};
                border-bottom: 1px solid {_BORDER};
            }}
        """)

    # ── Public API ───────────────────────────────────────────────────────

    def load_session(self, session_id: str) -> None:
        """Load timeline events for the given session."""
        from core.session_manager import SessionManager

        self._session_id = session_id
        self._all_events = SessionManager.get_timeline_events(session_id)

        self._screenshot_events = [e for e in self._all_events if e["type"] == "screenshot"]
        self._marker_events = [e for e in self._all_events if e["type"] != "screenshot"]

        if not self._all_events:
            self._show_placeholder()
            return

        self._placeholder.hide()
        self._content.show()

        # Time range
        self._time_start = self._all_events[0]["timestamp"]
        self._time_end = self._all_events[-1]["timestamp"]
        # Add 5% padding
        span = max(self._time_end - self._time_start, 1.0)
        self._time_start -= span * 0.02
        self._time_end += span * 0.02

        # Base width at zoom=1.0 (screenshot count drives it)
        self._base_total_width = max(
            _MIN_FILMSTRIP_WIDTH,
            len(self._screenshot_events) * (_THUMB_WIDTH + _THUMB_GAP) + _THUMB_GAP,
            800,  # minimum useful width
        )
        self._zoom = 1.0

        # Apply layout at current zoom
        self._apply_zoom()

        # Setup playhead overlay
        self._playhead.set_time_range(self._time_start, self._time_end)
        mid_time = (self._time_start + self._time_end) / 2
        self._playhead.set_playhead_time(mid_time)
        self._playhead.show()

        # Transcription
        self._load_transcription_with_timestamps(session_id)

        # Update info label
        n_ss = len(self._screenshot_events)
        n_ev = len(self._marker_events)
        duration = self._time_end - self._time_start
        dur_str = self._format_duration(duration)
        self._info_label.setText(f"{n_ss} screenshots  •  {n_ev} events  •  {dur_str}")

        # Defer playhead resize to after layout settles
        QTimer.singleShot(50, self._resize_playhead)

    def navigate_to_interaction(self, interaction_index: int) -> None:
        """Move the playhead to the given interaction's timestamp."""
        for ev in self._all_events:
            if ev["type"] == "interaction" and ev["data"]["index"] == interaction_index:
                self.navigate_to_time(ev["timestamp"])
                break

    def navigate_to_time(self, timestamp: float) -> None:
        """Move the playhead to *timestamp* and update all dependent views.

        This is the main entry point for external callers (e.g. the session
        browser) that want to jump the timeline to a specific moment.
        """
        self._playhead.set_playhead_time(timestamp)
        self._on_playhead_moved(timestamp)
        self._scroll_to_nearest_screenshot(timestamp)

    def clear(self) -> None:
        """Reset the timeline to empty state."""
        self._session_id = None
        self._all_events = []
        self._screenshot_events = []
        self._marker_events = []
        self._filmstrip.set_screenshots([], 0.0, 1.0, 800)
        self._playhead.hide()
        self._show_placeholder()

    # ── Internal ────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        self._content.hide()
        self._placeholder.show()
        self._info_label.setText("")

    def _resize_playhead(self) -> None:
        """Resize the playhead overlay to match the tracks container."""
        self._playhead.setGeometry(0, 0, self._tracks_container.width(), self._tracks_container.height())

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._content.hide()
            self._placeholder.hide()
            self.setFixedHeight(_HEADER_HEIGHT)
        else:
            self._content.show()
            if not self._all_events:
                self._placeholder.show()
            self._update_fixed_height()
        self._toggle_btn.setText("▶" if self._collapsed else "▼")

    def _load_transcription_with_timestamps(self, session_id: str) -> None:
        """Load transcription and assign approximate timestamps."""
        from core.session_manager import _session_transcription_path

        path = _session_transcription_path(session_id)
        if not os.path.isfile(path):
            self._transcription_panel.set_transcription_lines_with_timestamps([])
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_lines = f.readlines()
        except IOError:
            self._transcription_panel.set_transcription_lines_with_timestamps([])
            return

        # We need to assign timestamps to each line.
        # Strategy: distribute transcription lines proportionally between
        # the session start/end time, using interaction timestamps as anchors.
        interaction_ts = [
            e["timestamp"] for e in self._all_events if e["type"] == "interaction"
        ]

        lines_with_ts: list[tuple[float, str]] = []
        non_empty_lines = [(i, line.strip()) for i, line in enumerate(raw_lines) if line.strip()]

        if not non_empty_lines:
            self._transcription_panel.set_transcription_lines_with_timestamps([])
            return

        total_lines = len(non_empty_lines)
        t_start = self._time_start
        t_end = self._time_end

        for seq_idx, (line_idx, text) in enumerate(non_empty_lines):
            # Linear interpolation across the session's time range
            frac = seq_idx / max(total_lines - 1, 1)
            ts = t_start + frac * (t_end - t_start)
            lines_with_ts.append((ts, text))

        self._transcription_panel.set_transcription_lines_with_timestamps(lines_with_ts)

    def _on_thumbnail_clicked(self, index: int) -> None:
        if 0 <= index < len(self._screenshot_events):
            ss = self._screenshot_events[index]
            self._playhead.set_playhead_time(ss["timestamp"])
            self._transcription_panel.navigate_to_time(ss["timestamp"])
            self.screenshotSelected.emit(ss["data"]["path"])

    def _on_event_clicked(self, event: dict) -> None:
        self._playhead.set_playhead_time(event["timestamp"])
        self._transcription_panel.navigate_to_time(event["timestamp"])

        if event["type"] == "interaction":
            idx = event["data"]["index"]
            self.interactionSelected.emit(idx)

        # Scroll to nearest screenshot
        self._scroll_to_nearest_screenshot(event["timestamp"])

    def _on_ruler_seek(self, ts: float) -> None:
        """Ruler click/drag — move playhead and update everything."""
        self._playhead.set_playhead_time(ts)
        self._on_playhead_moved(ts)

    def _on_transcription_line_clicked(self, ts: float) -> None:
        """User clicked a transcription line — jump the timeline there."""
        self.navigate_to_time(ts)

    def _on_playhead_moved(self, ts: float) -> None:
        self._transcription_panel.navigate_to_time(ts)

        # Highlight nearest screenshot
        nearest_idx = self._find_nearest_screenshot(ts)
        if nearest_idx >= 0:
            self._filmstrip.set_selected_index(nearest_idx)
            self.screenshotSelected.emit(self._screenshot_events[nearest_idx]["data"]["path"])

    def _find_nearest_screenshot(self, ts: float) -> int:
        if not self._screenshot_events:
            return -1
        best_idx = 0
        best_dist = abs(self._screenshot_events[0]["timestamp"] - ts)
        for i, ss in enumerate(self._screenshot_events[1:], 1):
            dist = abs(ss["timestamp"] - ts)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return best_idx

    def _scroll_to_nearest_screenshot(self, ts: float) -> None:
        """Scroll the filmstrip so the nearest screenshot is visible."""
        nearest_idx = self._find_nearest_screenshot(ts)
        if nearest_idx < 0:
            return

        target_x = self._playhead._time_to_x(self._screenshot_events[nearest_idx]["timestamp"])
        viewport_w = self._scroll.viewport().width()
        # Centre the thumbnail in the viewport
        scroll_to = max(0, int(target_x - viewport_w / 2))
        self._scroll.horizontalScrollBar().setValue(scroll_to)

    # ── Zoom ─────────────────────────────────────────────────────────────

    def _apply_zoom(self) -> None:
        """Recalculate total width from base width × zoom and re-layout."""
        total_w = max(_MIN_FILMSTRIP_WIDTH, int(self._base_total_width * self._zoom))

        self._filmstrip.set_screenshots(
            self._screenshot_events, self._time_start, self._time_end, total_w
        )

        self._app_track.set_data(
            self._screenshot_events, self._time_start, self._time_end, total_w
        )

        self._event_track.set_events(
            self._marker_events, self._time_start, self._time_end, total_w
        )
        self._ruler.set_time_range(self._time_start, self._time_end, total_w)

        # Show/hide app track based on whether any screenshot has app metadata
        has_app_data = any(
            ss.get("data", {}).get("app_name") for ss in self._screenshot_events
        )
        self._app_track.setVisible(has_app_data)
        app_h = _APP_TRACK_HEIGHT if has_app_data else 0

        tracks_h = (_THUMB_HEIGHT + 28) + app_h + _MARKER_TRACK_HEIGHT + _RULER_HEIGHT
        self._tracks_container.setFixedSize(total_w, tracks_h)

        # Scroll area height = tracks + horizontal scrollbar (8px)
        self._scroll.setFixedHeight(tracks_h + 8)

        self._playhead.set_time_range(self._time_start, self._time_end)
        QTimer.singleShot(10, self._resize_playhead)

        self._update_fixed_height()

    def _update_fixed_height(self) -> None:
        """Set the widget to a fixed height that fits all components exactly."""
        if self._collapsed:
            return
        has_app_data = any(
            ss.get("data", {}).get("app_name") for ss in self._screenshot_events
        )
        app_h = _APP_TRACK_HEIGHT if has_app_data else 0
        tracks_h = (_THUMB_HEIGHT + 28) + app_h + _MARKER_TRACK_HEIGHT + _RULER_HEIGHT
        scroll_h = tracks_h + 8  # + horizontal scrollbar
        total = _HEADER_HEIGHT + scroll_h + _TRANSCRIPTION_HEIGHT
        self.setFixedHeight(total)

    # noinspection PyPep8Naming
    def wheelEvent(self, event) -> None:
        """Ctrl+scroll zooms the timeline; plain scroll scrolls horizontally."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._zoom = min(_ZOOM_MAX, self._zoom + _ZOOM_STEP)
            elif delta < 0:
                self._zoom = max(_ZOOM_MIN, self._zoom - _ZOOM_STEP)
            self._apply_zoom()
            event.accept()
        else:
            # Forward horizontal scroll
            if event.angleDelta().y() != 0:
                sb = self._scroll.horizontalScrollBar()
                sb.setValue(sb.value() - event.angleDelta().y())
                event.accept()
            else:
                super().wheelEvent(event)

    # noinspection PyPep8Naming
    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._playhead.isVisible():
            QTimer.singleShot(0, self._resize_playhead)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            return f"{h}h {m}m"
