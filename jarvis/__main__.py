"""Entry point: ``python -m jarvis`` or ``jarvis`` (if installed)."""

from __future__ import annotations

import argparse
import logging
import sys

from jarvis.config import JarvisConfig


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis — your local AI assistant",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="Ollama model name (default: qwen3:4b)",
    )
    parser.add_argument(
        "--fallback",
        default=None,
        help="Fallback model if primary is unavailable (default: phi4-mini)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming (get full response at once)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config = JarvisConfig()
    if args.model:
        config.model.name = args.model
    if args.fallback:
        config.model.fallback = args.fallback

    # Import agents so they register themselves
    import jarvis.agents.builtin  # noqa: F401

    from jarvis.ui.terminal import TerminalUI

    ui = TerminalUI(config)
    ui.run()


if __name__ == "__main__":
    main()
