"""Configuration via environment variables (see .env.example)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from jarvis.project_root import discover_project_root


def _default_workspace_root() -> Path:
    return discover_project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_host: str = Field(default="http://127.0.0.1:11434", description="Ollama API base URL")
    model: str = Field(
        default="qwen2.5:7b",
        description="Default model (use small instruct models for efficiency)",
    )
    summary_model: str | None = Field(
        default=None,
        description="If set, use this model for memory summaries (defaults to same as model)",
    )
    multi_agent: bool = Field(default=False, description="Enable coordinator + specialist agents")
    memory_path: Path = Field(default_factory=lambda: Path.home() / ".jarvis" / "memory.db")
    recent_turns: int = Field(default=12, ge=2, le=50, description="User/assistant pairs to load")
    summary_every: int = Field(
        default=8,
        ge=2,
        description="After this many new messages, refresh the rolling summary",
    )
    workspace_root: Path = Field(
        default_factory=_default_workspace_root,
        description="Sandbox root: only files under this path are readable/writable",
    )
    workspace_tools: bool = Field(
        default=True,
        description="Expose list/read/write-.md tools to the model (Ollama tool calling)",
    )
    tool_rounds_max: int = Field(default=16, ge=1, le=32, description="Max tool-call iterations per message")
    skills_enabled: bool = Field(
        default=True,
        description="Inject Markdown skills from workspace Skills/ into system context",
    )
    skills_dir: str = Field(default="Skills", description="Subdirectory of workspace_root for *.md skills")
    skills_max_chars: int = Field(
        default=16_000,
        ge=500,
        le=64_000,
        description="Max characters of injected skill text per message",
    )


def get_settings() -> Settings:
    return Settings()
