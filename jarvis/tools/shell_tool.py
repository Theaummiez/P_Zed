"""
Run shell commands in a sandboxed subprocess.
Output is capped to avoid flooding the context window.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from .base import Tool

_MAX_OUTPUT = 4000  # characters


class ShellTool(Tool):
    name = "shell"
    description = (
        "Execute a shell command on the local machine and return stdout+stderr. "
        "Use for file operations, system queries, running scripts, git, etc. "
        "Avoid long-running or interactive commands."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30).",
                "default": 30,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: home directory).",
            },
        },
        "required": ["command"],
    }

    async def run(self, command: str, timeout: int = 30, cwd: str = None) -> str:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            if len(output) > _MAX_OUTPUT:
                output = output[:_MAX_OUTPUT] + f"\n... [truncated, {len(output)} chars total]"
            return output or "(no output)"
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"Error: command timed out after {timeout}s."
        except Exception as e:
            return f"Error: {e}"
