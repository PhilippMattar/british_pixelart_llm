# 01 — Textual TUI: layout, widgets, events, conversation sidebar

## Goal

The interactive shell of the app: a two-pane layout — a conversation **sidebar** (list,
newest first) beside the chat log + input — with create / switch / remove conversations
(R4), each resuming with full scrollback (R3), driven by slash commands and keybindings.

## Why it exists

R2 (cross-platform UI) and R3/R4 (visible history, scroll, start/stop/resume, switch
between conversations) need a real UI, not a REPL. Textual gives a cross-platform terminal
UI with layout, focus, and events; PLAN.md §9 fixes the Claude-Code-inspired look (sidebar,
footer keybindings, slash commands). Persistence (Ch. 02) supplies the data the sidebar lists.

## What was built

- `src/bpx/app.py` — `ChatApp(App)`:
  - `compose()` yields `Header` · `Horizontal(ListView#sidebar, Vertical#main)` · `Footer`,
    where `#main` stacks the `VerticalScroll#log`, the `WaitingIndicator`, and the `Input`.
  - `_refresh_sidebar()` rebuilds the `ListView` from `store.list_conversations` and
    re-highlights the active row; `on_list_view_selected` loads the picked conversation.
  - `action_new_conversation` / `action_delete_conversation` (Ctrl+N and `/new` `/delete`);
    delete selects the next chat, or creates a fresh one so there's never zero.
  - `_load_conversation` rebuilds the log from stored messages and updates the Header badge.
- `src/bpx/widgets/model_picker.py` — a `ModalScreen` overlay (Ch. 03) that calls
  `event.stop()` so its selection doesn't reach the sidebar handler.

## Core concepts

- **compose + containers** — the UI is a tree yielded by `compose()`. `Horizontal` / `Vertical`
  arrange children; `with Horizontal(): ...` nests them. Widgets get `id`s for querying/CSS.
- **Textual CSS & `fr` units** — `width: 32` fixes the sidebar; `width: 1fr` / `height: 1fr`
  lets `#main` and `#log` absorb the remaining space so the input sits at the bottom.
- **Messages & handlers** — widgets post messages that bubble up; the app handles them by
  convention-named methods (`on_input_submitted`, `on_list_view_selected`). Bubbling means a
  modal's `ListView.Selected` would reach the app too — guard by `event.list_view.id` and/or
  `event.stop()`.
- **`ListView.index` vs `Selected`** — setting `.index` only *highlights* (emits `Highlighted`),
  so re-highlighting the active row during a refresh doesn't trigger a reload; only an explicit
  selection (Enter/click) emits `Selected`.
- **Workers** — streaming runs in an `@work(exclusive=True)` async worker so the UI stays live
  and Esc can cancel it (Ch. 00).

## Resources

- Textual tutorial — <https://textual.textualize.io/tutorial/>
- Layout guide — <https://textual.textualize.io/guide/layout/>
- Textual CSS — <https://textual.textualize.io/guide/CSS/>
- Events & messages — <https://textual.textualize.io/guide/events/>
- ListView widget — <https://textual.textualize.io/widgets/list_view/>
- Testing (`run_test`, `Pilot`) — <https://textual.textualize.io/guide/testing/>

## Gotchas

- A `ListView.Selected` message bubbles to the app even from a modal's own list — always scope
  the app handler (`if event.list_view.id != "sidebar": return`) or `event.stop()` in the modal.
- Rebuilding the sidebar on every message is fine at these counts, but re-highlighting must use
  `.index` (not a selection) or you get a reload loop.
- Textual apps need a TTY; drive them headlessly in tests with `App.run_test()` + `Pilot`, and
  remember `await prompt.action_submit()` only *queues* the event — `await pilot.pause()` before
  asserting so the handler (and any worker it starts) actually runs.
- `Static.update()` is synchronous, but `Markdown.update()` returns an awaitable — don't `await`
  the wrong one.
