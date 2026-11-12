"""Session storage: concurrent writers must not lose each other's changes."""

import threading

import numpy as np
import pytest

from core.sessions import index, store


@pytest.fixture(autouse=True)
def sessions_dir(tmp_path, monkeypatch):
    # SESSIONS_DIR is relative ("sessions"); run each test in an empty folder.
    monkeypatch.chdir(tmp_path)
    return tmp_path / "sessions"


def _hammer(target, threads=8, per_thread=25):
    errors = []

    def run(t):
        try:
            for i in range(per_thread):
                target(t, i)
        except Exception as e:  # surfaced by the assert below
            errors.append(e)

    workers = [threading.Thread(target=run, args=(t,)) for t in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert not errors


def test_concurrent_updates_keep_every_change():
    sid = "s1"

    def write(t, i):
        if t % 2:
            store.update_session(
                sid, lambda d: d.setdefault("history", []).append({"t": t, "i": i})
            )
        else:
            store.update_session(
                sid, lambda d: d.setdefault("corrections", []).append({"t": t, "i": i})
            )

    _hammer(write)
    data = store.read_session(sid)
    assert len(data["history"]) == 4 * 25
    assert len(data["corrections"]) == 4 * 25


def test_read_session_returns_private_copy():
    store.update_session("s2", lambda d: d.__setitem__("tags", ["a"]))
    first = store.read_session("s2")
    first["tags"].append("mutated")
    assert store.read_session("s2")["tags"] == ["a"]


def test_rename_and_tags_only_touch_existing_sessions():
    store.rename_session("missing", "x")
    assert store.read_session("missing") is None
    store.update_session("s3", lambda d: None)
    store.rename_session("s3", "Name")
    store.set_session_tags("s3", ["t1", "t2"])
    data = store.read_session("s3")
    assert (data["name"], data["tags"]) == ("Name", ["t1", "t2"])


def test_list_skips_empty_sessions_and_delete_empty(sessions_dir):
    store.update_session("empty", lambda d: None)
    store.update_session(
        "full",
        lambda d: d.update(history=[{"prompt": "p"}], updated_at=5),
    )
    assert [s["id"] for s in store.list_sessions()] == ["full"]
    assert store.count_empty_sessions() == 1
    assert store.delete_empty_sessions() == 1
    assert not (sessions_dir / "empty").exists()


def test_legacy_flat_file_is_migrated(sessions_dir):
    sessions_dir.mkdir()
    (sessions_dir / "old.json").write_text(
        '{"id": "old", "history": [{"prompt": "p"}]}'
    )
    data = store.read_session("old")
    assert data["history"] == [{"prompt": "p"}]
    assert (sessions_dir / "old" / "session.json").exists()
    assert not (sessions_dir / "old.json").exists()


def test_latest_session_id(sessions_dir):
    assert store.latest_session_id() is None
    store.update_session("a", lambda d: None)
    assert store.latest_session_id() == "a"


class _FakeEngine:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def embed_texts(self, texts):
        from core.llm.embeddings import EmbeddingError

        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingError("offline")
        return np.ones((len(texts), 3), dtype=np.float32)


def _session_with_prompt(sid="s"):
    store.update_session(
        sid, lambda d: d.update(history=[{"prompt": "hello", "response": "world"}])
    )


def test_index_reuses_embeddings_and_redoes_zero_vectors(monkeypatch):
    import core.llm.embeddings as emb

    engine = _FakeEngine()
    monkeypatch.setattr(emb, "get_embedding_engine", lambda cfg: engine)
    _session_with_prompt()
    store.atomic_json_write(
        store.session_embeddings_path("s"),
        [
            {"type": "prompt", "index": 0, "text": "hello", "embedding": [0, 0, 0]},
            {"type": "response", "index": 0, "text": "world", "embedding": [1, 2, 3]},
        ],
    )
    index.index_session_sync({}, "s")
    # The stored zero vector (an old failure) is recomputed; the real one is kept.
    assert engine.calls == [["hello"]]
    chunks = {c["text"]: c["embedding"] for c in index.get_all_embeddings()}
    assert chunks == {"hello": [1.0, 1.0, 1.0], "world": [1, 2, 3]}


def test_index_failure_keeps_previous_index(monkeypatch):
    import core.llm.embeddings as emb

    monkeypatch.setattr(emb, "get_embedding_engine", lambda cfg: _FakeEngine(fail=True))
    _session_with_prompt()
    index.index_session_sync({}, "s")
    assert index.get_all_embeddings() == []


def test_get_all_embeddings_tags_session_and_rereads_on_change():
    store.update_session("s", lambda d: None)
    path = store.session_embeddings_path("s")
    store.atomic_json_write(path, [{"type": "tag", "index": 0, "text": "a"}])
    assert [c["session_id"] for c in index.get_all_embeddings()] == ["s"]
    store.atomic_json_write(
        path,
        [
            {"type": "tag", "index": 0, "text": "a"},
            {"type": "tag", "index": 1, "text": "b"},
        ],
    )
    assert len(index.get_all_embeddings()) == 2


def test_schedule_index_merges_requests(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    passes = []

    def slow_index(config, session_id):
        passes.append(session_id)
        started.set()
        release.wait(5)

    monkeypatch.setattr(index, "index_session_sync", slow_index)
    index.schedule_index({}, "s")
    assert started.wait(5)
    for _ in range(10):  # arrive while the first pass runs
        index.schedule_index({}, "s")
    release.set()
    for _ in range(100):
        with index._state_guard:
            if "s" not in index._running:
                break
        threading.Event().wait(0.05)
    assert passes == ["s", "s"]  # the first pass plus one merged re-run


def test_session_manager_writers_do_not_clobber_each_other(monkeypatch, tmp_path):
    from core.session_manager import SessionManager

    monkeypatch.setattr(index, "schedule_index", lambda config, sid: None)
    image = tmp_path / "shot.png"
    image.write_bytes(b"png")
    manager = SessionManager({"save_transcriptions": False})

    def write(t, i):
        if t % 2:
            manager.append_interaction(f"question {t}-{i}\nmore", str(image), "a", None)
        else:
            manager.append_corrections([{"t": t, "i": i}])

    _hammer(write, threads=6, per_thread=10)
    data = store.read_session(manager.current_session_id)
    assert len(data["history"]) == 30
    assert len(data["corrections"]) == 30
    assert data["title"].startswith("question ")
    # Every interaction kept its own copy of the image.
    assert len({h["image"] for h in data["history"]}) == 30
    assert manager.get_history() == data["history"]
