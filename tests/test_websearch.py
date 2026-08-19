from bpx.websearch import agent
from bpx.websearch.fetch import Page
from bpx.websearch.search import SearchResult


class _Client:
    """Fake control LLM: canned query/summary; scripted decisions consumed in order."""

    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def complete(self, messages):
        p = messages[0].content
        if "Search query:" in p:  # _make_query
            return "test query"
        if "Relevant notes:" in p:  # _summarize
            return "- a relevant fact [1]"
        return self._decisions.pop(0) if self._decisions else "ANSWER"  # _decide


def _search_one(*results):
    return lambda q, max_results=6: list(results)


async def test_agent_fetches_and_cites(monkeypatch):
    monkeypatch.setattr(agent, "web_search", _search_one(SearchResult("A", "https://a.com", "")))

    async def fake_fetch(url, max_chars=6000):
        return Page(url=url, text="apple " * 100, links=[])

    monkeypatch.setattr(agent, "fetch_page", fake_fetch)
    res = await agent.build_web_context(_Client(["FETCH 0", "ANSWER"]), "about apples?", [])
    assert res is not None
    assert res.sources == ["[1] https://a.com"]
    assert "[1]" in res.context


async def test_agent_follows_in_page_link(monkeypatch):
    pages = {
        "https://a.com": Page("https://a.com", "surface " * 100, [("Deeper", "https://deep.com")]),
        "https://deep.com": Page("https://deep.com", "the answer " * 100, []),
    }
    monkeypatch.setattr(agent, "web_search", _search_one(SearchResult("A", "https://a.com", "")))

    async def fake_fetch(url, max_chars=6000):
        return pages.get(url)

    monkeypatch.setattr(agent, "fetch_page", fake_fetch)
    # FETCH 0 (a.com) surfaces deep.com at index 1; FETCH 1 follows that in-page link.
    res = await agent.build_web_context(_Client(["FETCH 0", "FETCH 1", "ANSWER"]), "q", [])
    assert any("deep.com" in s for s in res.sources)


async def test_agent_skips_unfetchable_pages(monkeypatch):
    monkeypatch.setattr(
        agent,
        "web_search",
        _search_one(SearchResult("A", "https://blocked.com", ""), SearchResult("B", "https://ok.com", "")),
    )

    async def fake_fetch(url, max_chars=6000):
        return None if "blocked" in url else Page(url, "good " * 100, [])

    monkeypatch.setattr(agent, "fetch_page", fake_fetch)
    res = await agent.build_web_context(_Client(["FETCH 0", "FETCH 1", "ANSWER"]), "q", [])
    assert res.sources == ["[1] https://ok.com"]  # the 403'd page is dropped


async def test_agent_no_results_returns_none(monkeypatch):
    monkeypatch.setattr(agent, "web_search", lambda q, max_results=6: [])
    assert await agent.build_web_context(_Client([]), "q", []) is None
