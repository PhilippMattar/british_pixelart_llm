"""WaitingIndicator — a tiny "the model is working" animation.

A 2x2 box of dots: three are lit and the single gap rotates clockwise, so the trio
appears to chase around the square. The timer runs on the event loop, so it keeps moving
even while the worker awaits the first token. On Esc-cancel it freezes red ("Stopped");
on normal completion it hides. A deliberately simple precursor to the Phase-4 persona
pixel-art (PLAN.md §9, widgets).
"""

from __future__ import annotations

from textual.timer import Timer
from textual.widgets import Static

# The 4 corners of a 2x2 box, clockwise from top-left. Each frame leaves one corner dark.
_CORNERS = [(0, 0), (0, 1), (1, 1), (1, 0)]
_TICK = 0.14  # seconds per frame


class WaitingIndicator(Static):
    DEFAULT_CSS = """
    WaitingIndicator {
        height: auto;
        padding: 0 1;
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
        self._frame = (self._frame + 1) % len(_CORNERS)
        self._paint("Generating…")

    def _paint(self, label: str) -> None:
        gap = _CORNERS[self._frame % len(_CORNERS)]

        def cell(r: int, c: int) -> str:
            return "·" if (r, c) == gap else "●"

        rows = ["".join(cell(r, c) for c in range(2)) for r in range(2)]
        rows[0] = f"{rows[0]} {label}"
        self.current_frame = "\n".join(rows)
        self.update(self.current_frame)
