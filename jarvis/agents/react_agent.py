"""
ReAct-style agent loop (Reason + Act).

The agent:
1. Receives the user message + memory context.
2. Calls the LLM, which may emit <tool_call> JSON blocks.
3. Executes the requested tool(s).
4. Feeds results back and loops until the model stops calling tools.
5. Streams the final answer token by token.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, List, Dict, Any, Optional, Callable

from jarvis.config.settings import JarvisConfig
from jarvis.core.llm import OllamaClient
from jarvis.core.prompts import build_system_prompt

logger = logging.getLogger(__name__)

# Regex to extract JSON from a <tool_call>…</tool_call> block
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE)
# Also handle raw JSON objects that look like {"name": ..., "arguments": ...}
_RAW_JSON_RE = re.compile(r"\{[^{}]*\"name\"\s*:\s*\"[^\"]+\"[^{}]*\"arguments\"\s*:[^{}]*\}", re.DOTALL)


def _extract_tool_calls(text: str) -> List[Dict[str, Any]]:
    calls = []
    for m in _TOOL_CALL_RE.finditer(text):
        try:
            calls.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            pass
    if not calls:
        for m in _RAW_JSON_RE.finditer(text):
            try:
                obj = json.loads(m.group(0))
                if "name" in obj:
                    calls.append(obj)
            except json.JSONDecodeError:
                pass
    return calls


def _strip_tool_calls(text: str) -> str:
    text = _TOOL_CALL_RE.sub("", text)
    return text.strip()


class ReactAgent:
    """
    Single ReAct agent that can call tools and accumulate multi-turn
    conversation history.
    """

    def __init__(
        self,
        cfg: JarvisConfig,
        llm: OllamaClient,
        tools: Dict[str, Any],          # name -> Tool instance
        memory,                          # MemoryStore instance
        model: Optional[str] = None,
        name: str = "JARVIS",
    ):
        self.cfg = cfg
        self.llm = llm
        self.tools = tools
        self.memory = memory
        self.model = model or cfg.ollama.primary_model
        self.name = name
        self._history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_stream(
        self,
        user_message: str,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_tool_result: Optional[Callable[[str, Any], None]] = None,
    ) -> AsyncIterator[str]:
        """
        Run the agent for one user turn, yielding response tokens.
        Tool calls happen silently; callbacks are fired for UI feedback.
        """
        # Retrieve relevant memories
        memory_ctx = await self.memory.retrieve_context(user_message)

        # Build tools description for the system prompt
        tools_json = self._tools_json()

        system = build_system_prompt(
            user_name=self.cfg.ui.user_name,
            tools_json=tools_json,
            extra_context=memory_ctx,
        )

        # Add user turn to history
        self._history.append({"role": "user", "content": user_message})

        messages = [{"role": "system", "content": system}] + self._history

        for iteration in range(self.cfg.agent.max_iterations):
            # ── Collect the full model response first (needed to detect tool calls)
            full_response = ""
            streaming_tokens: List[str] = []

            # Stream tokens but buffer them — we need the full text to detect
            # whether this is a final answer or a tool call
            async for tok in self.llm.chat_stream(messages, model=self.model):
                streaming_tokens.append(tok)
                full_response += tok

            # Check for thinking blocks and optionally strip
            display_response = full_response
            if not self.cfg.ui.show_thinking:
                display_response = re.sub(r"<think>[\s\S]*?</think>", "", full_response).strip()

            tool_calls = _extract_tool_calls(full_response)

            if not tool_calls:
                # Final answer — stream tokens to caller
                final_text = _strip_tool_calls(display_response)
                for tok in final_text:
                    yield tok
                # Save turn to memory
                self._history.append({"role": "assistant", "content": full_response})
                await self.memory.save_turn(user_message, full_response)
                return

            # ── Execute tool calls
            tool_results = []
            for call in tool_calls:
                tool_name = call.get("name", "")
                arguments = call.get("arguments", call.get("parameters", {}))
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except Exception:
                        arguments = {"input": arguments}

                if on_tool_call:
                    on_tool_call(tool_name, arguments)

                result = await self._execute_tool(tool_name, arguments)

                if on_tool_result:
                    on_tool_result(tool_name, result)

                tool_results.append({
                    "tool": tool_name,
                    "result": result,
                })

            # Add assistant message (with tool calls) to history
            messages.append({"role": "assistant", "content": full_response})
            # Feed tool results back
            results_text = "\n".join(
                f"Tool '{r['tool']}' returned:\n{r['result']}" for r in tool_results
            )
            messages.append({"role": "user", "content": f"[Tool results]\n{results_text}"})

        # Fallback if max iterations hit
        yield "\n[JARVIS] Reached max tool iterations. Here is what I know so far."

    async def run(self, user_message: str) -> str:
        parts = []
        async for tok in self.run_stream(user_message):
            parts.append(tok)
        return "".join(parts)

    def reset_history(self) -> None:
        self._history.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tools_json(self) -> str:
        specs = []
        for name, tool in self.tools.items():
            specs.append({
                "name": name,
                "description": tool.description,
                "parameters": tool.parameters,
            })
        return json.dumps(specs, indent=2)

    async def _execute_tool(self, name: str, arguments: dict) -> Any:
        if name not in self.tools:
            return f"Error: tool '{name}' not found."
        try:
            result = await self.tools[name].run(**arguments)
            return result
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return f"Error running tool '{name}': {e}"
