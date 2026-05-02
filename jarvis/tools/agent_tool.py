"""
Tool that lets JARVIS spawn multiple sub-agents for parallel task execution.
"""

from __future__ import annotations

import json
from typing import Any, List, Dict

from .base import Tool


class SpawnAgentsTool(Tool):
    name = "spawn_agents"
    description = (
        "Spawn multiple specialised sub-agents to handle tasks in parallel. "
        "Pass a list of task descriptions; each runs independently and returns "
        "its result. Ideal for research, multi-step analysis, or parallel work."
    )
    parameters = {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["id", "description"],
                },
                "description": "List of tasks for sub-agents.",
            },
            "context": {
                "type": "string",
                "description": "Shared context/background for all sub-agents.",
                "default": "",
            },
        },
        "required": ["tasks"],
    }

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator

    async def run(
        self,
        tasks: List[Dict[str, str]],
        context: str = "",
    ) -> str:
        sub_tasks = await self.orchestrator.run_tasks(tasks, context=context)
        return self.orchestrator.format_results(sub_tasks)
