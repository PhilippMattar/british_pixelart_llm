# 09 — Adaptive RAG

## Goal

Answer questions about the user's *own* documents. `/rag add <path>` ingests a txt/pdf; then a
lecture-faithful pipeline — **judge → rewrite → multiturn retrieval → summarize** — pulls the
relevant passages and the model answers **citing its sources**. Everything is local: embeddings
via Ollama, vectors in the one SQLite file, no external service.

## Why it exists

Elective 1 (PLAN.md §10) and the demo's real-world use case: drop in a course paper and query it.
It's also the shared control path — the same judge is where Elective 2 (web search, Ch. 10) plugs
in a third route.

## What was built

- `store.py` — migration 006 adds `rag_documents` and `rag_chunks` (embedding stored as a float32
  BLOB), plus `add_document` / `add_chunks` / `list_documents` / `delete_document` /
  `rag_chunks_for_search`.
- `src/bpx/rag/embed.py` — `Embedder` (Ollama `nomic-embed-text` via `/v1/embeddings`) and
  `to_blob` / `from_blob` for float32 (de)serialization.
- `src/bpx/rag/chunk.py` — `read_document` (pypdf for PDFs, UTF-8 otherwise) and `chunk_text`
  (~350-word overlapping windows ≈ 500 tokens).
- `src/bpx/rag/pipeline.py` — the orchestration: `ingest_document`, brute-force `cosine` +
  `retrieve`, and the control steps `library_summary`, `judge`, `rewrite`, `sufficient`,
  `summarize`, tied together by `build_context` (the ≤3-round loop → a source-tagged `RagResult`).
- `app.py` — `/rag add <path>` ingests in a background worker; `generate()` runs `build_context`
  before answering (spinner covers it), injects the source-tagged block as a system message, and
  appends the **Sources** legend to the reply. `/rag` opens the document modal.
- `src/bpx/widgets/rag_list.py` — the `RagList` modal (view/delete documents).
- Drag-and-drop: `drop_paths()` recognises when the prompt's text is actually a dropped file path
  (quotes, `file://` URLs, macOS backslash-escaped spaces) and routes it to `/rag` instead of
  sending it as a message — so dragging a PDF in and pressing Enter ingests it.

## Core concepts

- **Retrieval = embed + cosine.** Each chunk is embedded once at ingest; a query is embedded at
  ask-time and ranked against the stored vectors by cosine similarity. At this scale (a few docs)
  brute force over all chunks is milliseconds — no ANN index needed.
- **The judge must know the library.** A judge asked "does this need the docs?" is blind without
  knowing what the docs *are* — so `library_summary` feeds it each document's title + opening
  snippet. That's the difference between "How much honey?" routing to DIRECT (wrong) vs LOCAL.
- **Multiturn retrieval.** After retrieving, an LLM judges whether the passages are *sufficient*;
  if not, the query is rewritten (broadened) and retrieval repeats, up to `MAX_ROUNDS`. Chunks
  accumulate across rounds (deduped by id).
- **Summarize, then cite.** The summarizer compresses the hits into source-tagged bullets (`[1]`,
  `[2]`); the final answer is generated with that block as context and cites the same tags, and
  the app shows the legend. Grounded answers, checkable sources.
- **Control calls are non-thinking.** Judge/rewrite/sufficient/summarize all go through a
  `reasoning_effort="none"` client — four cheap calls, not four 40-second thinks.

## Resources

- nomic-embed-text — <https://ollama.com/library/nomic-embed-text>
- Ollama embeddings API — <https://github.com/ollama/ollama/blob/main/docs/api.md#generate-embeddings>
- sqlite-vec (the planned store) — <https://github.com/asg017/sqlite-vec>
- pypdf — <https://pypdf.readthedocs.io/en/stable/>
- RAG (original paper) — <https://arxiv.org/abs/2005.11401>
- Cosine similarity — <https://en.wikipedia.org/wiki/Cosine_similarity>

## Gotchas

- **sqlite-vec could not be used — a plan deviation (§10).** This Python's `sqlite3` was built
  without loadable-extension support (`enable_load_extension` is missing — the uv/
  python-build-standalone default), and the usual fix `pysqlite3-binary` has **no macOS wheel**.
  A native extension would also hurt the R1 `uvx` install everywhere. So vectors are float32
  BLOBs in a normal table and search is **brute-force cosine in Python** — same goals (local,
  single-file, uv-friendly), minus an ANN index we don't need at this scale.
- **A topic-blind judge routes everything to DIRECT.** Passing the document titles + opening
  snippets (`library_summary`) is what lets it recognise a doc question.
- **Small models emit malformed JSON / stray words** — the control steps parse leniently (`"LOCAL"
  in reply`, `"YES" in reply`) rather than demanding exact output, and every step falls back
  safely (judge→none, rewrite→original query, sufficient→True to stop the loop, summarize→raw
  tagged chunks).
- **RAG adds latency before the answer** (embed + up to ~4 control calls). It only runs when the
  project has documents, and the waiting spinner covers it; the whole pipeline is inside the
  `generate` worker so Esc still cancels it.
- **Embedding dimensions must stay consistent** — every chunk and query must come from the same
  model; `from_blob`/`cosine` assume equal length.
- **Chunk size approximates tokens by words** (~350 words ≈ 500 tokens) — fine for retrieval;
  swap in a real tokenizer if precision ever matters.
- **Terminal "drag-and-drop" is really a paste.** A TUI can't receive OS file-drop events; the
  emulator pastes the *path* into the input, so drag → path appears → Enter ingests. `drop_paths`
  only fires when the whole input resolves to real ingestable file(s), so a normal message that
  happens to mention a path is never hijacked.
