"""Hermes-inspired terminal layout for ZEDO (banner, status bar, separators)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

BRAND = "ZEDO"
DEFAULT_CTX_WINDOW = 4096  # aligned with main chat num_ctx in pipeline


@dataclass
class SessionMeta:
    started_at: datetime

    @classmethod
    def now(cls) -> SessionMeta:
        return cls(started_at=datetime.now(timezone.utc))


def _fmt_duration(start: datetime) -> str:
    delta = datetime.now(timezone.utc) - start
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    return f"{s // 3600}h{(s % 3600) // 60}m"


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def render_banner(
    *,
    model: str,
    workspace: Path,
    skills_on: bool,
    skills_hint: str,
    file_tools_on: bool,
    multi_agent: bool,
) -> Panel:
    """Welcome banner (Hermes-style info density, ZEDO branding)."""
    try:
        cwd = workspace.resolve()
        cwd_s = str(cwd)
    except OSError:
        cwd_s = str(workspace)

    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()

    rows.add_row("Model", Text(model, style="bold cyan"))
    rows.add_row("Workspace", Text(_truncate(cwd_s, 72), style="white"))
    mode_parts = []
    if file_tools_on:
        mode_parts.append("file tools")
    if skills_on:
        mode_parts.append(f"skills ({skills_hint})")
    else:
        mode_parts.append("skills off")
    if multi_agent:
        mode_parts.append("multi-agent")
    rows.add_row("Session", Text(" · ".join(mode_parts), style="dim"))

    subtitle = Text()
    subtitle.append("Local assistant", style="italic dim")
    subtitle.append(" · ", style="dim")
    subtitle.append("Ollama", style="italic cyan")

    body = Group(Text.assemble((BRAND, "bold bright_white"), (" — terminal session\n", "dim")), subtitle, Rule(style="dim"), rows)

    return Panel(
        body,
        border_style="bright_blue",
        box=box.ROUNDED,
        title=f"[bold bright_white]{BRAND}[/]",
        subtitle="[dim]type /help for commands · Ctrl+C twice to exit[/]",
        padding=(1, 2),
    )


def render_status_bar(
    *,
    model: str,
    ctx_window: int,
    session: SessionMeta,
    width: int | None = None,
) -> Text:
    """Single-line status (inspired by Hermes CLI status bar)."""
    if width is None:
        width = shutil.get_terminal_size((100, 24)).columns

    model_disp = _truncate(model, 26)
    elapsed = _fmt_duration(session.started_at)
    # Local run: no token metering — show placeholder bar like Hermes "plenty of room"
    bar_w = max(8, min(24, (width - 60) // 2))
    filled = max(1, bar_w // 8)
    bar_chars = "█" * filled + "░" * (bar_w - filled)

    parts: list[str | tuple[str, str]] = []
    parts.append((" ● ", "bright_blue"))
    parts.append((f"{model_disp}", "bold white"))
    parts.append((" │ ", "dim"))
    parts.append(("local", "green"))
    parts.append((" │ ", "dim"))
    parts.append((f"{ctx_window // 1000}k ctx", "cyan"))
    parts.append((" │ ", "dim"))
    parts.append((f"[{bar_chars}]", "green"))
    parts.append((" │ ", "dim"))
    parts.append((elapsed, "yellow"))

    line = Text.assemble(*parts)
    return line


def render_reply_panel(markdown_body: str, *, title: str | None = None) -> Panel:
    """Assistant output panel with ZEDO title."""
    from rich.markdown import Markdown

    t = title or BRAND
    return Panel(
        Markdown(markdown_body),
        title=f"[bold bright_blue]{t}[/]",
        border_style="blue",
        box=box.ROUNDED,
    )


def slash_help_text() -> str:
    return """
**Slash commands** (Hermes-style)

| Command | Action |
|---------|--------|
| `/help` | Show this help |
| `/quit` `/exit` `/q` | Leave ZEDO |
| `/memory` | Show stored memory summary |
| `/clear-memory` | Reset SQLite memory |
| `/model` | Show current model |
| `/model `*`name`* | Switch model for this session |
"""


THINKING_FRAMES = (
    "[cyan]◜[/cyan] thinking…",
    "[cyan]◠[/cyan] thinking…",
    "[cyan]◇[/cyan] thinking…",
)
