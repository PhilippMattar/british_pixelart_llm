"""WaitingIndicator — a tiny "the model is working" animation.

Three dots chase clockwise around a 3x3 square while a reply is generating; the timer
runs on the event loop so it keeps moving even while the worker awaits the first token.
On Esc-cancel it freezes red ("Stopped"); on normal completion it hides. This is a
deliberately simple precursor to the Phase-4 persona pixel-art (PLAN.md §9, widgets).
"""

from __future__ import annotations

from textual.timer import Timer
from textual.widgets import Static

# The 8 perimeter cells of a 3x3 grid, clockwise from top-left. Centre (1,1) stays empty.
_CYCLE = [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2), (2, 1), (2, 0), (1, 0)]
_TICK = 0.12  # seconds per frame


class WaitingIndicator(Static):
    DEFAULT_CSS = """
    WaitingIndicator {
        height: auto;
        padding: 0 2;
        color: $accent;
    }
    WaitingIndicator.-idle { display: none; }
    WaitingIndicator.-stopped { color: $error; }
    """

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._timer: Timer | None = None
        self._frame = 0
        self.current_frame = ""  # last painted text (handy for tests/inspection)
        self.add_class("-idle")

    def start(self) -> None:
        """Show the indicator and begin animating."""
        self.remove_class("-idle", "-stopped")
        self._frame = 0
        self._paint("Generating…")
        if self._timer is None:
            self._timer = self.set_interval(_TICK, self._tick)
        self._timer.resume()

    def stop(self, *, cancelled: bool) -> None:
        """Freeze red on cancel (then auto-hide), or hide immediately on completion."""
        if self._timer is not None:
            self._timer.pause()
        if cancelled:
            self.add_class("-stopped")
            self._paint("Stopped (Esc)")
            self.set_timer(1.5, self._hide)
        else:
            self._hide()

    def _hide(self) -> None:
        self.add_class("-idle")
        self.remove_class("-stopped")

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(_CYCLE)
        self._paint("Generating…")

    def _paint(self, label: str) -> None:
        dots = {_CYCLE[(self._frame + i) % len(_CYCLE)] for i in range(3)}

        def cell(r: int, c: int) -> str:
            if (r, c) == (1, 1):
                return " "
            return "●" if (r, c) in dots else "·"

        rows = [" ".join(cell(r, c) for c in range(3)) for r in range(3)]
        rows[1] = f"{rows[1]}   {label}"
        self.current_frame = "\n".join(rows)
        self.update(self.current_frame)
