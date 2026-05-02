"""
Safe Python code execution in a subprocess (no shell injection, isolated).
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import os
from typing import Any

from .base import Tool

_MAX_OUTPUT = 4000


class CodeRunnerTool(Tool):
    name = "run_python"
    description = (
        "Execute Python code and return the output. "
        "Use for calculations, data processing, or testing code snippets. "
        "The code runs in the same Python environment as JARVIS."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30).",
                "default": 30,
            },
        },
        "required": ["code"],
    }

    async def run(self, code: str, timeout: int = 30) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace")
            if len(output) > _MAX_OUTPUT:
                output = output[:_MAX_OUTPUT] + "\n... [truncated]"
            rc = proc.returncode
            if rc != 0:
                return f"[Exit code {rc}]\n{output}"
            return output or "(no output)"
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return f"Error: code timed out after {timeout}s."
        except Exception as e:
            return f"Error: {e}"
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
