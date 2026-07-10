from textual.app import App, ComposeResult

from bpx.widgets.spinner import WaitingIndicator


class _Host(App):
    def compose(self) -> ComposeResult:
        yield WaitingIndicator(id="w")


async def test_indicator_starts_hidden_then_animates():
    app = _Host()
    async with app.run_test() as pilot:
        w = app.query_one("#w", WaitingIndicator)
        assert w.has_class("-idle")  # hidden when idle

        w.start()
        assert not w.has_class("-idle")  # visible while generating
        first = w.current_frame
        await pilot.pause(0.3)  # let a few ticks advance the frame
        assert w.current_frame != first  # animation moved


async def test_stop_completed_hides():
    app = _Host()
    async with app.run_test():
        w = app.query_one("#w", WaitingIndicator)
        w.start()
        w.stop(cancelled=False)
        assert w.has_class("-idle")


async def test_stop_cancelled_freezes_red():
    app = _Host()
    async with app.run_test():
        w = app.query_one("#w", WaitingIndicator)
        w.start()
        w.stop(cancelled=True)
        assert w.has_class("-stopped")
        assert "Stopped" in w.current_frame
        w.start()  # a new generation clears the stopped state
        assert not w.has_class("-stopped")
