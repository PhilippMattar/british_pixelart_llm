"""MemoryList — a modal to view and delete project memories (R6, §9).

Opened by `/memory`. Lists the durable facts remembered for the project; selecting one (Enter)
deletes it via the supplied callback. Esc closes.
"""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ..store import Memory


class MemoryList(ModalScreen[None]):
    DEFAULT_CSS = """
    MemoryList { align: center middle; }
    MemoryList > #mem {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    MemoryList #mem-title { text-style: bold; padding: 0 0 1 0; }
    MemoryList #mem-hint { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, memories: list[Memory], on_delete: Callable[[int], None]) -> None:
        super().__init__()
        self._memories = memories
        self._on_delete = on_delete
        self._ids = [m.id for m in memories]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="mem"):
            yield Label(f"Project memory · {len(self._memories)} fact(s)", id="mem-title")
            if self._memories:
                yield ListView(*(ListItem(Label(m.content)) for m in self._memories))
                yield Static("Enter deletes the highlighted fact · Esc closes", id="mem-hint")
            else:
                yield Static("No memories yet — keep chatting and they'll appear.", id="mem-hint")

    def on_mount(self) -> None:
        if self._memories:
            self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        index = event.list_view.index
        if index is None:
            return
        self._on_delete(self._ids.pop(index))
        event.item.remove()
        self.query_one("#mem-title", Label).update(f"Project memory · {len(self._ids)} fact(s)")

    def action_close(self) -> None:
        self.dismiss(None)
