# 07 — Keyword routing & persona switching

## Goal

Auto-switch the active model to the British or Scottish persona when the user's message
uses that dialect, while letting a manual `/model` pin a conversation and turn auto-switch
off. Every switch is logged into the chat so the history stays honest.

## Why it exists

The personas (R7) are only useful if they engage naturally. PLAN.md §8 specifies a keyword
router with curated word-boundary lexicons and the rule that **manual choice beats
auto-switch, per conversation**. This is the control path the electives' judge will later
generalise, so it's built now against the existing `/model` machinery — the persona *models*
themselves are placeholders until Phase-2 training lands.

## What was built

- `src/bpx/router/keywords.py` — two curated regex lexicons (british / scottish) and
  `detect(text) -> "british" | "scottish" | None`, returning the persona with strictly more
  hits (ties/none → `None`). `hits(text)` exposes the per-persona counts for tests.
- `models.toml` — `british` / `scottish` persona entries (`is_persona = true`), `model_id`
  pointing at `qwen3.5:4b` as a placeholder until `bpx-british` / `bpx-scottish` are trained.
- `store.py` — migration 003 adds `conversations.auto_switch` (default on), plus
  `set_auto_switch`. The `Conversation` row carries the flag.
- `src/bpx/app.py` — `_maybe_auto_switch(text)` runs before generation: if the conversation
  isn't pinned and a lexicon matches, it switches model, toasts, updates the badge, and
  writes an `event` row rendered as a centred note. `_switch_model` (manual `/model` and the
  picker) sets `auto_switch = False`. `event` rows are excluded from the LLM prompt.
- Tests: router unit (dialects, `checkmate`/`whiskey`/place-name false positives, ambiguity),
  app integration (auto-switch, manual pin disables it, plain text doesn't switch), store.

## Core concepts

- **Word boundaries beat substrings** — `\bmate\b` fires on "mate" but not "checkmate";
  `\bwhisky\b` matches the Scottish spelling and skips "whiskey". A single compiled
  alternation per persona (`re.IGNORECASE`) keeps detection O(n) in the message length.
- **Pinning as persisted state** — "manual choice disables auto-switch for that conversation"
  is a per-row boolean, so it survives restarts; the router reads it before firing.
- **Honest history** — switches are real, persisted `event` messages shown in scrollback, not
  ephemeral toasts; they're filtered out of the model prompt so they don't pollute context.
- **Curation is the hard part** — coverage is easy; avoiding false positives (`ken`/`bonnie`
  as names, place names, common words) is what makes auto-switch feel intentional.

## Resources

- Python `re` (regex, `\b`, `re.IGNORECASE`) — <https://docs.python.org/3/library/re.html>
- Regex word boundaries — <https://www.regular-expressions.info/wordboundaries.html>
- Textual notifications (toasts) — <https://textual.textualize.io/guide/actions/#notifications>

## Gotchas

- The persona `model_id`s are placeholders (`qwen3.5:4b`); until the LoRAs are trained the
  reply won't actually sound British/Scottish — only the routing/UX is real. Swap two lines
  in `models.toml` after Phase-2 export.
- `event` rows must be excluded from the prompt builder (`role in ("user", "assistant")`),
  or the model sees "auto-switched to scottish" as context.
- Migration 003's `ALTER TABLE … ADD COLUMN` is guarded (checks `PRAGMA table_info`) so the
  re-apply in the migration-002 test doesn't fail on a duplicate column.
- `detect` runs on every non-command message; keep the lexicons tight to avoid surprise
  switches mid-conversation. Auto-switch only *escalates* to a persona — it never flips back
  to `qwen` on its own (a manual `/model qwen` does that, and pins).
