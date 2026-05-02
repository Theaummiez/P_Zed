"""
File read/write/list operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from .base import Tool

_MAX_READ = 8000


class FileTool(Tool):
    name = "file"
    description = (
        "Read, write, or list files on the local filesystem. "
        "Actions: 'read', 'write', 'append', 'list', 'exists', 'delete'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "append", "list", "exists", "delete"],
            },
            "path": {
                "type": "string",
                "description": "Absolute or relative file/directory path.",
            },
            "content": {
                "type": "string",
                "description": "Content for write/append actions.",
            },
        },
        "required": ["action", "path"],
    }

    async def run(
        self,
        action: str,
        path: str,
        content: Optional[str] = None,
    ) -> Any:
        p = Path(os.path.expanduser(path))
        try:
            if action == "read":
                if not p.exists():
                    return f"File not found: {path}"
                text = p.read_text(errors="replace")
                if len(text) > _MAX_READ:
                    text = text[:_MAX_READ] + f"\n... [truncated]"
                return text

            elif action == "write":
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content or "")
                return f"Written {len(content or '')} chars to {path}."

            elif action == "append":
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a") as f:
                    f.write(content or "")
                return f"Appended to {path}."

            elif action == "list":
                if not p.exists():
                    return f"Path not found: {path}"
                if p.is_file():
                    return str(p)
                entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
                lines = []
                for e in entries[:200]:
                    prefix = "📄" if e.is_file() else "📁"
                    lines.append(f"{prefix} {e.name}")
                return "\n".join(lines)

            elif action == "exists":
                return str(p.exists())

            elif action == "delete":
                if not p.exists():
                    return f"Not found: {path}"
                if p.is_file():
                    p.unlink()
                else:
                    import shutil
                    shutil.rmtree(p)
                return f"Deleted {path}."

            else:
                return f"Unknown action: {action}"
        except Exception as e:
            return f"Error ({action} {path}): {e}"
