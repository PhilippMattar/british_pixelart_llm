# 08 — Project memory

## Goal

Give the assistant memory that spans conversations: a background LLM extracts durable facts about
the user, stores them **per project**, and the top-k are injected into the system prompt of every
chat in that project — so what you told it in one conversation is known in the next. `/memory`
lists and deletes them.

## Why it exists

Requirement R6: "simple memory over groups of chats (Project-Folder style)". Conversations are
already grouped under a project (§9); memory is the cross-conversation recall layer on top. It's
also a demo beat: tell the assistant something in one chat, open another, and it remembers.

## What was built

- `store.py` — migration 005 adds the `memories` table (`project_id` FK, `content`), plus
  `add_memory` / `list_memories(project_id, limit)` / `delete_memory`. Inspectable, per-project.
- `src/bpx/memory.py` — the store- and app-agnostic core: `build_prompt` (extraction instruction
  + recent transcript + already-known facts), `parse_facts` (robust JSON-array parsing),
  `dedup_new` (drop already-known / within-batch duplicates), `extract_facts` (the async
  orchestration, returns `[]` on any failure), and `system_prompt` (facts → a neutral injection
  block, or `None`).
- `llm.py` — a non-streaming `complete()` for background use (wants the whole answer, not deltas).
- `app.py` — `_memory_prompt()` prepends the injection as a leading `system` message in
  `generate()`; `_maybe_extract_memory` fires the `extract_memory` **background worker** once
  every `MEMORY_EVERY` (4) messages; the worker uses a `reasoning_effort="none"` client and
  stores new facts. `/memory` opens the modal.
- `src/bpx/widgets/memory_list.py` — the `MemoryList` modal: view the facts, Enter deletes the
  highlighted one, Esc closes.

## Core concepts

- **LLM as a fact extractor.** No embeddings or vector store here — the model reads the transcript
  and returns a JSON array of short, durable facts. Simple, inspectable, good enough for R6 (the
  vector machinery arrives for RAG, Ch. 09).
- **System-prompt injection is model-agnostic.** Facts go in as a leading `system` message, so the
  standard model and the personas alike get them. A persona still speaks in character — its voice
  lives in the LoRA weights, not the prompt — so the block is kept factual and neutral.
- **Background, non-blocking, fail-silent.** Extraction runs in a Textual worker in its own group,
  so it never blocks or cancels your generation; `extract_facts` swallows all errors so a flaky
  extraction can never break a chat.
- **Dedup on a normalised key.** Case/punctuation-insensitive comparison stops the same fact
  piling up as you keep chatting; the extractor is also *told* what's already known.
- **Project scoping.** Memories are keyed on `project_id`, so they're shared across a project's
  conversations but not leaked between projects (the `/project` UI lands later; the key is here).

## Resources

- OpenAI chat roles (system/user/assistant) — <https://platform.openai.com/docs/guides/text-generation>
- Textual workers (background tasks) — <https://textual.textualize.io/guide/workers/>
- Textual `ModalScreen` — <https://textual.textualize.io/guide/screens/#modal-screens>
- SQLite foreign keys / `ON DELETE CASCADE` — <https://www.sqlite.org/foreignkeys.html>
- Memory in LLM apps (background/summary memory pattern) — <https://python.langchain.com/docs/versions/migrating_memory/>

## Gotchas

- **Small models emit malformed JSON.** `qwen3:8b` returned `[{"fact"}, {"fact"}]` (each string
  wrapped in braces — invalid JSON), so a strict `json.loads` found nothing. Fixed two ways: an
  exact-format example in the prompt, **and** a fallback in `parse_facts` that extracts every
  quoted string from the array when `json.loads` fails. Verify extraction against the real model,
  not just a fake that returns clean JSON.
- **Extract non-thinking.** The extractor forces `reasoning_effort="none"`: a thinking model would
  be slow for a background task and would wrap the JSON in reasoning. (Ch. 06.)
- **The array regex is greedy** (`\[.*\]`, first `[` to last `]`) so a fact containing a bracket
  doesn't truncate the match.
- **Cadence, not every turn.** Extracting on every message is wasteful and repetitive; `MEMORY_EVERY`
  throttles it, and dedup handles the overlap when it does run.
- **Migration 005 uses `CREATE TABLE IF NOT EXISTS`** so the migration-002 rewind test (which
  replays later migrations) doesn't fail on a duplicate table.
- **Injection is unconditional across models** — fine, but if a persona ever feels diluted, that's
  the first knob to check; keep the injected block short and neutral.
