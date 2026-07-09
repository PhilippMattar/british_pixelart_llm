import pytest
from textual.widgets import Input, Markdown

from bpx.app import ChatApp
from bpx.widgets.spinner import WaitingIndicator


class _FakeClient:
    """Stand-in for LLMClient — streams fixed deltas, no network."""

    def __init__(self, deltas):
        self._deltas = list(deltas)

    async def stream(self, messages):
        for delta in self._deltas:
            yield delta


def _factory(*deltas):
    return lambda spec: _FakeClient(deltas or ("hello", " there"))


async def _send(app, pilot, text):
    prompt = app.query_one("#prompt", Input)
    prompt.value = text
    await prompt.action_submit()  # queues Input.Submitted
    await pilot.pause()  # let on_input_submitted run (persist user + start worker)
    await app.workers.wait_for_complete()  # wait for streaming to finish
    await pilot.pause()


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "bpx.db"
    monkeypatch.setenv("BPX_DB", str(path))
    return path


async def test_app_composes_and_opens_conversation(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test():
        assert app.query_one("#prompt", Input) is not None
        assert app.query_one("#log") is not None
        assert app.model_name == "base"
        assert app.conversation_id is not None


async def test_send_persists_user_and_assistant(db):
    app = ChatApp(client_factory=_factory("hi", " there"))
    async with app.run_test() as pilot:
        await _send(app, pilot, "hello")

        msgs = app.store.list_messages(app.conversation_id)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[0].content == "hello"
        assert msgs[1].content == "hi there"
        assert msgs[1].complete is True
        # waiting indicator hides again once the reply completes
        assert app.query_one("#waiting", WaitingIndicator).has_class("-idle")


async def test_first_message_sets_title(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _send(app, pilot, "What is the capital of Scotland?")
        conv = app.store.get_conversation(app.conversation_id)
        assert conv.title == "What is the capital of Scotland?"


async def test_scrollback_restored_on_reopen(db):
    app1 = ChatApp(client_factory=_factory("one", " two"))
    async with app1.run_test() as pilot:
        await _send(app1, pilot, "first message")
        cid = app1.conversation_id

    app2 = ChatApp(client_factory=_factory())
    async with app2.run_test():
        assert app2.conversation_id == cid  # most-recent conversation reopened
        contents = [m.content for m in app2.store.list_messages(cid)]
        assert contents == ["first message", "one two"]
        assert len(app2.query(Markdown)) == 2  # scrollback rebuilt


async def test_empty_submit_adds_nothing(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", Input)
        prompt.value = "   "
        await prompt.action_submit()
        await pilot.pause()
        assert app.store.list_messages(app.conversation_id) == []
