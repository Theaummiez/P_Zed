#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# JARVIS — one-shot local installation script
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         JARVIS — Local AI Assistant  •  installer        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python ────────────────────────────────────────────────────────
PY=$(command -v python3 || command -v python || true)
if [ -z "$PY" ]; then
    echo "ERROR: Python 3.10+ is required but was not found."
    exit 1
fi

PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ required (found $PY_VER)."
    exit 1
fi
echo "✓ Python $PY_VER found"

# ── 2. Virtual environment ─────────────────────────────────────────────────
VENV_DIR="$(pwd)/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment…"
    "$PY" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip

# ── 3. Install Python dependencies ─────────────────────────────────────────
echo "Installing Python dependencies…"
pip install --quiet -r requirements.txt
pip install --quiet -e .
echo "✓ Python packages installed"

# ── 4. Check / install Ollama ──────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    echo ""
    echo "Ollama not found. Installing…"
    curl -fsSL https://ollama.com/install.sh | sh
    echo "✓ Ollama installed"
else
    echo "✓ Ollama already installed ($(ollama --version 2>/dev/null || echo 'unknown version'))"
fi

# ── 5. Pull default model ─────────────────────────────────────────────────
DEFAULT_MODEL="${JARVIS_MODEL:-qwen2.5:3b}"
echo ""
echo "Pulling model: $DEFAULT_MODEL"
echo "(This may take a few minutes on first run — ~2 GB download)"
echo ""

# Start ollama serve in background if not running
if ! pgrep -x ollama &>/dev/null; then
    echo "Starting ollama server…"
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 3
fi

ollama pull "$DEFAULT_MODEL"
echo "✓ Model ready: $DEFAULT_MODEL"

# ── 6. Create launcher script ─────────────────────────────────────────────
cat > jarvis_run.sh << 'EOF'
#!/usr/bin/env bash
# Quick launcher — activates venv and starts JARVIS
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.venv/bin/activate"

# Start ollama if not running
if ! pgrep -x ollama &>/dev/null; then
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
fi

python -m jarvis "$@"
EOF
chmod +x jarvis_run.sh

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Installation complete!                                   ║"
echo "║                                                           ║"
echo "║  Start JARVIS:   ./jarvis_run.sh                         ║"
echo "║  Or:             source .venv/bin/activate && jarvis      ║"
echo "║                                                           ║"
echo "║  Smarter model:  JARVIS_MODEL=qwen2.5:7b ./jarvis_run.sh ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
