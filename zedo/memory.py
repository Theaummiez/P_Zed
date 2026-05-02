"""SQLite-backed conversation memory with rolling summary for long-term context."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MemoryState:
    summary: str
    messages: list[dict[str, str]]  # {role, content}


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: Path) -> None:
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        conn.commit()


def get_meta(path: Path, key: str, default: str | None = None) -> str | None:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    return row["value"]


def set_meta(path: Path, key: str, value: str) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def max_message_id(path: Path) -> int:
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT MAX(id) AS m FROM messages").fetchone()
    m = row["m"] if row else None
    return int(m) if m is not None else 0


def messages_since_last_summary(path: Path) -> int:
    """How many rows in messages were added after the last summarization checkpoint."""
    init_db(path)
    raw = get_meta(path, "last_summarized_message_id", "0")
    try:
        last_id = int(raw or "0")
    except ValueError:
        last_id = 0
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE id > ?",
            (last_id,),
        ).fetchone()
    return int(row["c"]) if row else 0


def mark_summary_checkpoint(path: Path) -> None:
    """Call after refreshing summary; ties checkpoint to latest message id."""
    mid = max_message_id(path)
    set_meta(path, "last_summarized_message_id", str(mid))


def load_state(path: Path, recent_pair_limit: int) -> MemoryState:
    """Load rolling summary and last N user+assistant messages."""
    init_db(path)
    with _connect(path) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'summary'").fetchone()
        summary = row["value"] if row else ""

        # Fetch last messages (all roles), then trim to last `recent_pair_limit` * 2 roughly
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (recent_pair_limit * 2 + 4,),
        ).fetchall()
    msgs: list[dict[str, str]] = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    return MemoryState(summary=summary, messages=msgs)


def append_message(path: Path, role: str, content: str) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO messages (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, time.time()),
        )
        conn.commit()


def set_summary(path: Path, text: str) -> None:
    init_db(path)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('summary', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (text,),
        )
        conn.commit()


def export_recent_for_summary(path: Path, last_n: int) -> str:
    """Plaintext of last N messages for summarization."""
    init_db(path)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (last_n,),
        ).fetchall()
    lines: list[str] = []
    for r in reversed(rows):
        role = r["role"].upper()
        lines.append(f"{role}: {r['content']}")
    return "\n\n".join(lines)


def parse_summary_json(text: str) -> str:
    """If model returns JSON {summary: ...}, unwrap."""
    t = text.strip()
    if t.startswith("{") and "summary" in t:
        try:
            data = json.loads(t)
            s = data.get("summary")
            if isinstance(s, str):
                return s.strip()
        except json.JSONDecodeError:
            pass
    return t
