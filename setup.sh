#!/usr/bin/env bash
set -euo pipefail

BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
fail()  { echo -e "${RED}[FAIL]${RESET}  $*"; exit 1; }

echo -e "${BOLD}${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║          Jarvis Setup Script           ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${RESET}"

# ── 1. Python check ──────────────────────────────────────────────────
info "Checking Python…"
if command -v python3 &>/dev/null; then
    PY=$(python3 --version)
    ok "Found $PY"
else
    fail "Python 3.10+ is required. Install it from https://python.org"
fi

# ── 2. Ollama check / install ────────────────────────────────────────
info "Checking Ollama…"
if command -v ollama &>/dev/null; then
    ok "Ollama is installed"
else
    warn "Ollama not found — installing…"
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama installed"
fi

# ── 3. Start Ollama if not running ───────────────────────────────────
info "Ensuring Ollama server is running…"
if curl -sf http://localhost:11434/api/version &>/dev/null; then
    ok "Ollama server is already running"
else
    info "Starting Ollama in the background…"
    ollama serve &>/dev/null &
    sleep 3
    if curl -sf http://localhost:11434/api/version &>/dev/null; then
        ok "Ollama server started"
    else
        warn "Could not auto-start Ollama. Run 'ollama serve' manually."
    fi
fi

# ── 4. Pull default model ───────────────────────────────────────────
MODEL="${JARVIS_MODEL:-qwen3:4b}"
info "Pulling model ${BOLD}${MODEL}${RESET}…"
ollama pull "$MODEL" && ok "Model $MODEL ready" || warn "Could not pull $MODEL — you can pull it later"

# ── 5. Install Python package ────────────────────────────────────────
info "Installing Jarvis Python package…"
pip install -e "$(dirname "$0")" && ok "Jarvis installed" || fail "pip install failed"

echo ""
echo -e "${GREEN}${BOLD}Setup complete!${RESET}"
echo -e "Run ${CYAN}jarvis${RESET} or ${CYAN}python -m jarvis${RESET} to start."
echo ""
