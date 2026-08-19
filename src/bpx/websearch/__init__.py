"""Agentic web search (Elective 2, PLAN.md §11).

Loop: search (ddgs) -> the model picks a URL -> fetch (httpx) + extract main text and in-page
links (trafilatura) -> the model decides: answer / follow an in-page link / new query. A fetch
budget bounds it; the result is a source-tagged context the answer cites. Entry point is the same
judge as §10 (see orchestrator.py).
"""
