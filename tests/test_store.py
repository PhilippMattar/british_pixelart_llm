from pathlib import Path

from bpx.store import MIGRATIONS, Store


def _open(tmp_path: Path) -> Store:
    return Store.open(tmp_path / "bpx.db")


def _project_count(store: Store) -> int:
    return store._conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]


def test_fresh_db_migrates_to_latest(tmp_path):
    store = _open(tmp_path)
    assert store.version == len(MIGRATIONS)
    store.close()


def test_reopen_is_idempotent(tmp_path):
    db = tmp_path / "bpx.db"
    first = Store.open(db)
    pid = first.default_project_id()
    first.close()

    store = Store.open(db)
    assert store.version == len(MIGRATIONS)  # not re-applied
    assert store.default_project_id() == pid  # default project not duplicated
    assert _project_count(store) == 1
    store.close()


def test_default_project_created(tmp_path):
    store = _open(tmp_path)
    assert store.default_project_id() >= 1
    assert _project_count(store) == 1
    store.close()


def test_conversation_and_message_roundtrip(tmp_path):
    store = _open(tmp_path)
    pid = store.default_project_id()
    cid = store.create_conversation(pid, model_name="base", title="Hi")
    store.add_message(cid, "user", "hello", complete=True)
    aid = store.add_message(cid, "assistant", "", model_name="base", complete=False)
    store.update_message(aid, "hello there", complete=True)

    msgs = store.list_messages(cid)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "hello there"
    assert msgs[1].complete is True

    convs = store.list_conversations(pid)
    assert len(convs) == 1 and convs[0].id == cid
    store.close()


def test_partial_message_survives_reopen(tmp_path):
    db = tmp_path / "bpx.db"
    store = Store.open(db)
    cid = store.create_conversation(store.default_project_id(), "base")
    store.add_message(cid, "assistant", "partial…", model_name="base", complete=False)
    store.close()

    reopened = Store.open(db)
    msg = reopened.list_messages(cid)[0]
    assert msg.content == "partial…"
    assert msg.complete is False
    reopened.close()


def test_cascade_delete_removes_messages(tmp_path):
    store = _open(tmp_path)
    pid = store.default_project_id()
    cid = store.create_conversation(pid, "base")
    store.add_message(cid, "user", "x")
    store.delete_conversation(cid)
    assert store.list_conversations(pid) == []
    assert store.list_messages(cid) == []
    store.close()


def test_set_model_and_title(tmp_path):
    store = _open(tmp_path)
    cid = store.create_conversation(store.default_project_id(), "base")
    store.set_model(cid, "gemma")
    store.set_title(cid, "Renamed")
    conv = store.get_conversation(cid)
    assert conv is not None
    assert conv.model_name == "gemma"
    assert conv.title == "Renamed"
    store.close()
