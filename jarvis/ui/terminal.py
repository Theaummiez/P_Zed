"""
Terminal UI — built with Rich (beautiful output) + Prompt Toolkit (smart input).

Features:
  • Coloured, panel-bordered JARVIS responses
  • Streaming token output (no waiting for the full reply)
  • Tool-call notifications in the status bar
  • Slash commands: /help /history /models /model <name> /clear /exit
  • Multi-line input with Ctrl+J
  • Ctrl+C cancels the current generation without exiting
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich import print as rprint

from jarvis.config.settings import JarvisConfig, CONFIG_DIR

_HISTORY_FILE = str(CONFIG_DIR / "input_history")

_DARK_STYLE = Style.from_dict({
    "prompt": "#00d7ff bold",
    "": "#e0e0e0",
})

_JARVIS_COLOR = "cyan"
_USER_COLOR = "yellow"
_TOOL_COLOR = "magenta"
_ERROR_COLOR = "red"
_INFO_COLOR = "dim white"


class TerminalUI:
    def __init__(self, cfg: JarvisConfig, agent, llm):
        self.cfg = cfg
        self.agent = agent
        self.llm = llm
        self.console = Console(highlight=True, markup=True)
        self._session: Optional[PromptSession] = None
        self._running = True

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------

    def _make_session(self) -> PromptSession:
        kb = KeyBindings()

        @kb.add("c-c")
        def _cancel(event):
            # Raise KeyboardInterrupt to cancel current generation
            raise KeyboardInterrupt()

        return PromptSession(
            history=FileHistory(_HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            key_bindings=kb,
            style=_DARK_STYLE,
            multiline=False,
        )

    def print_banner(self) -> None:
        banner = f"""
[bold cyan]
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
[/bold cyan]
[dim]Just A Rather Very Intelligent System — running locally[/dim]
[dim]Model: [cyan]{self.cfg.ollama.primary_model}[/cyan]   Type [bold]/help[/bold] for commands[/dim]
"""
        self.console.print(banner)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._session = self._make_session()
        self.print_banner()

        # Check Ollama availability
        if not await self.llm.is_available():
            self.console.print(
                Panel(
                    "[red]Ollama is not running.[/red]\n"
                    "Start it with: [bold]ollama serve[/bold]\n"
                    "Then pull a model: [bold]ollama pull qwen2.5:3b[/bold]",
                    title="[red]Connection Error[/red]",
                    border_style="red",
                )
            )
            return

        while self._running:
            try:
                raw = await self._session.prompt_async(
                    HTML(f"<prompt>{self.cfg.ui.user_name}</prompt> ❯ "),
                )
            except KeyboardInterrupt:
                continue
            except EOFError:
                self._running = False
                break

            user_input = raw.strip()
            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            await self._respond(user_input)

        self.console.print("\n[dim]JARVIS offline. Goodbye.[/dim]")

    # ------------------------------------------------------------------
    # Response rendering
    # ------------------------------------------------------------------

    async def _respond(self, user_input: str) -> None:
        self.console.print()

        # Show a spinner while waiting for first token
        spinner_done = asyncio.Event()
        response_parts: list[str] = []
        tool_notifications: list[str] = []

        def on_tool_call(name: str, args: dict) -> None:
            tool_notifications.append(
                f"[{_TOOL_COLOR}]⚙ Calling tool [bold]{name}[/bold]…[/{_TOOL_COLOR}]"
            )

        def on_tool_result(name: str, result) -> None:
            short = str(result)[:120].replace("\n", " ")
            tool_notifications.append(
                f"[{_TOOL_COLOR}]✓ [bold]{name}[/bold] → {short}[/{_TOOL_COLOR}]"
            )

        try:
            # Print tool notifications as they happen then stream response
            first_token = True
            with Live(
                Spinner("dots", text=f"[{_JARVIS_COLOR}]Thinking…[/{_JARVIS_COLOR}]"),
                console=self.console,
                refresh_per_second=15,
                transient=True,
            ) as live:
                async for token in self.agent.run_stream(
                    user_input,
                    on_tool_call=on_tool_call,
                    on_tool_result=on_tool_result,
                ):
                    response_parts.append(token)
                    if first_token:
                        first_token = False
                    # Update live display with tool notifications
                    if tool_notifications:
                        live.update(
                            Text.from_markup(
                                "\n".join(tool_notifications)
                                + f"\n[{_JARVIS_COLOR}]Thinking…[/{_JARVIS_COLOR}]"
                            )
                        )

            # Print tool notifications
            for note in tool_notifications:
                self.console.print(Text.from_markup(note))

            full_response = "".join(response_parts)

            # Render as Markdown inside a styled panel
            self.console.print(
                Panel(
                    Markdown(full_response),
                    title=f"[bold {_JARVIS_COLOR}]{self.cfg.ui.name}[/bold {_JARVIS_COLOR}]",
                    border_style=_JARVIS_COLOR,
                    padding=(0, 1),
                )
            )

        except KeyboardInterrupt:
            self.console.print(
                f"\n[{_INFO_COLOR}]Generation cancelled.[/{_INFO_COLOR}]"
            )
        except Exception as e:
            self.console.print(
                Panel(
                    f"[{_ERROR_COLOR}]{e}[/{_ERROR_COLOR}]",
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )
            if "--debug" in sys.argv:
                traceback.print_exc()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split()
        command = parts[0].lower()

        if command == "/help":
            help_text = """
**JARVIS Commands**

| Command | Description |
|---------|-------------|
| `/help` | Show this help |
| `/models` | List available Ollama models |
| `/model <name>` | Switch to a different model |
| `/history` | Show last 10 conversation turns |
| `/clear` | Clear conversation history |
| `/think` | Toggle thinking block visibility |
| `/pull <model>` | Download a new model |
| `/exit` or `/quit` | Exit JARVIS |

**Hotkeys**

| Key | Action |
|-----|--------|
| `Ctrl+C` | Cancel current generation |
| `Ctrl+D` | Exit |
| `↑` / `↓` | Navigate input history |
"""
            self.console.print(
                Panel(Markdown(help_text), title="Help", border_style="cyan")
            )

        elif command == "/models":
            try:
                models = await self.llm.list_models()
                if models:
                    lines = "\n".join(f"  • {m}" for m in models)
                    self.console.print(
                        Panel(lines, title="Available Models", border_style="cyan")
                    )
                else:
                    self.console.print("[dim]No models found. Run: ollama pull qwen2.5:3b[/dim]")
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

        elif command == "/model":
            if len(parts) < 2:
                self.console.print(
                    f"[dim]Current model: [cyan]{self.agent.model}[/cyan][/dim]"
                )
            else:
                new_model = parts[1]
                self.agent.model = new_model
                self.cfg.ollama.primary_model = new_model
                self.console.print(
                    f"[cyan]Switched to model: [bold]{new_model}[/bold][/cyan]"
                )

        elif command == "/history":
            turns = await self.agent.memory.get_recent_turns(10)
            if not turns:
                self.console.print("[dim]No conversation history yet.[/dim]")
            else:
                lines = []
                for user, assistant in turns:
                    lines.append(f"[yellow]You:[/yellow] {user[:120]}")
                    lines.append(f"[cyan]JARVIS:[/cyan] {assistant[:200]}")
                    lines.append("")
                self.console.print(
                    Panel(
                        "\n".join(lines),
                        title="Recent History",
                        border_style="dim",
                    )
                )

        elif command == "/clear":
            self.agent.reset_history()
            self.console.print("[dim]Conversation history cleared.[/dim]")

        elif command == "/think":
            self.cfg.ui.show_thinking = not self.cfg.ui.show_thinking
            state = "ON" if self.cfg.ui.show_thinking else "OFF"
            self.console.print(f"[dim]Thinking display: {state}[/dim]")

        elif command == "/pull":
            if len(parts) < 2:
                self.console.print("[red]Usage: /pull <model-name>[/red]")
                return
            model_name = parts[1]
            self.console.print(f"[dim]Pulling {model_name}…[/dim]")
            async for status in self.llm.pull_model(model_name):
                self.console.print(f"[dim]{status}[/dim]")
            self.console.print(f"[cyan]Done pulling {model_name}.[/cyan]")

        elif command in ("/exit", "/quit"):
            self._running = False

        else:
            self.console.print(
                f"[dim]Unknown command: {command}. Type /help for help.[/dim]"
            )
