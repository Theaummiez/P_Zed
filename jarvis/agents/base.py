"""Base class and registry for specialized agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from jarvis.core.llm import LLM

log = logging.getLogger(__name__)

_AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


class BaseAgent(ABC):
    """Every agent receives the shared LLM handle and a task description."""

    name: str = "base"
    description: str = "Abstract base agent"

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    @abstractmethod
    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        """Execute the agent's task and return a textual result."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name") and cls.name != "base":
            _AGENT_REGISTRY[cls.name] = cls


def get_agent(name: str, llm: LLM) -> BaseAgent:
    if name not in _AGENT_REGISTRY:
        raise KeyError(f"Unknown agent: {name!r}. Available: {list(_AGENT_REGISTRY)}")
    return _AGENT_REGISTRY[name](llm)


def list_agents() -> list[dict[str, str]]:
    return [{"name": n, "description": cls.description} for n, cls in _AGENT_REGISTRY.items()]
