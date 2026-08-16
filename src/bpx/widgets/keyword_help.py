"""KeywordHelp — a read-only modal listing the persona trigger words (§8).

The auto-switch lexicons are hard to memorise, so `/keywords` (or Ctrl+K) pops this up as a
lookup. Dismisses on Escape/Enter; it selects nothing.
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

# Optional flourish per persona; falls back to the capitalised name.
_LABELS = {"british": "🇬🇧 British", "scottish": "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scottish"}


class KeywordHelp(ModalScreen[None]):
    DEFAULT_CSS = """
    KeywordHelp { align: center middle; }
    KeywordHelp > #kw {
        width: 60;
        height: auto;
        max-height: 80%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    KeywordHelp #kw-title { text-style: bold; padding: 0 0 1 0; }
    KeywordHelp .kw-persona { text-style: bold; color: $accent; padding: 1 0 0 0; }
    KeywordHelp #kw-hint { color: $text-muted; padding: 1 0 0 0; }
    """

    BINDINGS = [("escape", "close", "Close"), ("enter", "close", "Close")]

    def __init__(self, lexicons: dict[str, list[str]]) -> None:
        super().__init__()
        self._lexicons = lexicons

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="kw"):
            yield Label("Persona trigger keywords", id="kw-title")
            for persona, words in self._lexicons.items():
                yield Static(_LABELS.get(persona, persona.capitalize()), classes="kw-persona")
                yield Static(", ".join(words))
            yield Static("Any of these switches the persona; a message with none reverts to your "
                         "base model.  Esc to close.", id="kw-hint")

    def on_key(self, event: events.Key) -> None:
        # Close on Enter too (BINDINGS' "enter" can be swallowed by focused widgets).
        if event.key == "enter":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)
