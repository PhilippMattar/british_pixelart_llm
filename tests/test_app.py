from textual.widgets import Input

from bpx.app import ChatApp


async def test_app_composes_core_widgets() -> None:
    app = ChatApp()
    async with app.run_test() as pilot:
        assert app.query_one("#prompt", Input) is not None
        assert app.query_one("#log") is not None
        assert app.model_name == "base"
        await pilot.pause()


async def test_empty_submit_adds_nothing() -> None:
    app = ChatApp()
    async with app.run_test():
        prompt = app.query_one("#prompt", Input)
        prompt.value = "   "
        await prompt.action_submit()
        assert app.history == []
