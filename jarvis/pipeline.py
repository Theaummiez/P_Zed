"""Orchestration: memory, optional multi-agent delegation, rolling summary."""

from __future__ import annotations

import json
import re
from typing import Any

from jarvis.config import Settings
from jarvis.memory import (
    MemoryState,
    append_message,
    export_recent_for_summary,
    load_state,
    mark_summary_checkpoint,
    parse_summary_json,
    set_summary,
)
from jarvis.ollama import chat, chat_message
from jarvis.workspace import OLLAMA_TOOLS, run_tool


COORDINATOR_SYSTEM = """You are a local AI assistant (Jarvis-style): precise, helpful, concise unless asked for depth.
You run on the user's machine; be practical about limits and suggest concrete steps.
If the user speaks another language, reply in that language."""

FILE_TOOLS_HINT = """You have tools to access files ONLY inside the workspace folder (project root). You cannot read or write outside it.
Use paths relative to that root (e.g. docs/note.md). To create notes, use workspace_write_markdown with a path ending in .md .
When listing, start from relative_path \"\" for the project root."""


ANALYST_SYSTEM = """You are an analytical sub-agent. Break down problems, consider edge cases, and give structured reasoning.
Be concise but rigorous. No fluff."""

WRITER_SYSTEM = """You are a writing sub-agent. Produce clear, well-organized text (markdown when helpful)."""

CLASSIFIER_SYSTEM = """You route user requests. Reply with JSON only, no markdown:
{"delegate":"none"|"analyst"|"writer","reason":"short"}
Use analyst for math, debugging, multi-step logic, or careful analysis.
Use writer for long-form drafting, emails, documentation.
Use none for chit-chat, facts, or short answers."""


def _workspace_root_line(settings: Settings) -> str:
    try:
        root = settings.workspace_root.resolve()
    except OSError:
        root = settings.workspace_root
    return f"Workspace root (sandbox): {root}"


def _parse_tool_calls(msg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw = msg.get("tool_calls") or []
    out: list[tuple[str, dict[str, Any]]] = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            fn = tc
        name = fn.get("name")
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        if name:
            out.append((str(name), args))
    return out


async def run_agent_with_tools(
    settings: Settings,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.7,
    num_ctx: int = 4096,
) -> str:
    """Agent loop with Ollama tool calling; filesystem limited to workspace_root."""
    if not settings.workspace_tools:
        # Plain chat (messages must be str-compatible for older chat())
        simple: list[dict[str, Any]] = []
        for m in messages:
            simple.append({k: m[k] for k in m if k in ("role", "content")})
        return await chat(
            settings.ollama_host,
            settings.model,
            simple,
            temperature=temperature,
            num_ctx=num_ctx,
        )

    root = settings.workspace_root
    rounds = 0
    working = [dict(m) for m in messages]

    while rounds < settings.tool_rounds_max:
        rounds += 1
        msg = await chat_message(
            settings.ollama_host,
            settings.model,
            working,
            temperature=temperature,
            num_ctx=num_ctx,
            tools=OLLAMA_TOOLS,
        )
        tool_calls = _parse_tool_calls(msg)
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        working.append(assistant_msg)

        raw_tc = msg.get("tool_calls") or []
        if raw_tc and not tool_calls:
            working.append(
                {
                    "role": "tool",
                    "tool_name": "workspace",
                    "content": '{"error":"tool_calls present but could not parse arguments"}',
                }
            )
            continue

        if not tool_calls:
            text = (msg.get("content") or "").strip()
            return text if text else "(No text response.)"

        for name, args in tool_calls:
            result = run_tool(root, name, args)
            working.append({"role": "tool", "tool_name": name, "content": result})

    return "Stopped: too many tool rounds (increase JARVIS_TOOL_ROUNDS_MAX if needed)."


async def _maybe_delegate(
    settings: Settings,
    user_text: str,
    memory_excerpt: str,
) -> str | None:
    """Returns specialist reply or None to handle with coordinator only."""
    if not settings.multi_agent:
        return None
    router_messages = [
        {"role": "system", "content": CLASSIFIER_SYSTEM},
        {
            "role": "user",
            "content": f"Context (memory excerpt):\n{memory_excerpt[:2000]}\n\nUser:\n{user_text}",
        },
    ]
    raw = await chat(
        settings.ollama_host,
        settings.model,
        router_messages,
        temperature=0.2,
        num_ctx=2048,
    )
    try:
        # strip markdown code fences if any
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```\w*\n?", "", clean)
            clean = re.sub(r"\n?```$", "", clean)
        data = json.loads(clean)
        delegate = data.get("delegate", "none")
    except (json.JSONDecodeError, TypeError):
        return None

    if delegate not in ("analyst", "writer"):
        return None

    sys = ANALYST_SYSTEM if delegate == "analyst" else WRITER_SYSTEM
    specialist_messages: list[dict[str, Any]] = [
        {"role": "system", "content": sys},
        {"role": "system", "content": _workspace_root_line(settings)},
        {"role": "system", "content": FILE_TOOLS_HINT},
        {
            "role": "user",
            "content": f"Memory context:\n{memory_excerpt[:3000]}\n\nTask:\n{user_text}",
        },
    ]
    return await run_agent_with_tools(
        settings,
        specialist_messages,
        temperature=0.5,
        num_ctx=4096,
    )


async def refresh_summary(settings: Settings, memory_path, prev_summary: str) -> str:
    chunk = export_recent_for_summary(memory_path, settings.summary_every + 4)
    summary_model = settings.summary_model or settings.model
    prompt = f"""Update the conversation summary for future sessions.
Previous summary (may be empty):
---
{prev_summary}
---
Recent dialogue:
---
{chunk}
---
Respond with JSON only: {{"summary": "<=400 words, facts, preferences, ongoing topics>"}}"""

    messages = [
        {"role": "system", "content": "You compress dialogue into durable memory. Be factual; omit chit-chat."},
        {"role": "user", "content": prompt},
    ]
    out = await chat(
        settings.ollama_host,
        summary_model,
        messages,
        temperature=0.2,
        num_ctx=2048,
    )
    return parse_summary_json(out)


async def run_turn(
    settings: Settings,
    user_text: str,
    *,
    messages_since_summary: int,
) -> tuple[str, MemoryState, bool]:
    """
    Returns assistant reply, updated memory view, and whether summary was refreshed.
    """
    path = settings.memory_path
    state = load_state(path, settings.recent_turns)
    memory_excerpt = ""
    if state.summary:
        memory_excerpt += f"Long-term summary:\n{state.summary}\n\n"
    if state.messages:
        memory_excerpt += "Recent conversation:\n"
        for m in state.messages[-settings.recent_turns * 2 :]:
            memory_excerpt += f"{m['role'].upper()}: {m['content']}\n"

    delegated = await _maybe_delegate(settings, user_text, memory_excerpt)
    if delegated is not None:
        assistant_content = delegated
    else:
        messages_list: list[dict[str, Any]] = [
            {"role": "system", "content": COORDINATOR_SYSTEM},
            {"role": "system", "content": _workspace_root_line(settings)},
            {"role": "system", "content": FILE_TOOLS_HINT},
        ]
        if state.summary:
            messages_list.append(
                {
                    "role": "system",
                    "content": f"Known context from earlier sessions:\n{state.summary}",
                }
            )
        for m in state.messages:
            messages_list.append(dict(m))
        messages_list.append({"role": "user", "content": user_text})

        assistant_content = await run_agent_with_tools(
            settings,
            messages_list,
            temperature=0.7,
            num_ctx=4096,
        )

    append_message(path, "user", user_text)
    append_message(path, "assistant", assistant_content)

    summary_refreshed = False
    new_count = messages_since_summary + 2
    if new_count >= settings.summary_every:
        new_summary = await refresh_summary(settings, path, state.summary)
        set_summary(path, new_summary)
        mark_summary_checkpoint(path)
        summary_refreshed = True
        new_state = load_state(path, settings.recent_turns)
        return assistant_content, new_state, summary_refreshed

    new_state = load_state(path, settings.recent_turns)
    return assistant_content, new_state, summary_refreshed
