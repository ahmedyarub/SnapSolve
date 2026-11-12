"""Dialog that pairs the Android remote: a QR code with this computer's address and key."""

import io

import segno
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout

from core.api_server import current_pairing

_dialog: QDialog | None = None


def _qr_pixmap(text: str) -> QPixmap:
    buffer = io.BytesIO()
    segno.make(text, error="m").save(buffer, kind="png", scale=8, border=2)
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap


def _build_dialog() -> QDialog:
    info = current_pairing()
    dialog = QDialog()
    dialog.setWindowTitle("Pair Android remote")
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    layout = QVBoxLayout(dialog)

    def note(text: str) -> None:
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)

    if not info["running"]:
        note(
            "The remote-control server is not running. Set enable_api_server to "
            "true in config/config.json and restart SnapSolve."
        )
    elif info["uri"] is None:
        note(
            f"The server only accepts connections from this computer "
            f"(api_server_host is {info['bind_host']}). To use a phone, set "
            "api_server_host to 0.0.0.0 in config/config.json and restart."
        )
    else:
        note("In the SnapSolve Remote app, tap “Scan pairing code” and scan this:")
        qr = QLabel()
        qr.setPixmap(_qr_pixmap(info["uri"]))
        qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr)
        note(
            f"Or enter it by hand: address {info['address']}, port {info['port']}, key:"
        )
        key_field = QLineEdit(info["key"])
        key_field.setReadOnly(True)
        layout.addWidget(key_field)
        note("Anyone with this key can control this computer; keep it private.")
    return dialog


def show_pairing_dialog() -> None:
    """Show the dialog (Qt main thread only); a second call refreshes it."""
    global _dialog
    if _dialog is not None:
        _dialog.close()
    _dialog = _build_dialog()
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
