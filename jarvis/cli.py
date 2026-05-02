"""Terminal REPL for the local assistant."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from jarvis.config import get_settings
from jarvis.memory import load_state, messages_since_last_summary
from jarvis.ollama import OllamaError, list_models
from jarvis.pipeline import run_turn


console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Local Jarvis-style assistant via Ollama (terminal, memory, optional multi-agent).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("JARVIS_MODEL"),
        help="Ollama model name (default: env JARVIS_MODEL or qwen2.5:3b)",
    )
    p.add_argument(
        "--multi-agent",
        action="store_true",
        help="Enable coordinator + specialist routing (more CPU/GPU when delegating)",
    )
    p.add_argument("--memory", default=None, help="SQLite path for persistent memory")
    p.add_argument("--no-memory", action="store_true", help="Disable loading prior summary only display")
    return p


async def _ensure_model(host: str, model: str) -> None:
    try:
        names = await list_models(host)
    except OllamaError as e:
        console.print(f"[red]Cannot reach Ollama:[/red] {e}")
        console.print("Install from https://ollama.com and run: [bold]ollama serve[/bold]")
        raise SystemExit(1)
    if model not in names and not any(n.startswith(model + ":") for n in names):
        console.print(
            f"[yellow]Model '{model}' not found locally.[/yellow] Pull it with:\n"
            f"  [bold]ollama pull {model}[/bold]"
        )


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    if args.model:
        settings.model = args.model
    if args.multi_agent:
        settings.multi_agent = True
    if args.memory:
        settings.memory_path = Path(args.memory)

    await _ensure_model(settings.ollama_host, settings.model)

    title = f"Jarvis (local) — model [bold]{settings.model}[/bold]"
    if settings.multi_agent:
        title += " — [cyan]multi-agent[/cyan]"
    console.print(Panel.fit(title, border_style="green"))

    state = load_state(settings.memory_path, settings.recent_turns)
    msg_since_summary = messages_since_last_summary(settings.memory_path)
    if state.summary and not args.no_memory:
        console.print(Panel(state.summary[:1200] + ("…" if len(state.summary) > 1200 else ""), title="Memory summary"))

    console.print("[dim]Commands: /quit /memory /clear-memory /model[/dim]\n")

    while True:
        try:
            line = Prompt.ask("[bold green]You[/bold green]")
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye.")
            raise SystemExit(0)

        text = line.strip()
        if not text:
            continue
        if text in ("/quit", "/exit", "/q"):
            console.print("Bye.")
            raise SystemExit(0)
        if text == "/memory":
            st = load_state(settings.memory_path, settings.recent_turns)
            console.print(Panel(st.summary or "(empty)", title="Stored summary"))
            continue
        if text == "/clear-memory":
            p = settings.memory_path
            if p.exists():
                p.unlink()
            console.print("[yellow]Memory file cleared.[/yellow]")
            msg_since_summary = messages_since_last_summary(settings.memory_path)
            continue
        if text.startswith("/model"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                console.print(f"Current model: [bold]{settings.model}[/bold]")
                continue
            settings.model = parts[1].strip()
            console.print(f"Switched model to [bold]{settings.model}[/bold] (session)")
            continue

        try:
            with console.status("[bold cyan]Thinking…[/bold cyan]"):
                reply, _state, summary_done = await run_turn(
                    settings,
                    text,
                    messages_since_summary=msg_since_summary,
                )
            if summary_done:
                msg_since_summary = messages_since_last_summary(settings.memory_path)
            else:
                msg_since_summary += 2
        except OllamaError as e:
            console.print(f"[red]{e}[/red]")
            continue

        console.print(Panel(Markdown(reply), title="Assistant", border_style="blue"))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
