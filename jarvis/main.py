"""
Application bootstrap — wires everything together and starts the UI.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from jarvis.config.settings import load_config, save_config, LOGS_DIR
from jarvis.core.llm import OllamaClient
from jarvis.memory.store import MemoryStore
from jarvis.agents.react_agent import ReactAgent
from jarvis.agents.orchestrator import Orchestrator
from jarvis.tools.registry import build_tools
from jarvis.ui.terminal import TerminalUI


def _setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(str(LOGS_DIR / "jarvis.log")),
        ],
    )


async def main() -> None:
    debug = "--debug" in sys.argv

    _setup_logging(debug)

    cfg = load_config()
    save_config(cfg)   # write defaults if first run

    llm = OllamaClient(cfg.ollama)
    memory = MemoryStore(cfg, llm_client=llm)
    orchestrator = Orchestrator(cfg, llm)
    tools = build_tools(memory, orchestrator)
    agent = ReactAgent(cfg, llm, tools, memory)
    ui = TerminalUI(cfg, agent, llm)

    try:
        await ui.run()
    finally:
        await llm.close()
        memory.close()


if __name__ == "__main__":
    asyncio.run(main())
