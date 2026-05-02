"""Base class for all JARVIS tools."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict


class Tool(ABC):
    """Every tool must expose a name, description, parameters schema, and async run()."""

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        ...
