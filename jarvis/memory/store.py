"""SQLite-backed persistent memory for conversations and learned knowledge."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from jarvis.config import MemoryConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    timestamp   REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    topic       TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    source      TEXT,
    confidence  REAL    DEFAULT 1.0,
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER REFERENCES conversations(id),
    rating          INTEGER,
    comment         TEXT,
    created_at      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge(topic);
"""


class MemoryStore:
    """Persistent memory backed by a local SQLite database."""

    def __init__(self, config: MemoryConfig) -> None:
        self.config = config
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.config.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.open()
        assert self._conn is not None
        return self._conn

    # ── conversation persistence ──────────────────────────────────────

    def save_message(self, session_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO conversations (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (session_id, role, content, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_history(self, session_id: str, limit: int | None = None) -> list[dict]:
        limit = limit or self.config.max_history_per_session
        rows = self.conn.execute(
            "SELECT role, content FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_recent_sessions(self, n: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT session_id, MIN(timestamp) AS started, MAX(timestamp) AS ended, COUNT(*) AS msgs "
            "FROM conversations GROUP BY session_id ORDER BY ended DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── knowledge base ────────────────────────────────────────────────

    def store_knowledge(self, topic: str, content: str, source: str | None = None) -> int:
        now = time.time()
        existing = self.conn.execute(
            "SELECT id FROM knowledge WHERE topic = ?", (topic,)
        ).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE knowledge SET content = ?, source = ?, updated_at = ?, confidence = MIN(confidence + 0.1, 1.0) WHERE id = ?",
                (content, source, now, existing["id"]),
            )
            self.conn.commit()
            return existing["id"]
        cur = self.conn.execute(
            "INSERT INTO knowledge (topic, content, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (topic, content, source, now, now),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def search_knowledge(self, query: str, limit: int = 5) -> list[dict]:
        rows = self.conn.execute(
            "SELECT topic, content, confidence FROM knowledge WHERE topic LIKE ? OR content LIKE ? ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── feedback / self-improvement ───────────────────────────────────

    def save_feedback(self, conversation_id: int, rating: int, comment: str = "") -> None:
        self.conn.execute(
            "INSERT INTO feedback (conversation_id, rating, comment, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, rating, comment, time.time()),
        )
        self.conn.commit()

    def get_improvement_context(self) -> str:
        """Build a short summary of what the user liked / disliked to inject into the system prompt."""
        positives = self.conn.execute(
            "SELECT c.content FROM feedback f JOIN conversations c ON c.id = f.conversation_id WHERE f.rating >= 4 ORDER BY f.created_at DESC LIMIT 5"
        ).fetchall()
        negatives = self.conn.execute(
            "SELECT c.content, f.comment FROM feedback f JOIN conversations c ON c.id = f.conversation_id WHERE f.rating <= 2 ORDER BY f.created_at DESC LIMIT 5"
        ).fetchall()

        parts: list[str] = []
        if positives:
            parts.append("The user appreciated these past answers — emulate this style:\n" + "\n".join(f"- {r['content'][:120]}" for r in positives))
        if negatives:
            parts.append("The user disliked these past answers — avoid this style:\n" + "\n".join(f"- {r['content'][:120]} (feedback: {r['comment'][:60]})" for r in negatives))
        return "\n\n".join(parts)

    def get_stats(self) -> dict[str, Any]:
        total_msgs = self.conn.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
        total_sessions = self.conn.execute("SELECT COUNT(DISTINCT session_id) AS n FROM conversations").fetchone()["n"]
        knowledge_count = self.conn.execute("SELECT COUNT(*) AS n FROM knowledge").fetchone()["n"]
        return {
            "total_messages": total_msgs,
            "total_sessions": total_sessions,
            "knowledge_entries": knowledge_count,
        }
