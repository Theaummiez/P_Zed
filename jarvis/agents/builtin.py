"""Built-in specialized agents that Jarvis can delegate to."""

from __future__ import annotations

from typing import Any

from jarvis.agents.base import BaseAgent
from jarvis.core.llm import LLM


class SummaryAgent(BaseAgent):
    name = "summarizer"
    description = "Summarize long text into concise bullet points"

    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        prompt = f"Summarize the following text into concise bullet points:\n\n{task}"
        resp = self.llm.chat([{"role": "user", "content": prompt}])
        return resp.message.content


class CodeAgent(BaseAgent):
    name = "coder"
    description = "Write, review, or explain code"

    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        system = (
            "You are a senior software engineer. Write clean, efficient code. "
            "Always include brief explanations of your design choices."
        )
        resp = self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ])
        return resp.message.content


class ResearchAgent(BaseAgent):
    name = "researcher"
    description = "Break down a topic and provide a structured analysis"

    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        system = (
            "You are a research analyst. Break down the topic into key areas, "
            "present facts, and cite reasoning. Be thorough but concise."
        )
        resp = self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ])
        return resp.message.content


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Create step-by-step plans for complex tasks"

    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        system = (
            "You are a project planner. Create detailed, actionable step-by-step plans. "
            "Include priorities, dependencies, and time considerations."
        )
        resp = self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ])
        return resp.message.content


class CriticAgent(BaseAgent):
    name = "critic"
    description = "Review and critique ideas, text, or code for quality"

    def run(self, task: str, context: dict[str, Any] | None = None) -> str:
        system = (
            "You are a constructive critic. Identify strengths and weaknesses. "
            "Provide specific, actionable improvement suggestions."
        )
        resp = self.llm.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ])
        return resp.message.content
