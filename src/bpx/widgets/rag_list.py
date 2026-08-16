"""RagList — a modal to view and delete ingested RAG documents (Elective 1, §10).

Opened by `/rag`. Lists the documents indexed for the project; selecting one (Enter) deletes it
(and its chunks, via the FK cascade) through the supplied callback. Esc closes.
"""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static

from ..store import RagDocument


class RagList(ModalScreen[None]):
    DEFAULT_CSS = """
    RagList { align: center middle; }
    RagList > #rag {
        width: 70;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    RagList #rag-title { text-style: bold; padding: 0 0 1 0; }
    RagList #rag-hint { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(self, documents: list[RagDocument], on_delete: Callable[[int], None]) -> None:
        super().__init__()
        self._documents = documents
        self._on_delete = on_delete
        self._ids = [d.id for d in documents]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="rag"):
            yield Label(f"RAG documents · {len(self._documents)}", id="rag-title")
            if self._documents:
                yield ListView(*(ListItem(Label(d.title)) for d in self._documents))
                yield Static("Enter deletes the highlighted document · Esc closes", id="rag-hint")
            else:
                yield Static("No documents yet — add one with /rag add <path>.", id="rag-hint")

    def on_mount(self) -> None:
        if self._documents:
            self.query_one(ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        event.stop()
        index = event.list_view.index
        if index is None:
            return
        self._on_delete(self._ids.pop(index))
        event.item.remove()
        self.query_one("#rag-title", Label).update(f"RAG documents · {len(self._ids)}")

    def action_close(self) -> None:
        self.dismiss(None)
