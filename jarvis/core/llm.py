"""Thin wrapper around the Ollama Python SDK for local LLM inference."""

from __future__ import annotations

import logging
from typing import Generator

import ollama
from ollama import ChatResponse

from jarvis.config import ModelConfig

log = logging.getLogger(__name__)


class LLM:
    """Manages communication with a locally-running Ollama model."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self._client = ollama.Client()
        self._active_model: str | None = None

    def _ensure_model(self, model: str | None = None) -> str:
        """Pull the model if it isn't already available locally."""
        name = model or self.config.name
        try:
            self._client.show(name)
        except ollama.ResponseError:
            log.info("Model %s not found locally — pulling (this may take a while)…", name)
            self._client.pull(name)
        self._active_model = name
        return name

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        stream: bool = False,
    ) -> ChatResponse | Generator:
        name = self._ensure_model(model)
        opts = {"temperature": temperature or self.config.temperature}

        if stream:
            return self._client.chat(
                model=name,
                messages=messages,
                options=opts,
                stream=True,
            )

        return self._client.chat(
            model=name,
            messages=messages,
            options=opts,
        )

    def generate(self, prompt: str, *, model: str | None = None) -> str:
        """Simple single-turn generation (convenience wrapper)."""
        name = self._ensure_model(model)
        resp = self._client.generate(model=name, prompt=prompt)
        return resp["response"]

    def list_local_models(self) -> list[str]:
        return [m["name"] for m in self._client.list().get("models", [])]
