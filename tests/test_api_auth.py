"""The remote-control API must refuse every request without the right key."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import core.api_server as api_server
from core.remote_auth import (
    REDACTED,
    is_loopback,
    key_matches,
    pairing_address,
    pairing_uri,
    redact_secrets,
)

KEY = "test-key-123"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api_server, "_api_key", KEY)
    monkeypatch.setattr(
        api_server,
        "_app_config",
        {"api_server_key": KEY, "openrouter_api_key": "sk-or", "model": "m"},
    )
    return TestClient(api_server.app)


# Routes that need no app state beyond the key check.
PROTECTED_GETS = ["/status", "/config", "/response_image"]


@pytest.mark.parametrize("path", PROTECTED_GETS)
def test_get_routes_reject_missing_key(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_GETS)
def test_get_routes_reject_wrong_key(client, path):
    assert client.get(path, headers={"Authorization": "nope"}).status_code == 401


def test_status_accepts_raw_and_bearer_key(client):
    assert client.get("/status", headers={"Authorization": KEY}).status_code == 200
    bearer = {"Authorization": f"Bearer {KEY}"}
    assert client.get("/status", headers=bearer).status_code == 200


def test_post_routes_reject_missing_key(client):
    assert client.post("/keyboard/type", json={"text": "x"}).status_code == 401
    assert client.post("/mouse/click", json={"button": "left"}).status_code == 401


def test_config_redacts_every_secret(client):
    body = client.get("/config", headers={"Authorization": KEY}).json()
    assert body["api_server_key"] == REDACTED
    assert body["openrouter_api_key"] == REDACTED
    assert body["model"] == "m"


def test_empty_server_key_locks_the_api(client, monkeypatch):
    monkeypatch.setattr(api_server, "_api_key", "")
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"Authorization": ""}).status_code == 401


def test_websocket_rejects_missing_key(client):
    with pytest.raises(WebSocketDisconnect) as exc, client.websocket_connect("/ws"):
        pass
    assert exc.value.code == 1008


def test_websocket_rejects_wrong_query_key(client):
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws?key=wrong"):
        pass


def test_websocket_accepts_header_and_query_key(client, monkeypatch):
    connects = []
    monkeypatch.setattr(
        api_server, "_handle_connect", lambda cfg: connects.append(1) or {"ok": 1}
    )
    monkeypatch.setattr(api_server, "_handle_disconnect", lambda: None)
    with client.websocket_connect("/ws", headers={"Authorization": KEY}) as ws:
        assert ws.receive_json() == {"ok": 1}
    with client.websocket_connect(f"/ws?key={KEY}") as ws:
        assert ws.receive_json() == {"ok": 1}
    assert len(connects) == 2


def test_key_matches():
    assert key_matches("abc", "abc")
    assert key_matches("  Bearer abc ", "abc")
    assert not key_matches("abd", "abc")
    assert not key_matches(None, "abc")
    assert not key_matches("abc", "")


def test_redact_secrets_is_recursive_and_keeps_empty_values():
    config = {"a": [{"x_token": "t"}], "b_password": "p", "c_key": "", "d": 1}
    assert redact_secrets(config) == {
        "a": [{"x_token": REDACTED}],
        "b_password": REDACTED,
        "c_key": "",
        "d": 1,
    }


def test_pairing_address_and_uri():
    assert is_loopback("127.0.0.1") and is_loopback("localhost")
    assert pairing_address("127.0.0.1") is None
    assert pairing_address("10.0.0.7") == "10.0.0.7"
    uri = pairing_uri("10.0.0.7", 3031, "a/b+c")
    assert uri == "snapsolve://pair?host=10.0.0.7&port=3031&key=a%2Fb%2Bc"


def test_export_route_needs_key_and_validates_format(client, monkeypatch):
    import core.sessions.export as export

    monkeypatch.setattr(export, "export_session", lambda sid, fmt: f"{sid}:{fmt}")
    assert client.get("/sessions/s1/export").status_code == 401
    ok = client.get("/sessions/s1/export?format=json", headers={"Authorization": KEY})
    assert ok.status_code == 200 and ok.text == "s1:json"
    bad = client.get("/sessions/s1/export?format=exe", headers={"Authorization": KEY})
    assert bad.status_code == 400


def test_health_reports_injected_status(client, monkeypatch):
    import requests

    import core.sources.whisperlive_manager as wl

    monkeypatch.setattr(api_server, "_status_provider", lambda: {"ocr": "FakeOCR"})
    monkeypatch.setattr(wl, "is_whisperlive_service_online", lambda: False)

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", offline)
    body = client.get("/health", headers={"Authorization": KEY}).json()
    assert body["downstream_services"] == {
        "ocr": "FakeOCR",
        "whisperlive": "offline",
        "antigravity": "offline",
    }
