"""Jarvis Brain — the central coordinator that ties LLM, memory, and agents together."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Generator

from jarvis.agents.orchestrator import Orchestrator
from jarvis.config import JarvisConfig
from jarvis.core.llm import LLM
from jarvis.memory.store import MemoryStore

log = logging.getLogger(__name__)


class Brain:
    """Central nervous system of Jarvis.

    Combines the LLM, persistent memory, and multi-agent orchestration
    into a single coherent interface.
    """

    def __init__(self, config: JarvisConfig | None = None) -> None:
        self.config = config or JarvisConfig()
        self.config.ensure_dirs()

        self.llm = LLM(self.config.model)
        self.memory = MemoryStore(self.config.memory)
        self.orchestrator = Orchestrator(self.llm, self.config.agents)

        self.session_id = uuid.uuid4().hex[:12]
        self.memory.open()
        self._last_msg_id: int | None = None

    def close(self) -> None:
        self.memory.close()

    def _build_system_messages(self) -> list[dict]:
        """Construct system prompt including improvement context."""
        parts = [self.config.system_prompt]

        improvement = self.memory.get_improvement_context()
        if improvement:
            parts.append(improvement)

        knowledge_summary = self._relevant_knowledge_prompt()
        if knowledge_summary:
            parts.append(knowledge_summary)

        return [{"role": "system", "content": "\n\n".join(parts)}]

    def _relevant_knowledge_prompt(self) -> str:
        """Quick check for potentially relevant learned knowledge."""
        history = self.memory.get_history(self.session_id, limit=3)
        if not history:
            return ""
        last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
        if not last_user:
            return ""
        hits = self.memory.search_knowledge(last_user[:80], limit=3)
        if not hits:
            return ""
        return "Relevant knowledge you previously learned:\n" + "\n".join(
            f"- [{h['topic']}] {h['content'][:200]}" for h in hits
        )

    def ask(self, user_input: str) -> str:
        """Synchronous ask — returns the full response."""
        self._last_msg_id = self.memory.save_message(self.session_id, "user", user_input)

        delegated, agent_results = self.orchestrator.run(user_input)

        if delegated and isinstance(agent_results, list):
            combined = self._synthesize_agent_results(user_input, agent_results)
            self.memory.save_message(self.session_id, "assistant", combined)
            return combined

        messages = self._build_system_messages() + self.memory.get_history(self.session_id)
        resp = self.llm.chat(messages)
        answer = resp.message.content
        self.memory.save_message(self.session_id, "assistant", answer)
        return answer

    def ask_stream(self, user_input: str) -> Generator[str, None, None]:
        """Streaming ask — yields tokens as they arrive."""
        self._last_msg_id = self.memory.save_message(self.session_id, "user", user_input)

        delegated, agent_results = self.orchestrator.run(user_input)
        if delegated and isinstance(agent_results, list):
            combined = self._synthesize_agent_results(user_input, agent_results)
            self.memory.save_message(self.session_id, "assistant", combined)
            yield combined
            return

        messages = self._build_system_messages() + self.memory.get_history(self.session_id)
        chunks: list[str] = []
        for part in self.llm.chat(messages, stream=True):
            token = part.message.content
            if token:
                chunks.append(token)
                yield token
        full = "".join(chunks)
        self.memory.save_message(self.session_id, "assistant", full)

    def _synthesize_agent_results(self, original_query: str, results: list[dict[str, str]]) -> str:
        """Ask the LLM to unify the outputs of multiple agents into a cohesive answer."""
        agent_text = "\n\n".join(
            f"=== Agent: {r['agent']} ===\n{r['result']}" for r in results
        )
        synthesis_prompt = (
            f"The user asked: {original_query}\n\n"
            f"Several specialist agents produced the following outputs:\n\n{agent_text}\n\n"
            "Synthesize these into a single, clear, well-structured answer for the user."
        )
        messages = self._build_system_messages() + [{"role": "user", "content": synthesis_prompt}]
        resp = self.llm.chat(messages)
        return resp.message.content

    def learn(self, topic: str, content: str, source: str | None = None) -> None:
        """Explicitly teach Jarvis something new."""
        self.memory.store_knowledge(topic, content, source)

    def rate_last(self, rating: int, comment: str = "") -> None:
        """Rate the last assistant response (1-5) for self-improvement feedback."""
        if self._last_msg_id is not None:
            self.memory.save_feedback(self._last_msg_id, rating, comment)

    def stats(self) -> dict[str, Any]:
        return self.memory.get_stats()
