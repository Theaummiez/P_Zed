"""
Build the complete tool registry, wiring dependencies.
"""

from __future__ import annotations

from typing import Dict, Any

from .shell_tool import ShellTool
from .file_tool import FileTool
from .web_tool import WebSearchTool, WebFetchTool
from .code_tool import CodeRunnerTool
from .memory_tool import MemoryTool
from .agent_tool import SpawnAgentsTool


def build_tools(memory_store, orchestrator) -> Dict[str, Any]:
    memory_tool = MemoryTool(memory_store)
    spawn_tool = SpawnAgentsTool(orchestrator)

    tools = {
        "shell": ShellTool(),
        "file": FileTool(),
        "web_search": WebSearchTool(),
        "web_fetch": WebFetchTool(),
        "run_python": CodeRunnerTool(),
        "memory": memory_tool,
        "spawn_agents": spawn_tool,
    }
    return tools
