import pytest
from textual.widgets import Input, ListView, Markdown

from bpx.app import ChatApp
from bpx.widgets.model_picker import ModelPicker
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


async def _command(app, pilot, text):
    prompt = app.query_one("#prompt", Input)
    prompt.value = text
    await prompt.action_submit()
    await pilot.pause()


async def test_slash_model_switches_and_persists(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _command(app, pilot, "/model gemma")
        assert app.model_name == "gemma"
        assert app.store.get_conversation(app.conversation_id).model_name == "gemma"
        assert "gemma" in app.sub_title  # status badge updated
        assert app.store.list_messages(app.conversation_id) == []  # command isn't a message


async def test_unknown_model_ignored(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _command(app, pilot, "/model nope")
        assert app.model_name == "base"  # unchanged


async def test_switched_model_used_for_next_reply(db):
    app = ChatApp(client_factory=_factory("hi"))
    async with app.run_test() as pilot:
        await _command(app, pilot, "/model gemma")
        await _send(app, pilot, "hello")
        msgs = app.store.list_messages(app.conversation_id)
        assert msgs[-1].role == "assistant"
        assert msgs[-1].model_name == "gemma"


async def test_model_picker_opens_and_selects(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        app.action_model_picker()
        await pilot.pause()
        picker = app.screen  # the modal is the top screen on the stack
        assert isinstance(picker, ModelPicker)
        lv = picker.query_one(ListView)
        lv.index = app.registry.names().index("gemma")
        lv.action_select_cursor()
        await pilot.pause()
        assert app.model_name == "gemma"


def _sidebar_count(app) -> int:
    return len(app.query_one("#sidebar", ListView).children)


async def test_new_conversation_switches_and_clears(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _send(app, pilot, "hello")
        first = app.conversation_id
        await _command(app, pilot, "/new")
        assert app.conversation_id != first
        assert app.store.list_messages(app.conversation_id) == []  # fresh chat
        assert _sidebar_count(app) == 2


async def test_delete_selects_another(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        first = app.conversation_id
        await _command(app, pilot, "/new")
        second = app.conversation_id
        await _command(app, pilot, "/delete")  # deletes the active (second)
        ids = [c.id for c in app.store.list_conversations(app.store.default_project_id())]
        assert second not in ids
        assert app.conversation_id == first
        assert _sidebar_count(app) == 1


async def test_delete_last_creates_fresh(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        only = app.conversation_id
        await _command(app, pilot, "/delete")
        assert app.conversation_id != only  # never left with zero conversations
        assert len(app.store.list_conversations(app.store.default_project_id())) == 1


async def test_select_conversation_from_sidebar(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        first = app.conversation_id
        await _command(app, pilot, "/new")  # second active; sidebar order [second, first]
        lv = app.query_one("#sidebar", ListView)
        lv.index = 1  # the older conversation
        lv.action_select_cursor()
        await pilot.pause()
        assert app.conversation_id == first
