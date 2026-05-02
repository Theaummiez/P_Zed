"""Sandboxed file access under a single workspace root (no path escape)."""

from __future__ import annotations

import json
import os
from pathlib import Path

READ_MAX_BYTES = 512 * 1024
LIST_MAX_ENTRIES = 400
WRITE_MAX_BYTES = 2 * 1024 * 1024


class WorkspaceError(ValueError):
    pass


def _safe_relative(rel: str) -> Path:
    if not rel or not isinstance(rel, str):
        return Path()
    p = Path(rel.strip())
    if p.is_absolute():
        raise WorkspaceError("paths must be relative to the workspace root")
    parts = p.parts
    if ".." in parts:
        raise WorkspaceError("path must not contain '..'")
    return p


def resolve_under_root(root: Path, relative: str) -> Path:
    root = root.resolve()
    rel = _safe_relative(relative)
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise WorkspaceError("path escapes workspace sandbox") from e
    return candidate


def list_workspace(root: Path, relative_dir: str = "", *, recursive: bool = False) -> str:
    """List files under relative_dir (default root). One level unless recursive."""
    base = resolve_under_root(root, relative_dir)
    if not base.exists():
        return json.dumps({"error": "path does not exist", "path": relative_dir})
    if not base.is_dir():
        return json.dumps({"error": "not a directory", "path": relative_dir})

    entries: list[dict[str, str]] = []
    if recursive:
        count = 0
        for dirpath, dirnames, filenames in os.walk(base, topdown=True):
            # skip descending into hidden dirs
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith("."):
                    continue
                fp = Path(dirpath) / name
                try:
                    rel = fp.relative_to(root)
                except ValueError:
                    continue
                entries.append({"path": str(rel).replace("\\", "/"), "type": "file"})
                count += 1
                if count >= LIST_MAX_ENTRIES:
                    break
            if count >= LIST_MAX_ENTRIES:
                break
    else:
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                rel = child.relative_to(root)
            except ValueError:
                continue
            t = "dir" if child.is_dir() else "file"
            entries.append({"path": str(rel).replace("\\", "/"), "type": t})

    return json.dumps({"root": str(root), "entries": entries}, ensure_ascii=False)


def read_workspace_file(root: Path, relative_path: str) -> str:
    path = resolve_under_root(root, relative_path)
    if not path.is_file():
        return json.dumps({"error": "not a file or missing", "path": relative_path})
    size = path.stat().st_size
    if size > READ_MAX_BYTES:
        return json.dumps(
            {
                "error": "file too large",
                "path": relative_path,
                "max_bytes": READ_MAX_BYTES,
                "size": size,
            }
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    return json.dumps({"path": relative_path, "content": text}, ensure_ascii=False)


def write_workspace_markdown(root: Path, relative_path: str, content: str) -> str:
    if not isinstance(content, str):
        content = str(content)
    if len(content.encode("utf-8")) > WRITE_MAX_BYTES:
        return json.dumps({"error": "content too large", "max_bytes": WRITE_MAX_BYTES})
    rel_norm = relative_path.strip().replace("\\", "/")
    if not rel_norm.lower().endswith(".md"):
        return json.dumps({"error": "only .md files can be created or overwritten", "path": relative_path})
    path = resolve_under_root(root, rel_norm)
    if path.exists() and not path.is_file():
        return json.dumps({"error": "path exists and is not a file", "path": relative_path})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return json.dumps({"ok": True, "path": rel_norm, "bytes": len(content.encode("utf-8"))})


OLLAMA_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": "List files and folders inside the workspace sandbox. Paths are relative to project root; cannot escape.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Directory relative to workspace (empty string = root).",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list files recursively (capped); if false, one level only.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read_file",
            "description": "Read a text file under the workspace (utf-8).",
            "parameters": {
                "type": "object",
                "required": ["relative_path"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write_markdown",
            "description": "Create or overwrite a Markdown (.md) file under the workspace. Prefer paths under Docs/ for notes you create (e.g. Docs/meeting-notes.md or Docs/2026/jan/plan.md); intermediate folders are created automatically.",
            "parameters": {
                "type": "object",
                "required": ["relative_path", "content"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Target path ending in .md, relative to workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full Markdown body to write.",
                    },
                },
            },
        },
    },
]


def run_tool(root: Path, name: str, arguments: dict | str | None) -> str:
    args = arguments
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}

    try:
        if name == "workspace_list":
            rel = args.get("relative_path") or args.get("path") or ""
            rec = bool(args.get("recursive", False))
            return list_workspace(root, str(rel), recursive=rec)
        if name == "workspace_read_file":
            rp = args.get("relative_path") or args.get("path")
            if not rp:
                return json.dumps({"error": "missing relative_path"})
            return read_workspace_file(root, str(rp))
        if name == "workspace_write_markdown":
            rp = args.get("relative_path") or args.get("path")
            content = args.get("content", "")
            if not rp:
                return json.dumps({"error": "missing relative_path"})
            return write_workspace_markdown(root, str(rp), str(content))
    except WorkspaceError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool {name}"})
