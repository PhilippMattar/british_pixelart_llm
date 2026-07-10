"""Textual chat app with a conversation sidebar and SQLite persistence (Phase 1).

See PLAN.md §5, §9. A left sidebar lists conversations (newest first); the right pane is
the streaming chat log + input. Conversations are created/switched/removed (R4) and each
resumes with full scrollback (R3). Slash commands drive it: `/new`, `/delete`, `/model`,
`/help`, `/quit`. The active model is pinned per conversation and shown in the Header badge
(R5). `client_factory` is injectable so tests can supply a fake streaming client (offline).
"""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Markdown

from .llm import LLMClient, Message
from .registry import ModelSpec, Registry, client_for
from .store import Store
from .widgets.model_picker import ModelPicker
from .widgets.spinner import WaitingIndicator

DEFAULT_TITLE = "New conversation"


class ChatApp(App[None]):
    TITLE = "bpx"
    SUB_TITLE = "british_pixelart_llm"

    CSS = """
    #sidebar { width: 32; border-right: solid $panel; }
    #sidebar > ListItem { padding: 0 1; }
    #main { width: 1fr; }
    #log { height: 1fr; padding: 1 2; }
    #log Markdown { margin: 0 0 1 0; }
    #prompt { margin: 0 1 1 1; }
    """

    BINDINGS = [
        ("escape", "cancel", "Stop generating"),
        ("ctrl+n", "new_conversation", "New"),
        ("ctrl+o", "model_picker", "Model"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self, *, client_factory: Callable[[ModelSpec], LLMClient] = client_for
    ) -> None:
        super().__init__()
        self.registry = Registry.load()
        self._client_factory = client_factory
        self.store: Store | None = None
        self.model_name = "qwen"
        self.conversation_id: int | None = None
        self._project_id: int | None = None
        self._conversation_ids: list[int] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="sidebar")
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                yield WaitingIndicator(id="waiting")
                yield Input(placeholder="Message bpx…   (/new · /model · /help)", id="prompt")
        yield Footer()

    async def on_mount(self) -> None:
        self.store = Store.open()
        self._project_id = self.store.default_project_id()
        conversations = self.store.list_conversations(self._project_id)
        conversation_id = (
            conversations[0].id
            if conversations
            else self.store.create_conversation(self._project_id, self.model_name)
        )
        await self._load_conversation(conversation_id)
        await self._refresh_sidebar()
        self.query_one("#prompt", Input).focus()

    def on_unmount(self) -> None:
        if self.store is not None:
            self.store.close()

    # -- rendering helpers --
    @staticmethod
    def _user_md(content: str) -> str:
        return f"**You**\n\n{content}"

    @staticmethod
    def _assistant_md(content: str, model: str, *, stopped: bool = False) -> str:
        marker = " _(stopped)_" if stopped else ""
        return f"**{model}**{marker}\n\n{content or '…'}"

    async def _mount(self, markdown: str) -> Markdown:
        widget = Markdown(markdown)
        await self.query_one("#log", VerticalScroll).mount(widget)
        widget.scroll_visible()
        return widget

    async def _load_conversation(self, conversation_id: int) -> None:
        assert self.store is not None
        conversation = self.store.get_conversation(conversation_id)
        assert conversation is not None
        self.conversation_id = conversation_id
        self.model_name = conversation.model_name
        log = self.query_one("#log", VerticalScroll)
        await log.remove_children()
        for message in self.store.list_messages(conversation_id):
            if message.role == "user":
                await log.mount(Markdown(self._user_md(message.content)))
            else:
                await log.mount(
                    Markdown(
                        self._assistant_md(
                            message.content,
                            message.model_name or self.model_name,
                            stopped=not message.complete,
                        )
                    )
                )
        log.scroll_end(animate=False)
        self._update_status()

    async def _refresh_sidebar(self) -> None:
        """Rebuild the conversation list (newest first) and re-highlight the active one."""
        assert self.store is not None and self._project_id is not None
        conversations = self.store.list_conversations(self._project_id)
        self._conversation_ids = [c.id for c in conversations]
        sidebar = self.query_one("#sidebar", ListView)
        await sidebar.clear()
        for conversation in conversations:
            await sidebar.append(ListItem(Label(conversation.title or DEFAULT_TITLE)))
        # Setting .index highlights without emitting Selected, so this won't reload.
        if self.conversation_id in self._conversation_ids:
            sidebar.index = self._conversation_ids.index(self.conversation_id)

    def _update_status(self) -> None:
        """Status badge (Header sub-title): active model · conversation title."""
        if self.store is None or self.conversation_id is None:
            return
        conversation = self.store.get_conversation(self.conversation_id)
        title = conversation.title if conversation is not None else ""
        self.sub_title = f"{self.model_name}  ·  {title}"

    # -- conversation switching / CRUD --
    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "sidebar":
            return  # ignore selections from other list views (e.g. the model picker)
        index = event.list_view.index
        if index is None:
            return
        conversation_id = self._conversation_ids[index]
        if conversation_id != self.conversation_id:
            await self._load_conversation(conversation_id)
        self.query_one("#prompt", Input).focus()

    async def action_new_conversation(self) -> None:
        assert self.store is not None and self._project_id is not None
        conversation_id = self.store.create_conversation(self._project_id, self.model_name)
        await self._load_conversation(conversation_id)
        await self._refresh_sidebar()
        self.query_one("#prompt", Input).focus()

    async def action_delete_conversation(self) -> None:
        assert self.store is not None and self._project_id is not None
        if self.conversation_id is None:
            return
        self.store.delete_conversation(self.conversation_id)
        remaining = self.store.list_conversations(self._project_id)
        next_id = (
            remaining[0].id
            if remaining
            else self.store.create_conversation(self._project_id, self.model_name)
        )
        await self._load_conversation(next_id)
        await self._refresh_sidebar()
        self.query_one("#prompt", Input).focus()

    # -- send / generate --
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self.store is None or self.conversation_id is None:
            return
        event.input.value = ""
        if text.startswith("/"):
            await self._handle_command(text)
            return
        self.store.add_message(self.conversation_id, "user", text)
        self.store.touch(self.conversation_id)
        self._maybe_set_title(text)
        await self._mount(self._user_md(text))
        await self._refresh_sidebar()
        self.generate()

    # -- slash commands --
    async def _handle_command(self, text: str) -> None:
        parts = text[1:].split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if command == "model":
            if arg:
                self._switch_model(arg)
            else:
                self.action_model_picker()
        elif command == "new":
            await self.action_new_conversation()
        elif command in ("delete", "del", "rm"):
            await self.action_delete_conversation()
        elif command in ("quit", "q", "exit"):
            self.exit()
        elif command == "help":
            self.notify(
                "/new · /delete · /model [name] · /help · /quit",
                title="Commands",
                timeout=6,
            )
        elif command in ("project", "rag", "search", "memory"):
            self.notify(f"/{command} arrives in a later phase.")
        else:
            self.notify(f"Unknown command: /{command}", severity="warning")

    def _switch_model(self, name: str) -> None:
        if name not in self.registry.names():
            self.notify(
                f"Unknown model '{name}'. Available: {', '.join(self.registry.names())}",
                severity="warning",
            )
            return
        assert self.conversation_id is not None and self.store is not None
        self.model_name = name
        self.store.set_model(self.conversation_id, name)
        self._update_status()
        self.notify(f"Model → {name}")

    def action_model_picker(self) -> None:
        self.push_screen(
            ModelPicker(self.registry.names(), self.model_name), self._on_model_picked
        )

    def _on_model_picked(self, name: str | None) -> None:
        if name:
            self._switch_model(name)

    def _maybe_set_title(self, text: str) -> None:
        assert self.store is not None and self.conversation_id is not None
        conversation = self.store.get_conversation(self.conversation_id)
        if conversation is not None and conversation.title == DEFAULT_TITLE:
            title = text.splitlines()[0][:40].strip() or DEFAULT_TITLE
            self.store.set_title(self.conversation_id, title)

    @work(exclusive=True)
    async def generate(self) -> None:
        assert self.store is not None and self.conversation_id is not None
        conversation_id = self.conversation_id
        prompt = [
            Message(m.role, m.content)
            for m in self.store.list_messages(conversation_id)
            if m.content
        ]
        client = self._client_factory(self.registry.get(self.model_name))
        assistant_id = self.store.add_message(
            conversation_id, "assistant", "", model_name=self.model_name, complete=False
        )
        bubble = await self._mount(self._assistant_md("", self.model_name))
        log = self.query_one("#log", VerticalScroll)
        waiting = self.query_one("#waiting", WaitingIndicator)
        waiting.start()
        acc = ""
        cancelled = False
        try:
            async for delta in client.stream(prompt):
                acc += delta
                await bubble.update(self._assistant_md(acc, self.model_name))
                log.scroll_end(animate=False)
        except CancelledError:
            cancelled = True
            raise
        finally:
            waiting.stop(cancelled=cancelled)
            self.store.update_message(assistant_id, acc, complete=not cancelled)
            self.store.touch(conversation_id)

    def action_cancel(self) -> None:
        self.workers.cancel_all()
