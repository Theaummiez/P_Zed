"""Configuration via environment variables (see .env.example)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_host: str = Field(default="http://127.0.0.1:11434", description="Ollama API base URL")
    model: str = Field(
        default="qwen2.5:3b",
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


def get_settings() -> Settings:
    return Settings()
