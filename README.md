# Local Jarvis-style assistant (terminal)

Run a **local** assistant on your machine: chat in the terminal, **no API keys**, no rate limits. It uses **[Ollama](https://ollama.com)** for inference (efficient Llama.cpp-based runtime, Metal/CUDA/CPU), **SQLite** for memory, and an optional **multi-agent** mode that routes work to specialist prompts (same small model; extra calls only when useful).

## Why this stack (efficiency)

| Piece | Role |
|--------|------|
| **Ollama** | Standard local runner; pulls quantized GGUF models; uses GPU when available. |
| **Small instruct models** | `qwen2.5:3b`, `phi3:mini`, `llama3.2:3b` — strong quality per GB RAM; good default for daily Q&A. |
| **Quantization** | Models are already 4-bit (typical); fewer bits → less VRAM/RAM. |
| **Rolling summary** | Long-term “memory” without sending full history every time — fewer tokens per turn. |

“Gets better each time you talk” here means **persistent memory**: preferences and facts accumulate in a rolling summary plus recent turns, so later sessions stay coherent (not automatic self-training of the weights).

## Setup

1. **Install Ollama** from https://ollama.com and start it (`ollama serve` if needed).

2. **Pull a small model** (pick one that fits your RAM/VRAM):

   ```bash
   ollama pull qwen2.5:3b
   ```

   Alternatives: `phi3:mini`, `llama3.2:3b`, `gemma2:2b`.

3. **Install this project**:

   ```bash
   cd /path/to/P_Zed
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e .
   ```

4. **Run**:

   ```bash
   jarvis
   # or
   python -m jarvis.cli
   ```

### Options

- `--model <name>` — Ollama model tag (default: `qwen2.5:3b` or `JARVIS_MODEL`).
- `--multi-agent` — Router + analyst/writer-style replies (uses extra inference when delegating).
- `--memory /path/to/file.db` — Custom SQLite path (default: `~/.jarvis/memory.db`).

### Environment (optional)

Copy and edit:

```bash
export JARVIS_OLLAMA_HOST=http://127.0.0.1:11434
export JARVIS_MODEL=qwen2.5:3b
export JARVIS_SUMMARY_MODEL=qwen2.5:3b   # optional; defaults to JARVIS_MODEL
export JARVIS_MULTI_AGENT=false
export JARVIS_SUMMARY_EVERY=8              # messages before rolling summary refresh
```

### REPL commands

- `/quit` — Exit  
- `/memory` — Show stored summary  
- `/clear-memory` — Delete SQLite memory file  
- `/model <name>` — Switch model for this session  

## Requirements

- Python **3.11+**
- **Ollama** running locally with at least one pulled model
