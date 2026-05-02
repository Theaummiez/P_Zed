"""Multi-agent orchestrator — decomposes complex tasks and farms out sub-tasks."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from jarvis.agents.base import BaseAgent, get_agent, list_agents
from jarvis.config import AgentConfig
from jarvis.core.llm import LLM

log = logging.getLogger(__name__)

_DECOMPOSE_PROMPT = """You are a task decomposition engine.
Given a user request, decide whether it should be handled directly or split into sub-tasks for specialized agents.

Available agents:
{agents}

Respond with JSON only — no markdown fences, no explanation.

If the task is simple, return:
{{"direct": true}}

If it should be split, return:
{{"direct": false, "subtasks": [{{"agent": "<agent_name>", "task": "<specific sub-task description>"}}]}}

User request:
{task}"""


class Orchestrator:
    """Analyses incoming requests and optionally distributes work across agents."""

    def __init__(self, llm: LLM, config: AgentConfig) -> None:
        self.llm = llm
        self.config = config

    def should_delegate(self, task: str) -> dict | None:
        """Ask the LLM whether to delegate and, if so, to which agents."""
        agents_desc = "\n".join(f"- {a['name']}: {a['description']}" for a in list_agents())
        prompt = _DECOMPOSE_PROMPT.format(agents=agents_desc, task=task)

        raw = self.llm.generate(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]

        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Orchestrator could not parse decomposition — falling back to direct handling")
            return None

        if plan.get("direct", True):
            return None
        return plan

    def execute_plan(self, plan: dict) -> list[dict[str, str]]:
        """Run all sub-tasks, potentially in parallel."""
        subtasks: list[dict] = plan.get("subtasks", [])
        results: list[dict[str, str]] = []

        with ThreadPoolExecutor(max_workers=self.config.max_concurrent) as pool:
            futures = {}
            for st in subtasks:
                agent_name = st["agent"]
                task_desc = st["task"]
                try:
                    agent = get_agent(agent_name, self.llm)
                except KeyError:
                    results.append({"agent": agent_name, "result": f"[unknown agent: {agent_name}]"})
                    continue
                futures[pool.submit(agent.run, task_desc)] = agent_name

            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result(timeout=self.config.default_timeout)
                except Exception as exc:
                    result = f"[agent {agent_name} failed: {exc}]"
                results.append({"agent": agent_name, "result": result})

        return results

    def run(self, task: str) -> tuple[bool, str | list[dict[str, str]]]:
        """High-level entry: returns (delegated, result).

        If delegated is False, the caller should handle the task directly.
        If True, result is a list of agent outputs.
        """
        plan = self.should_delegate(task)
        if plan is None:
            return False, ""
        results = self.execute_plan(plan)
        return True, results
