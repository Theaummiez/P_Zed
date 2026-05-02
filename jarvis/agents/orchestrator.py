"""
Multi-agent orchestrator.

When JARVIS decides a task should be parallelised, it calls the
`spawn_agents` tool. The orchestrator:
  1. Creates N lightweight sub-agents (each with their own tool set).
  2. Runs them concurrently with asyncio.gather.
  3. Aggregates results and returns them to the main agent.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from jarvis.config.settings import JarvisConfig
from jarvis.core.llm import OllamaClient
from jarvis.core.prompts import AGENT_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class SubTask:
    id: str
    description: str
    result: Optional[str] = None
    error: Optional[str] = None
    status: str = "pending"   # pending | running | done | failed


class SubAgent:
    """Minimal single-shot agent for a sub-task (no tool use, pure LLM)."""

    def __init__(self, llm: OllamaClient, model: str):
        self.llm = llm
        self.model = model

    async def run(self, task: str, context: str = "") -> str:
        prompt = AGENT_PROMPT.format(task=task)
        messages = [{"role": "system", "content": prompt}]
        if context:
            messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "user", "content": "Begin."})
        return await self.llm.chat(messages, model=self.model)


class Orchestrator:
    """
    Manages a pool of sub-agents running in parallel.
    """

    def __init__(self, cfg: JarvisConfig, llm: OllamaClient):
        self.cfg = cfg
        self.llm = llm

    async def run_tasks(
        self,
        tasks: List[Dict[str, str]],
        context: str = "",
    ) -> List[SubTask]:
        """
        Run a list of tasks in parallel, up to cfg.agent.max_agents at a time.

        Each task dict should have: {"id": str, "description": str}
        """
        sub_tasks = [
            SubTask(id=t.get("id", str(i)), description=t["description"])
            for i, t in enumerate(tasks)
        ]

        semaphore = asyncio.Semaphore(self.cfg.agent.max_agents)

        async def _run_one(st: SubTask) -> None:
            async with semaphore:
                st.status = "running"
                agent = SubAgent(self.llm, model=self.cfg.ollama.primary_model)
                try:
                    st.result = await asyncio.wait_for(
                        agent.run(st.description, context),
                        timeout=self.cfg.agent.timeout_seconds,
                    )
                    st.status = "done"
                except asyncio.TimeoutError:
                    st.error = "Sub-agent timed out."
                    st.status = "failed"
                except Exception as e:
                    st.error = str(e)
                    st.status = "failed"
                    logger.error("Sub-agent %s failed: %s", st.id, e)

        await asyncio.gather(*[_run_one(st) for st in sub_tasks])
        return sub_tasks

    def format_results(self, sub_tasks: List[SubTask]) -> str:
        lines = []
        for st in sub_tasks:
            status_icon = "✓" if st.status == "done" else "✗"
            lines.append(f"{status_icon} [{st.id}] {st.description}")
            if st.result:
                lines.append(f"   → {st.result.strip()}")
            if st.error:
                lines.append(f"   ✗ Error: {st.error}")
        return "\n".join(lines)
