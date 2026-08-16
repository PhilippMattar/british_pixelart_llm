import pytest
from textual.widgets import Input, ListView, Markdown

from bpx.app import ChatApp
from bpx.widgets.model_picker import ModelPicker
from bpx.widgets.spinner import WaitingIndicator


class _FakeClient:
    """Stand-in for LLMClient — streams fixed deltas, no network. `complete` returns a canned
    string for the memory extractor (default "[]" -> no facts, so most tests ignore memory)."""

    def __init__(self, deltas, completion="[]"):
        self._deltas = list(deltas)
        self._completion = completion
        self.seen_messages: list = []  # last stream()'s messages, for assertions

    async def stream(self, messages):
        self.seen_messages = list(messages)
        for delta in self._deltas:
            yield delta

    async def complete(self, messages):
        return self._completion


def _factory(*deltas, completion="[]"):
    return lambda spec: _FakeClient(deltas or ("hello", " there"), completion=completion)


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
        assert app.model_name == "qwen"
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
        assert app.model_name == "qwen"  # unchanged


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


async def test_keywords_help_opens_and_closes(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _command(app, pilot, "/keywords")
        from bpx.widgets.keyword_help import KeywordHelp

        assert isinstance(app.screen, KeywordHelp)
        # the modal was handed the real lexicons to display
        assert "cuppa" in app.screen._lexicons["british"]
        assert "dreich" in app.screen._lexicons["scottish"]
        app.screen.action_close()
        await pilot.pause()
        assert not isinstance(app.screen, KeywordHelp)  # dismissed back to the main screen


async def test_memory_injected_as_system_prompt(db):
    client = _FakeClient(("ok",))
    app = ChatApp(client_factory=lambda spec: client)
    async with app.run_test() as pilot:
        app.store.add_memory(app.store.default_project_id(), "The user is vegetarian.")
        await _send(app, pilot, "what should I cook?")
        assert client.seen_messages[0].role == "system"  # memory injected first
        assert "vegetarian" in client.seen_messages[0].content


async def test_no_memory_means_no_system_prompt(db):
    client = _FakeClient(("ok",))
    app = ChatApp(client_factory=lambda spec: client)
    async with app.run_test() as pilot:
        await _send(app, pilot, "hello")
        assert client.seen_messages[0].role == "user"  # nothing injected


async def test_memory_extraction_stores_new_facts(db):
    facts = '["The user is called Sam.", "The user likes hiking."]'
    app = ChatApp(client_factory=_factory("ok", completion=facts))
    async with app.run_test() as pilot:
        await _send(app, pilot, "Hi, I'm Sam.")  # 2 turns
        await _send(app, pilot, "Tell me more.")  # 4 turns -> extraction fires
        contents = [m.content for m in app.store.list_memories(app.store.default_project_id())]
        assert "The user is called Sam." in contents
        assert "The user likes hiking." in contents


async def test_memory_modal_lists_and_deletes(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        pid = app.store.default_project_id()
        mid = app.store.add_memory(pid, "The user is vegetarian.")
        app.store.add_memory(pid, "The user lives in Berlin.")
        app.action_memory()
        await pilot.pause()
        from bpx.widgets.memory_list import MemoryList

        assert isinstance(app.screen, MemoryList)
        app._delete_memory(mid)  # the modal's delete callback
        remaining = [m.content for m in app.store.list_memories(pid)]
        assert remaining == ["The user lives in Berlin."]


class _FakeEmbedder:
    async def embed(self, texts):
        return [[float(len(t)), 1.0] for t in texts]

    async def embed_one(self, text):
        return (await self.embed([text]))[0]


async def test_rag_add_ingests_document(db, tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("apple banana cherry " * 100)
    app = ChatApp(client_factory=_factory(), embedder_factory=lambda base: _FakeEmbedder())
    async with app.run_test() as pilot:
        await _command(app, pilot, f"/rag add {doc}")
        await app.workers.wait_for_complete()
        pid = app.store.default_project_id()
        docs = app.store.list_documents(pid)
        assert len(docs) == 1 and docs[0].title == "notes.txt"
        assert len(app.store.rag_chunks_for_search(pid)) >= 1


async def test_rag_modal_lists_and_deletes(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        pid = app.store.default_project_id()
        did = app.store.add_document(pid, "/x/a.txt", "a.txt")
        app.action_rag()
        await pilot.pause()
        from bpx.widgets.rag_list import RagList

        assert isinstance(app.screen, RagList)
        app._delete_document(did)
        assert app.store.list_documents(pid) == []


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


async def test_keyword_autoswitches_persona(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        assert app.model_name == "qwen"
        await _send(app, pilot, "Alright mate, fancy a cuppa? innit")
        assert app.model_name == "british"  # auto-switched on British keywords
        roles = [m.role for m in app.store.list_messages(app.conversation_id)]
        assert "event" not in roles  # switch is a toast only, not an in-chat message


async def test_manual_persona_pins_and_disables_autoswitch(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _command(app, pilot, "/model british")  # a manual PERSONA choice pins
        assert app.store.get_conversation(app.conversation_id).auto_switch is False
        await _send(app, pilot, "Aye, dinnae be daft, it's dreich")  # would auto-switch
        assert app.model_name == "british"  # but stays pinned


async def test_manual_base_keeps_autoswitch_and_reverts_to_it(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _command(app, pilot, "/model gemma")  # a base model: routing stays on
        conv = app.store.get_conversation(app.conversation_id)
        assert conv.auto_switch is True and conv.base_model == "gemma"
        await _send(app, pilot, "Aye, it's pure dreich, dinnae ye think")
        assert app.model_name == "scottish"  # persona overlays
        await _send(app, pilot, "Please summarize this paragraph.")
        assert app.model_name == "gemma"  # reverts to the chosen base, not qwen


async def test_plain_message_reverts_to_base(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _send(app, pilot, "Aye, it's pure dreich, dinnae ye think")
        assert app.model_name == "scottish"  # overlaid a persona
        await _send(app, pilot, "Please summarize this paragraph.")
        assert app.model_name == "qwen"  # no keyword -> back to the default base


async def test_new_conversation_resets_to_default_model(db):
    app = ChatApp(client_factory=_factory())
    async with app.run_test() as pilot:
        await _send(app, pilot, "Alright mate, fancy a cuppa? innit")
        assert app.model_name == "british"  # drifted to a persona
        await _command(app, pilot, "/new")
        assert app.model_name == "qwen"  # a fresh conversation starts on the standard model
