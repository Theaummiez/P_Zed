"""
Two-tier memory system:

1. SQLite  — full conversation history (structured, persistent).
2. ChromaDB — semantic vector search over past turns (for relevant recall).

On every user turn:
  • The turn is written to SQLite.
  • The user message + assistant response are embedded and stored in ChromaDB.

On every agent invocation:
  • Recent N turns are loaded from SQLite (in-context history).
  • Top-K semantically similar past turns are retrieved from ChromaDB and
    injected as "memory context" into the system prompt.
  • Every summary_every_n turns, older turns are summarised by the LLM and
    compressed so the context stays small.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ChromaDB is optional — fall back gracefully if not installed
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False
    logger.warning("chromadb not installed — semantic memory disabled.")


# Optional sentence-transformers for richer embeddings
# Falls back to Ollama embeddings via the LLM client
_SENTENCE_TRANSFORMERS = False
try:
    from sentence_transformers import SentenceTransformer  # type: ignore
    _SENTENCE_TRANSFORMERS = True
except ImportError:
    pass


class MemoryStore:
    """
    Unified memory backend.  All blocking DB calls are run in a thread
    executor so they don't block the asyncio event loop.
    """

    def __init__(self, cfg, llm_client=None):
        self.cfg = cfg
        self.llm = llm_client  # used for embeddings if no local model

        # ── SQLite
        db_path = Path(cfg.memory.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_db()

        # ── ChromaDB
        self._chroma_collection = None
        if _CHROMA_AVAILABLE:
            try:
                chroma_path = Path(cfg.memory.chroma_path)
                chroma_path.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(
                    path=str(chroma_path),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                self._chroma_collection = client.get_or_create_collection(
                    name="jarvis_memory",
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("ChromaDB semantic memory ready.")
            except Exception as e:
                logger.warning("ChromaDB init failed: %s", e)

        # ── Local embedding model (all-MiniLM-L6-v2, ~80 MB)
        self._embed_model = None
        if _SENTENCE_TRANSFORMERS:
            try:
                self._embed_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Local sentence-transformer embeddings ready.")
            except Exception as e:
                logger.warning("SentenceTransformer failed: %s", e)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        cur = self._db.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS turns (
                id          TEXT PRIMARY KEY,
                ts          TEXT NOT NULL,
                user_msg    TEXT NOT NULL,
                assistant   TEXT NOT NULL,
                model       TEXT
            );
            CREATE TABLE IF NOT EXISTS summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                content     TEXT NOT NULL,
                turn_count  INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_turns_ts ON turns(ts);
        """)
        self._db.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def save_turn(
        self,
        user_msg: str,
        assistant_msg: str,
        model: str = "",
    ) -> None:
        turn_id = str(uuid.uuid4())
        ts = datetime.utcnow().isoformat()

        # SQLite write (thread-safe)
        await asyncio.get_event_loop().run_in_executor(
            None,
            self._sqlite_insert,
            turn_id, ts, user_msg, assistant_msg, model,
        )

        # Vector store write
        if self._chroma_collection is not None:
            combined = f"User: {user_msg}\nAssistant: {assistant_msg}"
            embedding = await self._embed(combined)
            if embedding:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._chroma_upsert,
                    turn_id, combined, embedding,
                    {"ts": ts, "user": user_msg[:200]},
                )

        # Maybe summarise older turns
        await self._maybe_summarise()

    def _sqlite_insert(self, tid, ts, user, assistant, model) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO turns VALUES (?,?,?,?,?)",
            (tid, ts, user, assistant, model),
        )
        self._db.commit()

    def _chroma_upsert(self, tid, doc, embedding, meta) -> None:
        self._chroma_collection.upsert(
            ids=[tid],
            documents=[doc],
            embeddings=[embedding],
            metadatas=[meta],
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_recent_turns(self, n: Optional[int] = None) -> List[Tuple[str, str]]:
        n = n or self.cfg.memory.recent_turns
        rows = await asyncio.get_event_loop().run_in_executor(
            None, self._sqlite_recent, n
        )
        return rows

    def _sqlite_recent(self, n: int) -> List[Tuple[str, str]]:
        cur = self._db.execute(
            "SELECT user_msg, assistant FROM turns ORDER BY ts DESC LIMIT ?", (n,)
        )
        rows = cur.fetchall()
        return list(reversed(rows))  # chronological order

    async def retrieve_context(self, query: str) -> str:
        """Return a formatted string of relevant memories for the system prompt."""
        parts: List[str] = []

        # Recent conversation summary if available
        summary = await self._get_latest_summary()
        if summary:
            parts.append(f"[Conversation summary]\n{summary}")

        # Semantic search
        if self._chroma_collection is not None:
            embedding = await self._embed(query)
            if embedding:
                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._chroma_collection.query(
                            query_embeddings=[embedding],
                            n_results=min(self.cfg.memory.semantic_top_k,
                                          self._chroma_collection.count()),
                        )
                    )
                    docs = results.get("documents", [[]])[0]
                    if docs:
                        parts.append("[Relevant past context]\n" + "\n---\n".join(docs[:3]))
                except Exception as e:
                    logger.debug("Chroma query error: %s", e)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Summarisation
    # ------------------------------------------------------------------

    async def _maybe_summarise(self) -> None:
        n = self.cfg.memory.summary_every_n
        if not self.llm:
            return
        count = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        )
        last_sum_count = await asyncio.get_event_loop().run_in_executor(
            None, self._last_summary_turn_count
        )
        if count - last_sum_count >= n:
            await self._summarise_turns(last_sum_count, count)

    def _last_summary_turn_count(self) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(turn_count),0) FROM summaries"
        ).fetchone()
        return row[0] if row else 0

    async def _summarise_turns(self, from_count: int, to_count: int) -> None:
        rows = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._db.execute(
                "SELECT user_msg, assistant FROM turns ORDER BY ts LIMIT ? OFFSET ?",
                (to_count - from_count, from_count)
            ).fetchall()
        )
        if not rows:
            return
        conversation = "\n".join(
            f"User: {r[0]}\nAssistant: {r[1]}" for r in rows
        )
        prompt = [
            {"role": "system", "content": "Summarise the following conversation concisely, preserving key facts about the user's preferences, goals, and important decisions."},
            {"role": "user", "content": conversation},
        ]
        try:
            summary = await self.llm.chat(prompt)
            ts = datetime.utcnow().isoformat()
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: (
                    self._db.execute(
                        "INSERT INTO summaries(ts, content, turn_count) VALUES(?,?,?)",
                        (ts, summary, to_count)
                    ),
                    self._db.commit()
                )
            )
            logger.info("Summarised turns %d-%d.", from_count, to_count)
        except Exception as e:
            logger.warning("Summarisation failed: %s", e)

    async def _get_latest_summary(self) -> Optional[str]:
        row = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._db.execute(
                "SELECT content FROM summaries ORDER BY id DESC LIMIT 1"
            ).fetchone()
        )
        return row[0] if row else None

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def _embed(self, text: str) -> Optional[List[float]]:
        if self._embed_model:
            try:
                return self._embed_model.encode(text).tolist()
            except Exception:
                pass
        if self.llm:
            try:
                return await self.llm.embed(text)
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # Stats / introspection
    # ------------------------------------------------------------------

    def turn_count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM turns").fetchone()[0]

    def close(self) -> None:
        self._db.close()
