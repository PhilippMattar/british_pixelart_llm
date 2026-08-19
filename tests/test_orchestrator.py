from bpx import orchestrator
from bpx.store import Store
from bpx.websearch.agent import WebResult


class _Judge:
    def __init__(self, word):
        self.word = word

    async def complete(self, messages):
        return self.word


async def test_judge_three_way():
    assert await orchestrator.judge(_Judge("LOCAL"), "q", [], "lib", web_enabled=True) == "local"
    assert await orchestrator.judge(_Judge("WEB"), "q", [], "lib", web_enabled=True) == "web"
    assert await orchestrator.judge(_Judge("DIRECT"), "q", [], "lib", web_enabled=True) == "none"
    # WEB downgrades to none when web is disabled
    assert await orchestrator.judge(_Judge("WEB"), "q", [], "lib", web_enabled=False) == "none"


async def _fake_web(client, query, history, on_status=None):
    return WebResult("web ctx", ["[1] https://u"])


async def test_force_web_skips_judge(tmp_path, monkeypatch):
    store = Store.open(tmp_path / "o.db")
    pid = store.default_project_id()
    monkeypatch.setattr(orchestrator.websearch, "build_web_context", _fake_web)
    # client/embedder unused on this path
    res = await orchestrator.build_context(
        None, None, store, pid, "q", [], web_enabled=True, force_route="web"
    )
    assert res.sources == ["[1] https://u"]
    store.close()


async def test_web_route_dispatches_to_agent(tmp_path, monkeypatch):
    store = Store.open(tmp_path / "o.db")
    pid = store.default_project_id()
    monkeypatch.setattr(orchestrator.websearch, "build_web_context", _fake_web)
    res = await orchestrator.build_context(_Judge("WEB"), None, store, pid, "q", [], web_enabled=True)
    assert res is not None and res.sources == ["[1] https://u"]
    store.close()


async def test_direct_and_no_docs_returns_none(tmp_path):
    store = Store.open(tmp_path / "o.db")
    pid = store.default_project_id()
    res = await orchestrator.build_context(_Judge("DIRECT"), None, store, pid, "q", [], web_enabled=True)
    assert res is None
    store.close()
