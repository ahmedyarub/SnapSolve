"""Access control for the remote-control API: key checks, secret redaction, pairing.

The API can move the mouse and type on this computer, so it never runs open: a
key is generated on first start when none is configured, every HTTP route and the
WebSocket require it, and the phone gets it by scanning a pairing QR code.
"""

import hmac
import ipaddress
import re
import secrets
import socket
from typing import Any
from urllib.parse import quote

KEY_BYTES = 24  # 32 URL-safe characters
REDACTED = "***REDACTED***"
# Config keys whose values are credentials (api_server_key, openrouter_api_key,
# webhook_token, ...). Matched on the key name so new providers are covered.
_SECRET_NAME = re.compile(r"(key|token|secret|password)$", re.IGNORECASE)


def generate_api_key() -> str:
    return secrets.token_urlsafe(KEY_BYTES)


def key_matches(candidate: str | None, expected: str) -> bool:
    """Whether `candidate` ("<key>" or "Bearer <key>") equals `expected`.

    An empty `expected` matches nothing, so a missing key locks the API instead
    of opening it. The comparison takes constant time.
    """
    if not expected or not candidate:
        return False
    candidate = candidate.strip()
    if candidate[:7].lower() == "bearer ":
        candidate = candidate[7:].strip()
    return hmac.compare_digest(candidate.encode(), expected.encode())


def redact_secrets(value: Any) -> Any:
    """Copy of a config value with every credential-named entry masked."""
    if isinstance(value, dict):
        return {
            k: (
                REDACTED
                if isinstance(k, str) and _SECRET_NAME.search(k) and v
                else redact_secrets(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    return value


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def lan_address() -> str | None:
    """This computer's address on the local network, or None when offline.

    Connecting a UDP socket only selects a route; no packet is sent.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed anywhere
            address = probe.getsockname()[0]
        except OSError:
            return None
    return None if address.startswith("0.") else address


def pairing_address(bind_host: str) -> str | None:
    """The address a phone should use, or None if the server is not reachable from it."""
    if is_loopback(bind_host):
        return None
    if bind_host in ("0.0.0.0", "::", ""):
        return lan_address()
    return bind_host


def pairing_uri(host: str, port: int, key: str) -> str:
    """URI the Android app reads from the pairing QR code."""
    return f"snapsolve://pair?host={quote(host)}&port={port}&key={quote(key, safe='')}"
