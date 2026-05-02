"""Terminal REPL for ZEDO — Hermes-inspired layout (banner, status bar, panels)."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule

from zedo.config import get_settings
from zedo.memory import load_state, messages_since_last_summary
from zedo.ollama import OllamaError, list_models
from zedo.pipeline import run_turn
from zedo.project_root import discover_project_root, is_zedo_project_root
from zedo.tui import (
    BRAND,
    SessionMeta,
    render_banner,
    render_reply_panel,
    render_status_bar,
    slash_help_text,
)


console = Console()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Zedo — local assistant via Ollama (terminal, memory, Skills, optional multi-agent).",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("ZEDO_MODEL") or os.environ.get("JARVIS_MODEL"),
        help="Ollama model name (default: env ZEDO_MODEL or qwen2.5:7b; JARVIS_MODEL still accepted)",
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
        help="Sandbox root for file tools (default: current directory or ZEDO_WORKSPACE_ROOT)",
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

    if settings.workspace_tools and not is_zedo_project_root(settings.workspace_root):
        console.print(
            "[yellow]Warning:[/yellow] workspace does not look like this repo "
            "(missing zedo/ + pyproject.toml). File tools may write elsewhere than you expect. "
            "Run [bold]zedo[/bold] from inside [bold]P_Zed[/bold], or set "
            "[bold]ZEDO_WORKSPACE_ROOT[/bold] / [bold]--workspace[/bold] to your clone path "
            "(e.g. [dim]~/Documents/Maison/P_Zed[/dim])."
        )
    if args.no_skills:
        settings.skills_enabled = False

    await _ensure_model(settings.ollama_host, settings.model)

    skills_hint = "on"
    try:
        ws_root = settings.workspace_root.resolve()
        sd = ws_root / settings.skills_dir
        if settings.skills_enabled and sd.is_dir():
            skills_hint = f"{sd.relative_to(ws_root)}/"
        elif not settings.skills_enabled:
            skills_hint = "off"
    except (OSError, ValueError):
        skills_hint = "on" if settings.skills_enabled else "off"

    banner = render_banner(
        model=settings.model,
        workspace=settings.workspace_root,
        skills_on=settings.skills_enabled,
        skills_hint=skills_hint,
        file_tools_on=settings.workspace_tools,
        multi_agent=settings.multi_agent,
    )
    console.print(banner)
    console.print()

    state = load_state(settings.memory_path, settings.recent_turns)
    msg_since_summary = messages_since_last_summary(settings.memory_path)
    if state.summary and not args.no_memory:
        console.print(
            Panel(
                state.summary[:1200] + ("…" if len(state.summary) > 1200 else ""),
                title="[dim]Previous session summary[/]",
                border_style="dim",
            )
        )
        console.print()

    session = SessionMeta.now()
    ctx_window = 4096

    console.print(Rule("[dim]commands: /help · /quit · /memory · /clear-memory · /model[/]", style="dim"))
    console.print()

    while True:
        console.print(render_status_bar(model=settings.model, ctx_window=ctx_window, session=session))
        console.print()

        try:
            line = Prompt.ask(f"[bold bright_blue]{BRAND}[/bold bright_blue] [dim]›[/dim]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended.[/dim]")
            raise SystemExit(0)

        text = line.strip()
        if not text:
            continue
        low = text.lower()
        if low in ("/quit", "/exit", "/q"):
            console.print("[dim]Bye.[/dim]")
            raise SystemExit(0)
        if low == "/help":
            console.print(Panel(Markdown(slash_help_text()), title=f"[bold]{BRAND}[/] help", border_style="dim"))
            continue
        if text == "/memory":
            st = load_state(settings.memory_path, settings.recent_turns)
            console.print(Panel(st.summary or "(empty)", title="Memory summary", border_style="dim"))
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
            console.print(f"Switched model to [bold]{settings.model}[/bold] [dim](session)[/dim]")
            continue

        try:
            with console.status(
                f"[bold cyan]{BRAND}[/bold cyan] · reasoning…",
                spinner="dots",
                spinner_style="cyan",
            ):
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

        console.print()
        console.print(render_reply_panel(reply))
        console.print()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
