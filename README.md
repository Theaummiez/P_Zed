# JARVIS — Local AI Assistant

A local, private AI assistant inspired by Tony Stark's JARVIS. Runs **entirely on your machine** — no API keys, no cloud, no data leaving your device.

```
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
Just A Rather Very Intelligent System
```

---

## Features

| Feature | Detail |
|---------|--------|
| **100% local** | Powered by [Ollama](https://ollama.com) — zero cloud dependency |
| **Efficient models** | Qwen2.5 3B by default (2 GB RAM, very fast); upgrade to 7B/14B anytime |
| **ReAct agent loop** | Thinks step-by-step, calls tools, feeds results back, gives final answer |
| **Multi-agent orchestration** | Spawns parallel sub-agents for complex tasks |
| **Persistent memory** | SQLite (full history) + ChromaDB (semantic vector search) — gets smarter each conversation |
| **Self-summarisation** | Automatically compresses old conversations so context stays small |
| **Rich tools** | Shell, file read/write, web search (DuckDuckGo, no key), Python runner, memory management |
| **Beautiful terminal UI** | Rich panels, streaming output, slash commands, input history |

---

## Quick Start

### 1. One-shot install

```bash
git clone <this-repo>
cd <repo>
bash install.sh
```

The script will:
1. Create a Python virtual environment
2. Install all dependencies
3. Install [Ollama](https://ollama.com) if missing
4. Pull the default model (`qwen2.5:3b`, ~2 GB)

### 2. Run

```bash
./jarvis_run.sh
```

Or manually:

```bash
source .venv/bin/activate
ollama serve &   # if not already running
python -m jarvis
```

---

## Model Selection

JARVIS is designed around the **Qwen2.5** family — the best open-source models per GB of RAM:

| Model | RAM | Speed | Quality | When to use |
|-------|-----|-------|---------|-------------|
| `qwen2.5:3b` | ~2 GB | Very fast | Good | Default — daily questions, fast responses |
| `qwen2.5:7b` | ~4 GB | Fast | Great | Better reasoning, longer tasks |
| `qwen2.5:14b` | ~8 GB | Moderate | Excellent | Complex analysis, near GPT-4 quality |
| `qwen2.5-coder:7b` | ~4 GB | Fast | Best for code | Coding tasks |

Switch model at runtime:

```
/model qwen2.5:7b
```

Or set an environment variable:

```bash
JARVIS_MODEL=qwen2.5:7b ./jarvis_run.sh
```

Pull a new model:

```
/pull qwen2.5:14b
```

---

## Terminal Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/models` | List locally available models |
| `/model <name>` | Switch model mid-session |
| `/pull <name>` | Download a new model from Ollama |
| `/history` | Show recent conversation turns |
| `/clear` | Clear in-session history (memory persists) |
| `/think` | Toggle display of reasoning (`<think>` blocks) |
| `/exit` | Quit |

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `↑` / `↓` | Navigate input history |
| `Ctrl+C` | Cancel current generation |
| `Ctrl+D` | Exit |

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     TerminalUI                          │
│  (Rich panels, streaming, slash commands, Prompt Toolkit)│
└───────────────────────────┬─────────────────────────────┘
                            │
                     ┌──────▼──────┐
                     │ ReactAgent  │  ← Main agent loop (ReAct)
                     └──────┬──────┘
              ┌─────────────┼─────────────┐
              │             │             │
       ┌──────▼──────┐  ┌───▼───┐  ┌─────▼──────┐
       │  OllamaClient│  │ Tools │  │MemoryStore │
       │  (streaming) │  │  7x   │  │SQLite+Chroma│
       └─────────────┘  └───┬───┘  └────────────┘
                             │
                     ┌───────▼────────┐
                     │  Orchestrator  │  ← Multi-agent coordinator
                     │  (N sub-agents)│
                     └────────────────┘
```

### Memory System

JARVIS has a two-tier memory:

1. **SQLite** — stores every conversation turn verbatim, for loading recent history.
2. **ChromaDB** — stores vector embeddings of each turn; enables semantic recall ("what did I say about X two weeks ago?").
3. **Auto-summarisation** — every 50 turns, old conversations are compressed by the LLM into a summary, keeping the context window small.

### Multi-Agent Mode

When a task is complex, JARVIS can call `spawn_agents` to fan out N sub-agents in parallel. Each gets a task description and shared context, runs independently, and reports back. Results are aggregated and returned to the main agent.

Example prompt:

> "Research the best Python web frameworks in 2026, compare their performance benchmarks, and suggest which one I should use for a high-traffic API."

JARVIS will spawn agents for each framework, gather results in parallel, and synthesise them.

---

## Configuration

Config is stored at `~/.jarvis/config.yaml` (auto-created on first run).

```yaml
ollama:
  host: http://localhost:11434
  primary_model: qwen2.5:3b
  reasoning_model: qwen2.5:7b
  temperature: 0.7
  context_window: 8192
  keep_alive: 10m

memory:
  recent_turns: 20
  semantic_top_k: 5
  summary_every_n: 50

agent:
  max_agents: 5
  max_iterations: 15
  timeout_seconds: 120

ui:
  name: JARVIS
  user_name: Boss
  stream_output: true
  show_thinking: false
```

---

## Optional: Better Local Embeddings

For richer semantic memory, install the sentence-transformers package (~80 MB):

```bash
pip install sentence-transformers
```

JARVIS auto-detects it and uses `all-MiniLM-L6-v2` for embeddings (faster and more accurate than Ollama's embedding endpoint).

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) (auto-installed by `install.sh`)
- ~2 GB disk space for the default model
- 4 GB RAM minimum (8 GB recommended for the 7B model)

---

## Project Structure

```
jarvis/
├── main.py              # Bootstrap — wires everything
├── config/
│   └── settings.py      # All configuration
├── core/
│   ├── llm.py           # Async Ollama client (streaming)
│   └── prompts.py       # System prompts
├── agents/
│   ├── react_agent.py   # ReAct loop (reason → act → observe)
│   └── orchestrator.py  # Parallel sub-agent coordinator
├── memory/
│   └── store.py         # SQLite + ChromaDB memory
├── tools/
│   ├── shell_tool.py    # Run shell commands
│   ├── file_tool.py     # Read/write files
│   ├── web_tool.py      # DuckDuckGo search + URL fetch
│   ├── code_tool.py     # Run Python code
│   ├── memory_tool.py   # Explicit memory operations
│   └── agent_tool.py    # Spawn parallel sub-agents
└── ui/
    └── terminal.py      # Rich + Prompt Toolkit interface
```
