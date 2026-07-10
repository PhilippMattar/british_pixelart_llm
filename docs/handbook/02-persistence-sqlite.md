# 02 — Persistence: SQLite schema + migrations

## Goal

A durable, inspectable store for projects, conversations, and messages so chats survive
restarts (start/stop/resume, full scrollback) — with a versioned schema that can evolve
across the project without breaking saved data.

## Why it exists

R3/R4 require resuming chats and restoring history, which needs storage. PLAN.md §3 locks
the decision: stdlib `sqlite3`, a `schema_version` table, and a tiny migration runner **from
day one** — because a schema change mid-project with no migration path silently corrupts or
orphans saved chats. Building the runner up front (even with a single migration) means later
additions like the `memories` table (Phase 3) are a one-function change, not a rewrite.

## What was built

- `src/bpx/store.py`:
  - `Store` — a synchronous wrapper over one `sqlite3` connection (`row_factory = Row`,
    `PRAGMA foreign_keys = ON`). CRUD for conversations and messages, plus `set_model`,
    `set_title`, `touch`, `delete_conversation`.
  - `MIGRATIONS` — an ordered list of functions; `_migrate()` reads the current version from
    `schema_version` and applies the pending ones, each wrapped in one transaction with its
    version bump. `_migration_001` creates `projects / conversations / messages` + indexes.
  - `default_db_path()` — `platformdirs.user_data_dir("bpx")/bpx.db`, overridable via `$BPX_DB`.
  - `Conversation` / `StoredMessage` frozen dataclasses returned to callers (no raw rows leak).
- `tests/test_store.py` — fresh-DB migration, idempotent reopen, CRUD roundtrip, cascade
  delete, partial (`complete=0`) survival across reopen, default-project creation.

## Core concepts

- **Migration runner** — schema evolution as data: `version` integer + ordered upgrade
  functions. Applying `MIGRATIONS[current:]` in transactions makes upgrades idempotent and
  crash-safe. Never edit a shipped migration; append a new one.
- **Transactions via `with conn:`** — the connection context manager commits on success and
  rolls back on error. Statements are issued individually (not `executescript`, which
  auto-commits) so a migration and its version bump are atomic.
- **Foreign keys + `ON DELETE CASCADE`** — deleting a conversation removes its messages in the
  DB, not in app code. SQLite enforces this only with `PRAGMA foreign_keys = ON` per connection.
- **Partial messages** — an assistant row is written with `complete=0` and updated as it
  streams; a cancelled reply keeps `complete=0` and is restored verbatim, which is what makes
  "stop then resume" honest (PLAN.md §9).

## Resources

- Python `sqlite3` — <https://docs.python.org/3/library/sqlite3.html>
- sqlite3 transaction control — <https://docs.python.org/3/library/sqlite3.html#transaction-control>
- SQLite foreign keys — <https://www.sqlite.org/foreignkeys.html>
- Schema-migration pattern (concept) — <https://martinfowler.com/articles/evodb.html>
- platformdirs — <https://platformdirs.readthedocs.io/>

## Gotchas

- `PRAGMA foreign_keys = ON` is **per connection** and a no-op inside a transaction — set it
  right after `connect()`, before any `with conn:` block.
- `executescript()` commits the current transaction before running; that's why migrations use
  individual `execute()` calls to stay atomic with the version bump.
- ISO-8601 UTC timestamps sort lexicographically, so `ORDER BY updated_at DESC` gives correct
  most-recent-first ordering without date parsing — but only because every timestamp uses the
  same `+00:00` offset. Don't mix local time in.
- `$BPX_DB` must point somewhere writable; tests use `tmp_path`. The default user-data dir is
  created on open (`mkdir parents=True`).
