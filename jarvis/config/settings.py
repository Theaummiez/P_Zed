"""
Global configuration — all tuneable values live here.
Override any value by setting the corresponding environment variable or by
editing ~/.jarvis/config.yaml (auto-created on first run).
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

CONFIG_DIR = Path.home() / ".jarvis"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
MEMORY_DIR = CONFIG_DIR / "memory"
LOGS_DIR = CONFIG_DIR / "logs"


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    # Best efficiency/quality tradeoffs for local inference:
    # - Primary: qwen2.5:3b  (very fast, ~2 GB, great instruction following)
    # - Smarter:  qwen2.5:7b  (4 GB, better reasoning)
    # - Biggest:  qwen2.5:14b (8 GB, near GPT-4 quality locally)
    # - Coding:   qwen2.5-coder:7b
    primary_model: str = "qwen2.5:3b"
    reasoning_model: str = "qwen2.5:7b"
    embedding_model: str = "nomic-embed-text"
    temperature: float = 0.7
    context_window: int = 8192
    # Keep model loaded between calls (faster responses)
    keep_alive: str = "10m"


@dataclass
class MemoryConfig:
    # SQLite for structured conversation history
    db_path: str = str(MEMORY_DIR / "jarvis.db")
    # ChromaDB for semantic/vector memory
    chroma_path: str = str(MEMORY_DIR / "chroma")
    # How many recent turns to include in the prompt
    recent_turns: int = 20
    # How many semantic memories to retrieve per query
    semantic_top_k: int = 5
    # Summarise conversation every N turns to compress context
    summary_every_n: int = 50


@dataclass
class AgentConfig:
    max_agents: int = 5
    max_iterations: int = 15
    timeout_seconds: int = 120


@dataclass
class UIConfig:
    # Jarvis persona name shown in the terminal
    name: str = "JARVIS"
    user_name: str = "Boss"
    stream_output: bool = True
    show_thinking: bool = False   # show <think> blocks when using reasoning models
    theme: str = "dark"           # dark | light


@dataclass
class JarvisConfig:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    ui: UIConfig = field(default_factory=UIConfig)


def _ensure_dirs(cfg: JarvisConfig) -> None:
    for d in [CONFIG_DIR, MEMORY_DIR, LOGS_DIR,
              Path(cfg.memory.chroma_path)]:
        d.mkdir(parents=True, exist_ok=True)


def load_config() -> JarvisConfig:
    cfg = JarvisConfig()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        # Merge top-level sections
        if "ollama" in data:
            for k, v in data["ollama"].items():
                if hasattr(cfg.ollama, k):
                    setattr(cfg.ollama, k, v)
        if "memory" in data:
            for k, v in data["memory"].items():
                if hasattr(cfg.memory, k):
                    setattr(cfg.memory, k, v)
        if "agent" in data:
            for k, v in data["agent"].items():
                if hasattr(cfg.agent, k):
                    setattr(cfg.agent, k, v)
        if "ui" in data:
            for k, v in data["ui"].items():
                if hasattr(cfg.ui, k):
                    setattr(cfg.ui, k, v)
    # Allow env-var overrides for the most common knobs
    if os.getenv("JARVIS_MODEL"):
        cfg.ollama.primary_model = os.environ["JARVIS_MODEL"]
    if os.getenv("JARVIS_HOST"):
        cfg.ollama.host = os.environ["JARVIS_HOST"]
    _ensure_dirs(cfg)
    return cfg


def save_config(cfg: JarvisConfig) -> None:
    _ensure_dirs(cfg)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(asdict(cfg), f, default_flow_style=False)
