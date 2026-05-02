"""Minimal Ollama HTTP chat client."""

from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


async def chat(
    host: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.7,
    num_ctx: int = 4096,
    timeout: float = 300.0,
    tools: list[dict[str, Any]] | None = None,
) -> str:
    msg = await chat_message(
        host,
        model,
        messages,
        temperature=temperature,
        num_ctx=num_ctx,
        timeout=timeout,
        tools=tools,
    )
    content = msg.get("content")
    if content is None and not msg.get("tool_calls"):
        raise OllamaError(f"Unexpected Ollama response message: {msg!r}")
    return (content or "").strip()


async def chat_message(
    host: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.7,
    num_ctx: int = 4096,
    timeout: float = 300.0,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Raw assistant message dict (content, tool_calls, role)."""
    url = host.rstrip("/") + "/api/chat"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
    if r.status_code >= 400:
        raise OllamaError(f"Ollama error {r.status_code}: {r.text[:500]}")
    data = r.json()
    msg = data.get("message") or {}
    if not isinstance(msg, dict):
        raise OllamaError(f"Unexpected Ollama response: {data!r}")
    return msg


async def list_models(host: str, timeout: float = 10.0) -> list[str]:
    url = host.rstrip("/") + "/api/tags"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url)
    if r.status_code >= 400:
        raise OllamaError(f"Ollama tags error {r.status_code}: {r.text[:200]}")
    data = r.json()
    return [m["name"] for m in data.get("models", [])]
