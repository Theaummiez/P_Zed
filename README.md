# Jarvis — Local AI Assistant

A fully local AI assistant inspired by Jarvis from Iron Man. Runs entirely on your machine with **no rate limits**, **no cloud dependency**, and **no data leaving your computer**.

## Features

- **100% Local** — powered by [Ollama](https://ollama.com) and efficient open-source models
- **Multi-Agent System** — automatically delegates complex tasks to specialized agents (coder, researcher, planner, summarizer, critic) that run in parallel
- **Persistent Memory** — remembers past conversations and learned knowledge across sessions (SQLite)
- **Self-Improving** — learns from your feedback to give better answers over time
- **Beautiful Terminal UI** — Rich-powered streaming chat with Markdown rendering
- **Resource Efficient** — runs comfortably on 8 GB RAM with the default model

## Quick Start

```bash
# One-command setup (installs Ollama + model + Jarvis)
chmod +x setup.sh && ./setup.sh

# Or manually:
pip install -e .
ollama pull qwen3:4b    # ~3 GB download
jarvis                   # start chatting
```

## Usage

```bash
# Start with default model (qwen3:4b)
jarvis

# Use a different model
jarvis -m phi4-mini          # lighter, ~2.5 GB
jarvis -m llama3.2:3b        # Meta's compact model
jarvis -m mistral            # Mistral 7B (needs 16 GB)

# Debug mode
jarvis -v
```

### Chat Commands

| Command | Description |
|---|---|
| `/help` | Show all commands |
| `/agents` | List available specialist agents |
| `/learn <topic> \| <content>` | Teach Jarvis something new |
| `/rate <1-5> [comment]` | Rate the last response (feeds self-improvement) |
| `/stats` | Show memory statistics |
| `/model <name>` | Switch model mid-session |
| `/clear` | Clear the screen |
| `/exit` | Quit |

### Multi-Agent System

When you ask a complex question, Jarvis automatically decomposes it and delegates sub-tasks to specialized agents:

| Agent | Specialty |
|---|---|
| `summarizer` | Condense long text into bullet points |
| `coder` | Write, review, or explain code |
| `researcher` | Structured topic analysis |
| `planner` | Step-by-step action plans |
| `critic` | Constructive review of ideas/code |

Results from all agents are synthesized into a single coherent answer.

### Self-Improvement

Jarvis gets better the more you use it:

1. **Feedback loop** — use `/rate` to tell Jarvis what you liked or didn't. It adjusts its style based on your preferences.
2. **Knowledge base** — use `/learn` to teach Jarvis facts specific to you. It recalls them in future conversations.
3. **Conversation memory** — past sessions inform future answers through context injection.

## Recommended Models

| Model | Size | RAM | Best For |
|---|---|---|---|
| `qwen3:4b` (default) | 4B | ~3 GB | Best efficiency/capability ratio |
| `phi4-mini` | 3.8B | ~2.5 GB | Lowest resource usage, strong reasoning |
| `llama3.2:3b` | 3B | ~2 GB | Ultra-light, good general chat |
| `qwen2.5-coder:7b` | 7B | ~5 GB | Code-heavy workflows |
| `mistral` | 7B | ~5.5 GB | Fastest throughput (16 GB systems) |
| `llama3.3:8b` | 8B | ~6 GB | Best all-around (16 GB systems) |

## Configuration

Configuration is via environment variables or by editing `jarvis/config.py`:

| Variable | Default | Description |
|---|---|---|
| `JARVIS_MODEL` | `qwen3:4b` | Default Ollama model |
| `JARVIS_DATA_DIR` | `~/.jarvis` | Where memory DB and history are stored |

## Architecture

```
jarvis/
├── __main__.py          # CLI entry point
├── config.py            # Pydantic configuration
├── core/
│   ├── llm.py           # Ollama SDK wrapper
│   └── brain.py         # Central coordinator (LLM + memory + agents)
├── memory/
│   └── store.py         # SQLite persistent memory & knowledge base
├── agents/
│   ├── base.py          # Agent base class & registry
│   ├── builtin.py       # Built-in specialist agents
│   └── orchestrator.py  # Multi-agent task decomposition & parallel execution
└── ui/
    └── terminal.py      # Rich terminal chat interface
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- 8 GB RAM minimum (for default model)
