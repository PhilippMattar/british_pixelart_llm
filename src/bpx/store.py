"""SQLite persistence — projects, conversations, messages (PLAN.md §9, §3).

Stdlib `sqlite3` only. A `schema_version` table plus an ordered `MIGRATIONS` list run
pending migrations on open, so schema changes never break saved chats. The `memories`
table arrives in Phase 3 as migration 002 — the *runner* is what must exist from day one.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_dir

DEFAULT_PROJECT_NAME = "General"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_db_path() -> Path:
    """User data dir, or $BPX_DB override (tests and dev point this at a temp file)."""
    override = os.environ.get("BPX_DB")
    if override:
        return Path(override)
    return Path(user_data_dir("bpx")) / "bpx.db"


# --- migrations -----------------------------------------------------------------
# Each function upgrades the schema by exactly one version. Statements are issued
# individually (not via executescript, which auto-commits) so the whole migration
# plus its version bump runs inside one transaction.


def _migration_001(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE projects ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " name TEXT NOT NULL,"
        " created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE conversations ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,"
        " title TEXT NOT NULL,"
        " model_name TEXT NOT NULL,"
        " created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE messages ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,"
        " role TEXT NOT NULL,"
        " content TEXT NOT NULL,"
        " model_name TEXT,"
        " complete INTEGER NOT NULL DEFAULT 1,"
        " created_at TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX idx_messages_conversation ON messages(conversation_id)")
    conn.execute("CREATE INDEX idx_conversations_project ON conversations(project_id)")


# Ordered; MIGRATIONS[i] upgrades version i -> i+1.
MIGRATIONS = [_migration_001]


# --- row types ------------------------------------------------------------------


@dataclass(frozen=True)
class Conversation:
    id: int
    project_id: int
    title: str
    model_name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StoredMessage:
    id: int
    role: str
    content: str
    model_name: str | None
    complete: bool
    created_at: str


class Store:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, path: Path | str | None = None) -> "Store":
        path = path or default_db_path()
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        store = cls(conn)
        store._migrate()
        store._ensure_default_project()
        return store

    def close(self) -> None:
        self._conn.close()

    # -- migrations --
    def _migrate(self) -> None:
        conn = self._conn
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute("INSERT INTO schema_version (version) VALUES (0)")
                current = 0
            else:
                current = row["version"]
        for i in range(current, len(MIGRATIONS)):
            with conn:  # migration + version bump are one atomic transaction
                MIGRATIONS[i](conn)
                conn.execute("UPDATE schema_version SET version = ?", (i + 1,))

    @property
    def version(self) -> int:
        return self._conn.execute("SELECT version FROM schema_version").fetchone()["version"]

    # -- projects --
    def _ensure_default_project(self) -> None:
        row = self._conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        if row is None:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO projects (name, created_at) VALUES (?, ?)",
                    (DEFAULT_PROJECT_NAME, _now()),
                )

    def default_project_id(self) -> int:
        row = self._conn.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()
        return int(row["id"])

    # -- conversations --
    def create_conversation(
        self, project_id: int, model_name: str, title: str = "New conversation"
    ) -> int:
        now = _now()
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO conversations (project_id, title, model_name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (project_id, title, model_name, now, now),
            )
        return int(cur.lastrowid)

    def list_conversations(self, project_id: int) -> list[Conversation]:
        rows = self._conn.execute(
            "SELECT * FROM conversations WHERE project_id = ? ORDER BY updated_at DESC, id DESC",
            (project_id,),
        ).fetchall()
        return [self._conv(r) for r in rows]

    def get_conversation(self, conversation_id: int) -> Conversation | None:
        row = self._conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return self._conv(row) if row else None

    def set_title(self, conversation_id: int, title: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id)
            )

    def set_model(self, conversation_id: int, model_name: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET model_name = ? WHERE id = ?",
                (model_name, conversation_id),
            )

    def touch(self, conversation_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conversation_id)
            )

    def delete_conversation(self, conversation_id: int) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    # -- messages --
    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        model_name: str | None = None,
        complete: bool = True,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, model_name, complete, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, role, content, model_name, int(complete), _now()),
            )
        return int(cur.lastrowid)

    def update_message(self, message_id: int, content: str, complete: bool) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE messages SET content = ?, complete = ? WHERE id = ?",
                (content, int(complete), message_id),
            )

    def list_messages(self, conversation_id: int) -> list[StoredMessage]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ).fetchall()
        return [self._msg(r) for r in rows]

    # -- row mappers --
    @staticmethod
    def _conv(row: sqlite3.Row) -> Conversation:
        return Conversation(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            model_name=row["model_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _msg(row: sqlite3.Row) -> StoredMessage:
        return StoredMessage(
            id=row["id"],
            role=row["role"],
            content=row["content"],
            model_name=row["model_name"],
            complete=bool(row["complete"]),
            created_at=row["created_at"],
        )
