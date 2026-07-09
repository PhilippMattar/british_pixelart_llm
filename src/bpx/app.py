"""Minimal streaming chat loop (Phase 0). See PLAN.md §5, §9.

Intentionally small: one screen, a scrollable log, an input, streamed assistant
replies with Esc-to-stop. Projects, sidebar, persistence, personas, and pixel-art
arrive in later phases.
"""

from __future__ import annotations

from asyncio import CancelledError

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Markdown

from .llm import Message
from .registry import Registry, client_for


class ChatApp(App[None]):
    TITLE = "bpx"
    SUB_TITLE = "british_pixelart_llm"

    CSS = """
    #log { padding: 1 2; }
    #log Markdown { margin: 0 0 1 0; }
    #prompt { dock: bottom; margin: 0 1 1 1; }
    """

    BINDINGS = [
        ("escape", "cancel", "Stop generating"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.registry = Registry.load()
        self.model_name = "base"
        self.history: list[Message] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="log")
        yield Input(placeholder="Message bpx…", id="prompt")
        yield Footer()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        await self._append("**You**", text)
        self.history.append(Message("user", text))
        self.generate()

    async def _append(self, heading: str, body: str) -> Markdown:
        widget = Markdown(f"{heading}\n\n{body}")
        await self.query_one("#log", VerticalScroll).mount(widget)
        widget.scroll_visible()
        return widget

    @work(exclusive=True)
    async def generate(self) -> None:
        spec = self.registry.get(self.model_name)
        client = client_for(spec)
        bubble = await self._append(f"**{self.model_name}**", "…")
        log = self.query_one("#log", VerticalScroll)
        acc = ""
        try:
            async for delta in client.stream(self.history):
                acc += delta
                await bubble.update(f"**{self.model_name}**\n\n{acc}")
                log.scroll_end(animate=False)
        except CancelledError:
            acc += "\n\n_[stopped]_"
            raise
        finally:
            self.history.append(Message("assistant", acc))

    def action_cancel(self) -> None:
        self.workers.cancel_all()
