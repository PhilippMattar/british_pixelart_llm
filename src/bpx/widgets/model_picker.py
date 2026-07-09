"""ModelPicker — a small modal overlay listing registry models for `/model` (no arg).

Dismisses with the chosen model name, or None on Escape. See PLAN.md §4.2.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView


class ModelPicker(ModalScreen[str | None]):
    DEFAULT_CSS = """
    ModelPicker { align: center middle; }
    ModelPicker > #picker {
        width: 40;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1;
    }
    ModelPicker #picker-title { text-style: bold; padding: 0 0 1 0; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, names: list[str], current: str) -> None:
        super().__init__()
        self._names = names
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Label("Pick a model", id="picker-title")
            yield ListView(*(ListItem(Label(name)) for name in self._names))

    def on_mount(self) -> None:
        picker = self.query_one(ListView)
        picker.focus()
        if self._current in self._names:
            picker.index = self._names.index(self._current)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        self.dismiss(self._names[index] if index is not None else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
