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
from jarvis.project_root import discover_project_root, is_jarvis_project_root


console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Local Jarvis-style assistant via Ollama (terminal, memory, optional multi-agent).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("JARVIS_MODEL"),
        help="Ollama model name (default: env JARVIS_MODEL or qwen2.5:7b)",
    )
    p.add_argument(
        "--multi-agent",
        action="store_true",
        help="Enable coordinator + specialist routing (more CPU/GPU when delegating)",
    )
    p.add_argument("--memory", default=None, help="SQLite path for persistent memory")
    p.add_argument("--no-memory", action="store_true", help="Disable loading prior summary only display")
    p.add_argument(
        "--workspace",
        default=None,
        metavar="DIR",
        help="Sandbox root for file tools (default: current directory or JARVIS_WORKSPACE_ROOT)",
    )
    p.add_argument(
        "--no-file-tools",
        action="store_true",
        help="Disable workspace list/read/write tools for this session",
    )
    p.add_argument(
        "--no-skills",
        action="store_true",
        help="Disable loading Skills/*.md into system context",
    )
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
    if args.workspace:
        settings.workspace_root = Path(args.workspace).expanduser().resolve()

    if settings.workspace_tools and not is_jarvis_project_root(settings.workspace_root):
        console.print(
            "[yellow]Warning:[/yellow] workspace does not look like this repo "
            "(missing jarvis/ + pyproject.toml). File tools may write elsewhere than you expect. "
            "Run [bold]jarvis[/bold] from inside [bold]P_Zed[/bold], or set "
            "[bold]JARVIS_WORKSPACE_ROOT[/bold] / [bold]--workspace[/bold] to your clone path "
            "(e.g. [dim]~/Documents/Maison/P_Zed[/dim])."
        )
    if args.no_skills:
        settings.skills_enabled = False

    await _ensure_model(settings.ollama_host, settings.model)

    title = f"Jarvis (local) — model [bold]{settings.model}[/bold]"
    if settings.multi_agent:
        title += " — [cyan]multi-agent[/cyan]"
    try:
        ws_root = settings.workspace_root.resolve()
        skills_dir = ws_root / settings.skills_dir
        if settings.skills_enabled and skills_dir.is_dir():
            title += f"\n[dim]Skills:[/dim] [cyan]{skills_dir.relative_to(ws_root)}/[/cyan] [dim](*.md)[/dim]"
        elif settings.skills_enabled:
            title += (
                f"\n[dim]Skills:[/dim] [dim](no {settings.skills_dir}/ here — "
                "create it under workspace for custom rules)[/dim]"
            )
    except (OSError, ValueError):
        pass
    try:
        ws = settings.workspace_root.resolve()
    except OSError:
        ws = settings.workspace_root
    title += f"\n[dim]Workspace:[/dim] {ws}"
    if settings.workspace_tools:
        title += " [dim](file tools on)[/dim]"
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
