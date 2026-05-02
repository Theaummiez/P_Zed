"""
Tool that lets the agent explicitly save or retrieve memories.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import Tool


class MemoryTool(Tool):
    name = "memory"
    description = (
        "Explicitly save a note or retrieve memories. "
        "Actions: 'save' (store a fact), 'search' (semantic search over memory), "
        "'stats' (show memory stats)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "search", "stats"],
            },
            "content": {
                "type": "string",
                "description": "Note content for 'save', or query for 'search'.",
            },
        },
        "required": ["action"],
    }

    def __init__(self, memory_store):
        self.memory = memory_store

    async def run(self, action: str, content: Optional[str] = None) -> str:
        if action == "save":
            if not content:
                return "Error: content required for save."
            await self.memory.save_turn(
                user_msg=f"[Manual note] {content}",
                assistant_msg="Noted.",
            )
            return f"Saved to memory: {content}"

        elif action == "search":
            if not content:
                return "Error: content required for search."
            ctx = await self.memory.retrieve_context(content)
            return ctx or "No relevant memories found."

        elif action == "stats":
            count = self.memory.turn_count()
            return f"Memory contains {count} conversation turns."

        return f"Unknown action: {action}"
