"""Global configuration for Jarvis."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def _default_data_dir() -> Path:
    return Path(os.environ.get("JARVIS_DATA_DIR", Path.home() / ".jarvis"))


class ModelConfig(BaseModel):
    """Ollama model configuration."""

    name: str = Field(default_factory=lambda: os.environ.get("JARVIS_MODEL", "qwen3:4b"))
    temperature: float = 0.7
    context_length: int = 8192
    fallback: str = "phi4-mini"


class MemoryConfig(BaseModel):
    """Persistent memory / learning configuration."""

    db_path: Path = Field(default_factory=lambda: _default_data_dir() / "memory.db")
    max_history_per_session: int = 200
    learning_enabled: bool = True


class AgentConfig(BaseModel):
    """Multi-agent orchestration settings."""

    max_concurrent: int = 4
    default_timeout: float = 120.0


class JarvisConfig(BaseModel):
    """Top-level configuration."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    agents: AgentConfig = Field(default_factory=AgentConfig)
    data_dir: Path = Field(default_factory=_default_data_dir)
    system_prompt: str = (
        "You are Jarvis, a highly capable local AI assistant. "
        "You are precise, efficient, and always helpful. "
        "You remember past interactions and continuously improve your answers. "
        "When a task is complex, you can delegate sub-tasks to specialized agents. "
        "Be concise unless the user asks for detail."
    )

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory.db_path.parent.mkdir(parents=True, exist_ok=True)
