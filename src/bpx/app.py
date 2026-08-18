"""Textual chat app with a conversation sidebar and SQLite persistence (Phase 1).

See PLAN.md §5, §9, §10. A left sidebar lists conversations (newest first); the right pane is
the streaming chat log + input. Conversations are created/switched/removed (R4) and each
resumes with full scrollback (R3). Slash commands: `/new`, `/delete`, `/model`, `/keywords`,
`/memory`, `/rag add <path>`, `/help`, `/quit`. British/Scottish keywords overlay a persona on
the conversation's base model (§8); project memories (§9) and RAG document context (§10) are
injected as system messages. `client_factory` / `embedder_factory` are injectable so tests can
supply fakes.
"""

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Callable
from dataclasses import replace

from textual import events, work
from textual.app import App, ComposeResult
from textual.message import Message as TextualMessage
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Markdown

from pathlib import Path

from . import memory
from .llm import Chunk, LLMClient, Message
from .rag import pipeline as rag
from .rag.embed import Embedder
from .registry import ModelSpec, Registry, client_for
from .router.keywords import detect, lexicons
from .store import Store
from .widgets.keyword_help import KeywordHelp
from .widgets.memory_list import MemoryList
from .widgets.model_picker import ModelPicker
from .widgets.rag_list import RagList
from .widgets.spinner import WaitingIndicator

DEFAULT_TITLE = "New conversation"
# Files a drag-and-drop onto the prompt will ingest (§10). Dragging a file makes the terminal
# *paste its path* into the input; we detect that and route it to /rag instead of sending it.
_INGESTABLE_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}
# The standard, non-persona model every new conversation starts on (§8). Personas are an overlay
# the keyword router switches to and reverts from; they never become a conversation's base.
DEFAULT_MODEL = "qwen"
# Run background memory extraction once every this many user+assistant messages (R6, §9).
MEMORY_EVERY = 4

# Toast shown when the keyword router auto-switches persona (§8). Reverting to the base model is
# silent — it's the neutral default, not an event worth interrupting for.
_SWITCH_TOASTS = {
    "british": "Switching to British mode, mate 🇬🇧",
    "scottish": "Switching to Scottish mode, aye 🏴󠁧󠁢󠁳󠁣󠁴󠁿",
}


def _clean_drop_token(token: str) -> Path:
    """Normalise one dropped/pasted path token: quotes, file:// URLs, escaped spaces, ~."""
    token = token.strip().strip("'\"")
    if token.startswith("file://"):
        from urllib.parse import unquote, urlparse

        token = unquote(urlparse(token).path)
    token = token.replace("\\ ", " ")  # macOS terminals backslash-escape spaces on drop
    return Path(token).expanduser()


def drop_paths(text: str) -> list[Path]:
    """Ingestable file paths IFF the whole input is dropped file(s); else [] (so normal messages,
    even ones that mention a path, are never hijacked)."""
    text = text.strip()
    if not text:
        return []

    def ok(p: Path) -> bool:
        return p.is_file() and p.suffix.lower() in _INGESTABLE_SUFFIXES

    whole = _clean_drop_token(text)  # covers a single path, incl. escaped spaces
    if ok(whole):
        return [whole]
    tokens = text.replace("\n", " ").split()  # multiple simple (space-free) paths
    if len(tokens) > 1:
        cleaned = [_clean_drop_token(t) for t in tokens]
        if all(ok(p) for p in cleaned):
            return cleaned
    return []


class PromptInput(Input):
    """The message input — but a dropped *file path* is a file drop, not text. When the input is
    focused, Textual delivers the paste here (and its own handler would insert the path); we detect
    a file drop, suppress that, and emit a FileDropped message the app ingests. Normal text pastes
    behave as usual."""

    class FileDropped(TextualMessage):
        def __init__(self, paths: list[Path]) -> None:
            self.paths = paths
            super().__init__()

    def _on_paste(self, event: events.Paste) -> None:
        # Textual calls every _on_paste in the MRO, so we must NOT call super(). On a file drop,
        # prevent_default() skips Input's own paste handler and stop() keeps the raw paste from
        # also reaching App.on_paste; the app ingests via FileDropped. Normal text falls through
        # to Input's handler (no prevent_default), pasting as usual.
        paths = drop_paths(event.text)
        if paths:
            event.prevent_default()
            event.stop()
            self.post_message(self.FileDropped(paths))


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
        ("ctrl+k", "keywords", "Keywords"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        *,
        client_factory: Callable[[ModelSpec], LLMClient] = client_for,
        embedder_factory: Callable[[str], Embedder] = Embedder,
    ) -> None:
        super().__init__()
        self.registry = Registry.load()
        self._client_factory = client_factory
        self._embedder_factory = embedder_factory
        self.store: Store | None = None
        self.model_name = DEFAULT_MODEL
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
                yield PromptInput(
                    placeholder="Message bpx…   (drag a PDF to add it · /memory · /help)",
                    id="prompt",
                )
        yield Footer()

    async def on_mount(self) -> None:
        self.store = Store.open()
        self._project_id = self.store.default_project_id()
        conversations = self.store.list_conversations(self._project_id)
        conversation_id = (
            conversations[0].id
            if conversations
            else self.store.create_conversation(self._project_id, DEFAULT_MODEL)
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
    def _assistant_md(
        content: str, model: str, *, reasoning: str = "", stopped: bool = False
    ) -> str:
        marker = " _(stopped)_" if stopped else ""
        if content:
            return f"**{model}**{marker}\n\n{content}"
        if reasoning:
            # Thinking-mode progress: show the reasoning dimmed, as a quote, until the answer
            # starts — so a long think never looks like a frozen/blank reply.
            quoted = "\n".join(f"> {line}" for line in reasoning.splitlines())
            return f"**{model}** _💭 thinking…_\n\n{quoted}"
        return f"**{model}**{marker}\n\n…"

    @staticmethod
    def _event_md(content: str) -> str:
        return f"— _{content}_ —"

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
            elif message.role == "event":
                await log.mount(Markdown(self._event_md(message.content)))
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
        # Always start fresh on the standard model, not whatever the last conversation drifted to.
        conversation_id = self.store.create_conversation(self._project_id, DEFAULT_MODEL)
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
            else self.store.create_conversation(self._project_id, DEFAULT_MODEL)
        )
        await self._load_conversation(next_id)
        await self._refresh_sidebar()
        self.query_one("#prompt", Input).focus()

    # -- drag-and-drop (§10) --
    def _ingest_dropped(self, paths: list[Path]) -> None:
        self.query_one("#prompt", Input).value = ""  # a drop is a file action, not text entry
        for path in paths:
            self._rag_add(str(path))

    async def on_paste(self, event: events.Paste) -> None:
        """Handles a drop when a NON-input widget has focus (e.g. you clicked the chat history):
        the paste bubbles up to the app. A focused input instead routes through PromptInput ->
        FileDropped below. Together they make a drop work regardless of what was last clicked."""
        if self.store is None:
            return
        paths = drop_paths(event.text)
        if not paths:
            return
        event.stop()
        self._ingest_dropped(paths)

    def on_prompt_input_file_dropped(self, message: PromptInput.FileDropped) -> None:
        """A drop while the message input was focused."""
        self._ingest_dropped(message.paths)

    # -- send / generate --
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text or self.store is None or self.conversation_id is None:
            return
        event.input.value = ""
        dropped = drop_paths(text)  # a drag-and-dropped file path -> ingest, don't send
        if dropped:
            for path in dropped:
                self._rag_add(str(path))
            return
        if text.startswith("/"):
            await self._handle_command(text)
            return
        self.store.add_message(self.conversation_id, "user", text)
        self.store.touch(self.conversation_id)
        self._maybe_set_title(text)
        await self._mount(self._user_md(text))
        await self._maybe_auto_switch(text)
        await self._refresh_sidebar()
        self.generate()

    async def _maybe_auto_switch(self, text: str) -> None:
        """Keyword router (§8): a lexicon hit overlays that persona; no hit reverts to the
        conversation's base model. Skipped when a manual /model has pinned a persona. Switching
        to a persona shows a toast; reverting to the base is silent (the neutral default)."""
        assert self.store is not None and self.conversation_id is not None
        conversation = self.store.get_conversation(self.conversation_id)
        if conversation is None or not conversation.auto_switch:
            return
        persona = detect(text)
        # No keyword (or an unknown persona) -> fall back to the base model, not the current one.
        target = persona if persona in self.registry.names() else conversation.base_model
        if target == self.model_name:
            return
        self.model_name = target
        self.store.set_model(self.conversation_id, target)
        self._update_status()
        if target == persona:
            self.notify(_SWITCH_TOASTS.get(persona, f"Switching to {persona}"))

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
        elif command in ("keywords", "keys"):
            self.action_keywords()
        elif command in ("memory", "mem"):
            self.action_memory()
        elif command == "rag":
            sub = arg.split(maxsplit=1)
            if sub and sub[0].lower() == "add" and len(sub) > 1:
                self._rag_add(sub[1])
            elif not arg or arg.lower() in ("list", "ls"):
                self.action_rag()
            else:
                self.notify("Usage: /rag add <path>  ·  /rag (to list)", severity="warning")
        elif command == "help":
            self.notify(
                "/new · /model · /keywords · /memory · /rag add <path> · /help · /quit",
                title="Commands",
                timeout=6,
            )
        elif command in ("project", "search"):
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
        if self.registry.get(name).is_persona:
            # Manually choosing a persona pins it: no keyword routing until you pick a base again.
            self.store.set_auto_switch(self.conversation_id, False)
            self.notify(f"Model → {name} (pinned)")
        else:
            # Choosing a base model sets the fallback and keeps keyword routing on, so personas
            # still overlay and revert to *this* base.
            self.store.set_base_model(self.conversation_id, name)
            self.store.set_auto_switch(self.conversation_id, True)
            self.notify(f"Model → {name}")
        self._update_status()

    def action_model_picker(self) -> None:
        self.push_screen(
            ModelPicker(self.registry.names(), self.model_name), self._on_model_picked
        )

    def action_keywords(self) -> None:
        """Show the persona trigger-word lookup (Ctrl+K / /keywords)."""
        self.push_screen(KeywordHelp(lexicons()))

    def action_memory(self) -> None:
        """View/delete the project's remembered facts (/memory)."""
        assert self.store is not None and self._project_id is not None
        self.push_screen(MemoryList(self.store.list_memories(self._project_id), self._delete_memory))

    def _delete_memory(self, memory_id: int) -> None:
        assert self.store is not None
        self.store.delete_memory(memory_id)

    def _on_model_picked(self, name: str | None) -> None:
        if name:
            self._switch_model(name)

    def _maybe_set_title(self, text: str) -> None:
        assert self.store is not None and self.conversation_id is not None
        conversation = self.store.get_conversation(self.conversation_id)
        if conversation is not None and conversation.title == DEFAULT_TITLE:
            title = text.splitlines()[0][:40].strip() or DEFAULT_TITLE
            self.store.set_title(self.conversation_id, title)

    def _memory_prompt(self) -> list[Message]:
        """A leading system message of project memories (R6, §9), or empty if none."""
        assert self.store is not None and self._project_id is not None
        facts = [
            m.content
            for m in self.store.list_memories(self._project_id, limit=memory.INJECT_LIMIT)
        ]
        system = memory.system_prompt(facts)
        return [Message("system", system)] if system else []

    def _control_client(self) -> LLMClient:
        """A non-thinking client on the default model for background/control calls (memory, RAG)."""
        return self._client_factory(replace(self.registry.get(DEFAULT_MODEL), reasoning_effort="none"))

    def _embedder(self) -> Embedder:
        return self._embedder_factory(self.registry.get(DEFAULT_MODEL).endpoint)

    async def _rag_context(
        self, query: str, history: list[Message]
    ) -> tuple[list[Message], list[str]]:
        """Run the adaptive-RAG pipeline if the project has documents (§10). Returns a leading
        system message (source-tagged context) and the source legend, or empty if not retrieving."""
        assert self.store is not None and self._project_id is not None
        if not query or not self.store.list_documents(self._project_id):
            return [], []
        embedder = self._embedder()
        result = await rag.build_context(
            self._control_client(), embedder, self.store, self._project_id, query, history
        )
        if result is None:
            return [], []
        return [Message("system", result.context)], result.sources

    @work(exclusive=True)
    async def generate(self) -> None:
        assert self.store is not None and self.conversation_id is not None
        conversation_id = self.conversation_id
        history = [
            Message(m.role, m.content)
            for m in self.store.list_messages(conversation_id)
            if m.content and m.role in ("user", "assistant")  # skip event/log rows
        ]
        query = history[-1].content if history and history[-1].role == "user" else ""
        client = self._client_factory(self.registry.get(self.model_name))
        assistant_id = self.store.add_message(
            conversation_id, "assistant", "", model_name=self.model_name, complete=False
        )
        bubble = await self._mount(self._assistant_md("", self.model_name))
        log = self.query_one("#log", VerticalScroll)
        waiting = self.query_one("#waiting", WaitingIndicator)
        waiting.start()
        acc = ""
        reasoning = ""
        rag_sources: list[str] = []
        cancelled = False
        try:
            # Adaptive RAG runs before generation (slow LLM/embedding calls) — the spinner covers it.
            rag_msgs, rag_sources = await self._rag_context(query, history)
            prompt = self._memory_prompt() + rag_msgs + history
            async for chunk in client.stream(prompt):
                # Tolerate a plain-string stream (test fakes) as content; real client yields Chunk.
                kind = getattr(chunk, "kind", "content")
                text = getattr(chunk, "text", chunk)
                if kind == "reasoning":
                    reasoning += text
                else:
                    acc += text
                await bubble.update(self._assistant_md(acc, self.model_name, reasoning=reasoning))
                log.scroll_end(animate=False)
        except CancelledError:
            cancelled = True
            raise
        finally:
            waiting.stop(cancelled=cancelled)
            if rag_sources and acc and not cancelled:  # show which sources the answer used
                acc = acc.rstrip() + "\n\n---\n**Sources**\n" + "\n".join(rag_sources)
                await bubble.update(self._assistant_md(acc, self.model_name))
            self.store.update_message(assistant_id, acc, complete=not cancelled)
            self.store.touch(conversation_id)
        # Only on a clean finish (so a cancelled/partial turn doesn't feed extraction).
        self._maybe_extract_memory(conversation_id)

    def _maybe_extract_memory(self, conversation_id: int) -> None:
        """Every MEMORY_EVERY messages, kick off background fact extraction (R6, §9)."""
        assert self.store is not None
        turns = [
            m for m in self.store.list_messages(conversation_id) if m.role in ("user", "assistant")
        ]
        if turns and len(turns) % MEMORY_EVERY == 0:
            self.extract_memory(conversation_id)

    @work(group="memory")
    async def extract_memory(self, conversation_id: int) -> None:
        """Background: extract durable user facts and store the new ones. Never raises into the UI
        (memory.extract_facts swallows errors); a non-thinking client keeps it fast + clean JSON."""
        assert self.store is not None and self._project_id is not None
        transcript = [
            Message(m.role, m.content)
            for m in self.store.list_messages(conversation_id)
            if m.content and m.role in ("user", "assistant")
        ]
        existing = [m.content for m in self.store.list_memories(self._project_id)]
        new_facts = await memory.extract_facts(self._control_client(), existing, transcript)
        for fact in new_facts:
            self.store.add_memory(self._project_id, fact)
        if new_facts:
            self.notify(f"Remembered {len(new_facts)} new fact(s) · /memory", title="Memory")

    # -- RAG documents (/rag) --
    def action_rag(self) -> None:
        """View/delete ingested documents (/rag)."""
        assert self.store is not None and self._project_id is not None
        self.push_screen(RagList(self.store.list_documents(self._project_id), self._delete_document))

    def _delete_document(self, document_id: int) -> None:
        assert self.store is not None
        self.store.delete_document(document_id)

    def _rag_add(self, raw_path: str) -> None:
        path = Path(raw_path.strip().strip("'\"")).expanduser()
        if not path.is_file():
            self.notify(f"No such file: {path}", severity="warning")
            return
        self.notify(f"Indexing {path.name}…", title="RAG")
        self.ingest_document(str(path))

    @work(group="rag")
    async def ingest_document(self, path: str) -> None:
        """Background: chunk + embed a document into the project's RAG store (§10)."""
        assert self.store is not None and self._project_id is not None
        embedder = self._embedder()
        try:
            _, n_chunks = await rag.ingest_document(self.store, embedder, self._project_id, path)
        except Exception as exc:  # bad file / extraction / embedding failure
            self.notify(f"Could not index {Path(path).name}: {exc}", severity="error", title="RAG")
            return
        self.notify(f"Indexed {Path(path).name} · {n_chunks} chunks · /rag", title="RAG")

    def action_cancel(self) -> None:
        self.workers.cancel_all()
