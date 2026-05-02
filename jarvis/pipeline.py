"""Orchestration: memory, optional multi-agent delegation, rolling summary."""

from __future__ import annotations

import json
import re

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
from jarvis.ollama import chat


COORDINATOR_SYSTEM = """You are a local AI assistant (Jarvis-style): precise, helpful, concise unless asked for depth.
You run on the user's machine; be practical about limits and suggest concrete steps.
If the user speaks another language, reply in that language."""

ANALYST_SYSTEM = """You are an analytical sub-agent. Break down problems, consider edge cases, and give structured reasoning.
Be concise but rigorous. No fluff."""

WRITER_SYSTEM = """You are a writing sub-agent. Produce clear, well-organized text (markdown when helpful)."""

CLASSIFIER_SYSTEM = """You route user requests. Reply with JSON only, no markdown:
{"delegate":"none"|"analyst"|"writer","reason":"short"}
Use analyst for math, debugging, multi-step logic, or careful analysis.
Use writer for long-form drafting, emails, documentation.
Use none for chit-chat, facts, or short answers."""


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
    specialist_messages = [
        {"role": "system", "content": sys},
        {
            "role": "user",
            "content": f"Memory context:\n{memory_excerpt[:3000]}\n\nTask:\n{user_text}",
        },
    ]
    return await chat(
        settings.ollama_host,
        settings.model,
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
        messages: list[dict[str, str]] = [
            {"role": "system", "content": COORDINATOR_SYSTEM},
        ]
        if state.summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Known context from earlier sessions:\n{state.summary}",
                }
            )
        for m in state.messages:
            messages.append(m)
        messages.append({"role": "user", "content": user_text})

        assistant_content = await chat(
            settings.ollama_host,
            settings.model,
            messages,
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
