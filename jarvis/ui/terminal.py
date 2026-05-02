"""Rich-powered terminal chat interface for Jarvis."""

from __future__ import annotations

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from jarvis.agents.base import list_agents
from jarvis.config import JarvisConfig
from jarvis.core.brain import Brain

BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
"""

HELP_TEXT = """
[bold cyan]Commands:[/]
  [green]/help[/]           Show this help message
  [green]/agents[/]         List available specialist agents
  [green]/learn <topic> | <content>[/]
                   Teach Jarvis something new
  [green]/rate <1-5> [comment][/]
                   Rate the last response for self-improvement
  [green]/stats[/]          Show memory statistics
  [green]/model <name>[/]   Switch to a different Ollama model
  [green]/clear[/]          Clear the screen
  [green]/exit[/]           Quit Jarvis
"""


class TerminalUI:
    """Interactive terminal chat loop."""

    def __init__(self, config: JarvisConfig | None = None) -> None:
        self.config = config or JarvisConfig()
        self.console = Console()
        self.brain = Brain(self.config)
        history_path = self.config.data_dir / "prompt_history"
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_session: PromptSession = PromptSession(
            history=FileHistory(str(history_path)),
        )

    def _print_banner(self) -> None:
        self.console.print(Text(BANNER, style="bold cyan"))
        self.console.print(
            Panel(
                f"[bold]Model:[/] {self.config.model.name}  |  "
                f"[bold]Session:[/] {self.brain.session_id}  |  "
                f"Type [green]/help[/] for commands",
                title="[bold cyan]Local AI Assistant[/]",
                border_style="cyan",
            )
        )
        self.console.print()

    def _handle_command(self, text: str) -> bool:
        """Handle slash commands. Returns True if the input was a command."""
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            self.console.print(HELP_TEXT)
        elif cmd == "/exit":
            self.console.print("[bold cyan]Goodbye, sir.[/]")
            self.brain.close()
            sys.exit(0)
        elif cmd == "/clear":
            self.console.clear()
            self._print_banner()
        elif cmd == "/agents":
            agents = list_agents()
            if not agents:
                self.console.print("[yellow]No agents registered.[/]")
            for a in agents:
                self.console.print(f"  [green]{a['name']}[/] — {a['description']}")
        elif cmd == "/learn":
            if "|" not in arg:
                self.console.print("[red]Usage: /learn <topic> | <content>[/]")
            else:
                topic, content = arg.split("|", 1)
                self.brain.learn(topic.strip(), content.strip())
                self.console.print(f"[green]Learned about:[/] {topic.strip()}")
        elif cmd == "/rate":
            try:
                rating_parts = arg.split(maxsplit=1)
                rating = int(rating_parts[0])
                comment = rating_parts[1] if len(rating_parts) > 1 else ""
                self.brain.rate_last(rating, comment)
                self.console.print(f"[green]Feedback saved (rating={rating})[/]")
            except (ValueError, IndexError):
                self.console.print("[red]Usage: /rate <1-5> [comment][/]")
        elif cmd == "/stats":
            stats = self.brain.stats()
            self.console.print(Panel(
                f"[bold]Messages:[/] {stats['total_messages']}  |  "
                f"[bold]Sessions:[/] {stats['total_sessions']}  |  "
                f"[bold]Knowledge entries:[/] {stats['knowledge_entries']}",
                title="Memory Stats",
                border_style="cyan",
            ))
        elif cmd == "/model":
            if not arg:
                self.console.print(f"[bold]Current model:[/] {self.config.model.name}")
            else:
                self.config.model.name = arg.strip()
                self.brain.llm.config.name = arg.strip()
                self.console.print(f"[green]Switched to model:[/] {arg.strip()}")
        else:
            return False
        return True

    def run(self) -> None:
        """Main loop."""
        self._print_banner()

        while True:
            try:
                user_input = self.prompt_session.prompt(
                    [("class:prompt", "You > ")],
                    style=_prompt_style(),
                ).strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[bold cyan]Goodbye, sir.[/]")
                self.brain.close()
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if self._handle_command(user_input):
                    continue

            self.console.print()
            try:
                full_response = ""
                with Live(
                    Markdown(""),
                    console=self.console,
                    refresh_per_second=8,
                    vertical_overflow="visible",
                ) as live:
                    for token in self.brain.ask_stream(user_input):
                        full_response += token
                        live.update(Markdown(full_response))
            except Exception as exc:
                self.console.print(f"[bold red]Error:[/] {exc}")
                continue

            self.console.print()


def _prompt_style():
    from prompt_toolkit.styles import Style
    return Style.from_dict({
        "prompt": "bold cyan",
    })
