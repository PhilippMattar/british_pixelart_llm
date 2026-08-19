# 10 — Agentic web search

## Goal

Answer questions that need live, external information. When the shared judge routes a query to
`web`, an agent **searches, reads pages, follows links it finds inside those pages, and re-searches
as needed** — within a fetch budget — then answers **citing the URLs** it used.

## Why it exists

Elective 2 (PLAN.md §11). The distinguishing requirement is going *further than the direct search
results* — traversing links found *within* fetched pages — which is what makes it "agentic" rather
than a one-shot search. It enters through the **same judge** as RAG (§10): one control path routes
no-retrieval / local-docs / web.

## What was built

- `src/bpx/websearch/search.py` — `web_search` (DuckDuckGo via `ddgs`) → `SearchResult`s.
- `src/bpx/websearch/fetch.py` — `fetch_page` (httpx + trafilatura): main text **and in-page
  links**, or `None` if the page can't be read (403, non-HTML, empty, timeout).
- `src/bpx/websearch/agent.py` — the loop: make a query → search → **decide** (ANSWER / FETCH a
  candidate / SEARCH again) → fetch (adding the page's links to the frontier) → repeat within
  `FETCH_BUDGET` → `summarize` into a source-tagged `WebResult`.
- `src/bpx/orchestrator.py` — the single **3-way judge** (`local` / `web` / `none`) and dispatch;
  `rag.build_context` was split so the judge lives here and `rag.build_local_context` just
  retrieves.
- `app.py` — `generate()` calls the orchestrator (web enabled by default), streams the answer, and
  appends the source legend; `/search <q>` forces web (skips the judge); `/web [on|off]` toggles
  auto-routing; step progress shows as toasts.

## Core concepts

- **The agent loop is a decide-act cycle.** Each turn the model sees what's been gathered and the
  candidate links, and picks one action. Reading a page's text *and* its links, then letting the
  model choose a link to follow, is the "traverse within pages" requirement — the frontier grows
  with links discovered inside fetched pages.
- **One judge, three routes.** RAG and web share `orchestrator.judge`; giving it the local library
  summary lets it tell "answer from the user's docs" from "look it up online" from "just answer".
- **Resilience is the feature, not an afterthought.** On a live run ~half of pages 403 (bot
  blocks) or extract empty (JS-only). Every fetch failure returns `None` and the loop tries the
  next candidate; the budget bounds the work; a blocked page never wedges it.
- **Ground + cite.** The summarizer compresses fetched pages into source-tagged bullets (`[1]`,
  `[2]`); the answer is generated from that and cites the same tags; the app lists the URLs.
- **Non-thinking control calls.** Query-making, each decision, and summarizing all use a
  `reasoning_effort="none"` client — otherwise a web question would stack up several 40-second
  thinks.

## Resources

- ddgs (DuckDuckGo search) — <https://github.com/deedy5/ddgs>
- httpx — <https://www.python-httpx.org/>
- trafilatura (main-content extraction) — <https://trafilatura.readthedocs.io/en/latest/>
- ReAct: reasoning + acting agents — <https://arxiv.org/abs/2210.03629>
- Bracketed search-agent patterns (overview) — <https://python.langchain.com/docs/tutorials/rag/>

## Gotchas

- **Most of the web bot-blocks a naive client.** A thin User-Agent gets 403'd; use a realistic
  browser UA, and still expect ~half of results to fail or be JS-only — hence the skip-and-continue
  design, not "fetch the top result and hope".
- **`ddgs` is synchronous** — call it via `asyncio.to_thread` so the search doesn't block the event
  loop (and the whole agent runs inside `generate`, so Esc still cancels it).
- **Web search is many round-trips** (a query call + up to ~6 decisions + fetches + a summarize),
  so it's slow — tens of seconds. Progress is surfaced as toasts and the spinner covers it; keep
  control calls non-thinking.
- **Auto-routing costs a judge call per message.** With web on, every message is judged (to decide
  web vs not). It's a cheap non-thinking call, but `/web off` disables it, and `/search` bypasses
  the judge entirely.
- **Be a polite client.** One fetch per URL, a timeout, `follow_redirects`, and a small budget —
  don't hammer sites. `ddgs` itself can rate-limit; `web_search` returns `[]` on failure and the
  agent falls back to answering directly.
