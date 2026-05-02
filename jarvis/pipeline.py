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
from jarvis.workspace import (
    ALLOWED_WRITE_EXTENSIONS,
    OLLAMA_TOOLS,
    normalize_workspace_relative,
    run_tool,
    write_workspace_file,
)


COORDINATOR_SYSTEM = """You are a local AI assistant (Jarvis-style): precise, helpful, concise unless asked for depth.
You run on the user's machine; be practical about limits and suggest concrete steps.
If the user speaks another language, reply in that language."""

FILE_TOOLS_HINT = """You have tools to access files ONLY inside the workspace folder (project root). You cannot read or write outside it.

CRITICAL: To create a file you MUST use the workspace tools (native tool_calls). Writing prose or JSON-looking examples in your answer does NOT create files unless the tools actually run.

Do NOT claim a file was created until tools have run successfully.

Use workspace_write_file to create files. Allowed types: .md .txt .html .csv .tsv .json .xml .css .docx .pdf (plain text body; PDF/DOCX are generated from text). Prefer Docs/ for user documents (e.g. Docs/export/page.html, Docs/data/posts.csv).

When listing, use relative_path \"\" for project root or \"Docs\" for the docs area."""


ANALYST_SYSTEM = """You are an analytical sub-agent. Break down problems, consider edge cases, and give structured reasoning.
Be concise but rigorous. No fluff."""

WRITER_SYSTEM = """You are a writing sub-agent. Produce clear, well-organized text (markdown when helpful)."""

CLASSIFIER_SYSTEM = """You route user requests. Reply with JSON only, no markdown:
{"delegate":"none"|"analyst"|"writer","reason":"short"}
Use analyst for math, debugging, multi-step logic, or careful analysis.
Use writer for long-form drafting, emails, documentation.
Use none for chit-chat, facts, or short answers.
Use writer when the user asks to create or save a file or document in the workspace."""


def _user_intends_workspace_write(user_text: str) -> bool:
    t = user_text.lower()
    if any(ext in t for ext in (".md", ".pdf", ".docx", ".csv", ".html", ".htm", ".json", ".xml", ".txt", ".css")):
        return True
    if "markdown" in t:
        return True
    if "docs/" in t or "docs\\" in t:
        return True
    if any(k in t for k in ("crée", "créer", "creer", "create", "fichier", "file", "enregistr", "sauve")):
        return True
    return False


def _hint_extension(user_text: str) -> str | None:
    """Guess extension from user message."""
    t = user_text.lower()
    if ".pdf" in t or " pdf" in t:
        return ".pdf"
    if ".docx" in t or " word" in t:
        return ".docx"
    if ".csv" in t:
        return ".csv"
    if ".html" in t or ".htm" in t:
        return ".html"
    if ".json" in t:
        return ".json"
    if ".xml" in t:
        return ".xml"
    if ".txt" in t:
        return ".txt"
    if ".css" in t:
        return ".css"
    return None


def _extract_target_file_path(user_text: str, assistant_reply: str) -> str | None:
    """Guess relative path from messages (Docs/... with allowed extension)."""
    exts = "|".join(sorted(re.escape(e[1:]) for e in ALLOWED_WRITE_EXTENSIONS))
    path_core = r"(?:Docs|docs)/[a-zA-Z0-9_./\-]+"
    pat_full = re.compile(rf"(?i)\b{path_core}\.(?:{exts})\b")
    for src in (user_text, assistant_reply):
        m = pat_full.search(src)
        if m:
            return normalize_workspace_relative(m.group(0))
    loose = re.compile(rf"(?i)\b{path_core}\.(?:{exts})(?=\s|$|[`'\",.;)])")
    for src in (user_text, assistant_reply):
        for match in loose.finditer(src):
            return normalize_workspace_relative(match.group(0))
    m = re.search(r"(?i)\b(Docs|docs)/[a-zA-Z0-9_./\-]+", user_text)
    if m:
        p = m.group(0).rstrip("/").strip()
        ext = _hint_extension(user_text) or ".md"
        slug = "note"
        tl = user_text.lower()
        if "cardio" in tl:
            slug = "seance-cardio"
        elif "sport" in tl:
            slug = "seance"
        if not any(p.lower().endswith(e) for e in ALLOWED_WRITE_EXTENSIONS):
            p = f"{p}/{slug}{ext}"
        return normalize_workspace_relative(p)
    return None


def _default_target_path(user_text: str) -> str:
    ext = _hint_extension(user_text) or ".md"
    tl = user_text.lower()
    if "cardio" in tl or "sport" in tl:
        return normalize_workspace_relative(f"Docs/Sport/note{ext}")
    return f"Docs/notes/from-chat{ext}"


def _extract_saveable_body(assistant_reply: str) -> str | None:
    """Body for fallback save: fenced code block (md, html, csv, json, ...) or markdown-looking reply."""
    m = re.search(
        r"```(?:markdown|md|html|htm|csv|json|xml|txt|css|pdf|docx)?\s*\n?([\s\S]*?)```",
        assistant_reply,
        re.IGNORECASE,
    )
    if m:
        body = m.group(1).strip()
        return body if body else None
    t = assistant_reply.strip()
    if len(t) >= 25 and t.lstrip().startswith("#"):
        return t
    return None


def _fallback_write_if_needed(
    settings: Settings,
    user_text: str,
    assistant_reply: str,
    wrote_any_tool: bool,
) -> tuple[str, list[str]]:
    """If the model hallucinated a file write, persist content using workspace_write_file rules."""
    if not settings.workspace_tools or wrote_any_tool:
        return assistant_reply, []
    if not _user_intends_workspace_write(user_text):
        return assistant_reply, []
    body = _extract_saveable_body(assistant_reply)
    if not body or len(body) < 10:
        return assistant_reply, []
    rel = _extract_target_file_path(user_text, assistant_reply)
    if not rel:
        rel = _default_target_path(user_text)
    root = settings.workspace_root
    raw = write_workspace_file(root, rel, body)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return assistant_reply, []
    if not data.get("ok"):
        note = f"\n\n_(Écriture automatique impossible : {data.get('error', raw)})_"
        return assistant_reply + note, []
    abs_path = (root / rel).resolve()
    banner = (
        f"\n\n---\n_Fichier enregistré automatiquement (le modèle n’avait pas appelé les outils)_ : "
        f"`{rel}` → `{abs_path}`\n---"
    )
    return assistant_reply + banner, [rel]


def _workspace_root_line(settings: Settings) -> str:
    try:
        root = settings.workspace_root.resolve()
    except OSError:
        root = settings.workspace_root
    return f"Workspace root (sandbox): {root}"


KNOWN_WORKSPACE_TOOLS = frozenset(
    {"workspace_list", "workspace_read_file", "workspace_write_file", "workspace_write_markdown"}
)


def _extract_balanced_json_objects(text: str) -> list[dict[str, Any]]:
    """Parse top-level {...} JSON objects from text (handles models that print JSON instead of tool_calls)."""
    out: list[dict[str, Any]] = []
    depth = 0
    start = -1
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start : i + 1]
                try:
                    data = json.loads(chunk)
                    if isinstance(data, dict):
                        out.append(data)
                except json.JSONDecodeError:
                    pass
                start = -1
    return out


def _tool_calls_from_embedded_json(content: str) -> list[tuple[str, dict[str, Any]]]:
    """When the model prints {\"name\":\"workspace_...\",\"arguments\":{...}} in prose, execute it."""
    found: list[tuple[str, dict[str, Any]]] = []
    for data in _extract_balanced_json_objects(content):
        name = data.get("name")
        if name not in KNOWN_WORKSPACE_TOOLS:
            continue
        args = data.get("arguments")
        if not isinstance(args, dict):
            args = {}
        found.append((str(name), args))
    return found


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
) -> tuple[str, bool]:
    """Agent loop with Ollama tool calling; returns (reply text, whether a workspace write tool succeeded)."""
    if not settings.workspace_tools:
        # Plain chat (messages must be str-compatible for older chat())
        simple: list[dict[str, Any]] = []
        for m in messages:
            simple.append({k: m[k] for k in m if k in ("role", "content")})
        text = await chat(
            settings.ollama_host,
            settings.model,
            simple,
            temperature=temperature,
            num_ctx=num_ctx,
        )
        return text, False

    root = settings.workspace_root
    rounds = 0
    working = [dict(m) for m in messages]
    wrote_file_tool = False

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
        raw_content = msg.get("content") or ""
        tool_calls = _parse_tool_calls(msg)
        used_embedded = False
        if not tool_calls:
            embedded = _tool_calls_from_embedded_json(raw_content)
            if embedded:
                tool_calls = embedded
                used_embedded = True

        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": "(Executing workspace tools…)" if used_embedded else raw_content,
        }
        if msg.get("tool_calls"):
            assistant_msg["tool_calls"] = msg["tool_calls"]
        working.append(assistant_msg)

        raw_tc = msg.get("tool_calls") or []
        if raw_tc and not _parse_tool_calls(msg) and not used_embedded:
            working.append(
                {
                    "role": "tool",
                    "tool_name": "workspace",
                    "content": '{"error":"tool_calls present but could not parse arguments"}',
                }
            )
            continue

        if not tool_calls:
            text = raw_content.strip()
            return (text if text else "(No text response.)", wrote_file_tool)

        for name, args in tool_calls:
            result = run_tool(root, name, args)
            if name in ("workspace_write_markdown", "workspace_write_file"):
                try:
                    data = json.loads(result)
                    if isinstance(data, dict) and data.get("ok"):
                        wrote_file_tool = True
                except json.JSONDecodeError:
                    pass
            working.append({"role": "tool", "tool_name": name, "content": result})

    return "Stopped: too many tool rounds (increase JARVIS_TOOL_ROUNDS_MAX if needed).", wrote_file_tool


async def _maybe_delegate(
    settings: Settings,
    user_text: str,
    memory_excerpt: str,
) -> tuple[str | None, bool]:
    """Returns (specialist reply or None, whether a workspace write tool succeeded)."""
    if not settings.multi_agent:
        return None, False
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
        return None, False

    if delegate not in ("analyst", "writer"):
        return None, False

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
    text, wrote = await run_agent_with_tools(
        settings,
        specialist_messages,
        temperature=0.5,
        num_ctx=4096,
    )
    return text, wrote


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

    delegated, delegated_wrote = await _maybe_delegate(settings, user_text, memory_excerpt)
    if delegated is not None:
        assistant_content, _paths = _fallback_write_if_needed(
            settings, user_text, delegated, delegated_wrote
        )
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

        agent_reply, agent_wrote = await run_agent_with_tools(
            settings,
            messages_list,
            temperature=0.7,
            num_ctx=4096,
        )
        assistant_content, _paths = _fallback_write_if_needed(
            settings, user_text, agent_reply, agent_wrote
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
