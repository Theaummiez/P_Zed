"""
Thin async wrapper around the Ollama HTTP API.
Uses streaming for low time-to-first-token and supports both
chat (multi-turn) and generate (single-turn) endpoints.
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import AsyncIterator, Optional, List, Dict, Any

import httpx

from jarvis.config.settings import OllamaConfig

logger = logging.getLogger(__name__)


class OllamaClient:
    """Async client for the Ollama local inference server."""

    def __init__(self, cfg: OllamaConfig):
        self.cfg = cfg
        self._client = httpx.AsyncClient(
            base_url=cfg.host,
            timeout=httpx.Timeout(300.0, connect=10.0),
        )

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def _post_stream(self, path: str, payload: dict) -> AsyncIterator[dict]:
        async with self._client.stream("POST", path, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line:
                    yield json.loads(line)

    async def is_available(self) -> bool:
        try:
            r = await self._client.get("/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        r = await self._client.get("/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    async def pull_model(self, name: str) -> AsyncIterator[str]:
        """Stream pull progress lines."""
        async for chunk in self._post_stream("/api/pull", {"name": name, "stream": True}):
            status = chunk.get("status", "")
            if "total" in chunk:
                pct = int(chunk.get("completed", 0) / chunk["total"] * 100)
                yield f"{status} {pct}%"
            else:
                yield status

    # ------------------------------------------------------------------
    # Chat (multi-turn)
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from the model."""
        model = model or self.cfg.primary_model
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.cfg.keep_alive,
            "options": {
                "temperature": temperature if temperature is not None else self.cfg.temperature,
                "num_ctx": self.cfg.context_window,
            },
        }
        if stop:
            payload["options"]["stop"] = stop

        async for chunk in self._post_stream("/api/chat", payload):
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
            if chunk.get("done"):
                break

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        stop: Optional[List[str]] = None,
    ) -> str:
        """Return the full response as a single string."""
        parts: List[str] = []
        async for tok in self.chat_stream(messages, model=model,
                                          temperature=temperature, stop=stop):
            parts.append(tok)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        model = model or self.cfg.embedding_model
        r = await self._client.post(
            "/api/embeddings",
            json={"model": model, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()
