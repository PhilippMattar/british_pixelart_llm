# 07 — Keyword routing & persona switching

## Goal

Overlay the British or Scottish persona on top of a conversation's **base model** when the
user's message uses that dialect, and revert to the base when it doesn't — so a persona is a
per-message reaction, not a sticky mode. A manual `/model` picks the base (routing stays on) or
pins a persona (routing off). Switches to a persona show a toast; reverting is silent.

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
- `models.toml` — `british` / `scottish` persona entries (`is_persona = true`) now point at the
  trained `bpx-british` / `bpx-scottish`; the standard `qwen` entry is `qwen3:8b`.
- `store.py` — migration 003 adds `conversations.auto_switch` (default on); migration 004 adds
  `conversations.base_model` (default `qwen`), the non-persona model routing reverts to. Plus
  `set_auto_switch` / `set_base_model`.
- `src/bpx/app.py` — `_maybe_auto_switch(text)` runs before generation: unless pinned, a lexicon
  hit overlays that persona (toast), and **no hit reverts to `base_model`** (silent). New
  conversations start on `DEFAULT_MODEL` ("qwen"), never the last conversation's persona.
  `_switch_model` branches: a **persona** pins (`auto_switch = False`); a **base** model sets
  `base_model` and keeps routing on.
- `src/bpx/widgets/keyword_help.py` — a read-only `KeywordHelp` modal listing every trigger word
  per persona, opened by **Ctrl+K** or `/keywords` (`keywords.lexicons()` exposes the words).
  The lexicons are impossible to memorise, so this is the in-app lookup.
- Tests: router unit (dialects, `checkmate`/`whiskey`/place-name false positives, ambiguity,
  `lexicons()`), app integration (overlay + revert-to-base, persona pin, new-conversation reset,
  keyword-help modal), store.

## Core concepts

- **Word boundaries beat substrings** — `\bmate\b` fires on "mate" but not "checkmate";
  `\bwhisky\b` matches the Scottish spelling and skips "whiskey". A single compiled
  alternation per persona (`re.IGNORECASE`) keeps detection O(n) in the message length.
- **Persona as an overlay on a base** — a conversation has a persisted `base_model`; the router
  swaps in a persona on a keyword hit and swaps back on a miss. This keeps the persona a
  reaction to *this* message, and "back to normal" means back to the base the user last chose
  (their `gemma`, not always `qwen`), not wherever the last message left it.
- **Pinning as persisted state** — a manual *persona* choice sets `auto_switch = False` (per row,
  survives restarts) so routing stops; a manual *base* choice leaves it on. The router reads the
  flag before firing.
- **Toast, not transcript** — a switch is a transient toast, not a stored message. History stays
  honest anyway: every assistant row records the `model_name` that produced it, so scrollback
  still shows which voice answered each turn without cluttering the chat.
- **Curation is the hard part** — coverage is easy; avoiding false positives (`ken`/`bonnie`
  as names, place names, common words) is what makes auto-switch feel intentional.

## Resources

- Python `re` (regex, `\b`, `re.IGNORECASE`) — <https://docs.python.org/3/library/re.html>
- Regex word boundaries — <https://www.regular-expressions.info/wordboundaries.html>
- Textual notifications (toasts) — <https://textual.textualize.io/guide/actions/#notifications>

## Gotchas

- **Routing now flips both ways** — because a keyword-free message reverts to `base_model`, a
  persona lasts exactly as long as the dialect does. Keep the lexicons tight: an over-eager
  match (or miss) now causes a visible switch *and* a switch-back, not just an escalation.
- Migration `ALTER TABLE … ADD COLUMN` statements (003 `auto_switch`, 004 `base_model`) are
  guarded (checks `PRAGMA table_info`) so the re-apply in the migration-002 test doesn't fail on
  a duplicate column.
- **`base_model` must never be a persona.** Only `_switch_model`'s base branch writes it, and
  only for `is_persona = false` models — otherwise a revert could target a persona and the
  overlay/base distinction collapses. New conversations default it to `qwen`.
- Any leftover `event` rows from the old logging behaviour still render in old conversations'
  scrollback (they're filtered from the prompt); new switches don't create them.
