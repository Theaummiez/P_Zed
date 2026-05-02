"""
Web search (via DuckDuckGo — no API key needed) and URL fetch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

import httpx

from .base import Tool

logger = logging.getLogger(__name__)

_MAX_CONTENT = 6000


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web using DuckDuckGo (no API key required). "
        "Returns a list of titles, URLs, and snippets."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def run(self, query: str, max_results: int = 5) -> str:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return "Error: duckduckgo_search not installed. Run: pip install duckduckgo-search"

        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: list(DDGS().text(query, max_results=max_results)),
            )
            if not results:
                return "No results found."
            lines = []
            for r in results:
                lines.append(f"**{r.get('title', '')}**")
                lines.append(f"URL: {r.get('href', '')}")
                lines.append(r.get('body', ''))
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Search error: {e}"


class WebFetchTool(Tool):
    name = "web_fetch"
    description = (
        "Fetch the text content of a URL. "
        "Useful for reading articles, documentation, or web pages."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch."},
        },
        "required": ["url"],
    }

    async def run(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                content_type = r.headers.get("content-type", "")
                if "html" in content_type:
                    text = _html_to_text(r.text)
                else:
                    text = r.text
                if len(text) > _MAX_CONTENT:
                    text = text[:_MAX_CONTENT] + "\n... [truncated]"
                return text
        except Exception as e:
            return f"Fetch error: {e}"


def _html_to_text(html: str) -> str:
    """Very lightweight HTML-to-text stripping."""
    try:
        from html.parser import HTMLParser

        class MLStripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self._parts: List[str] = []
                self._skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "footer"):
                    self._skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "footer"):
                    self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    stripped = data.strip()
                    if stripped:
                        self._parts.append(stripped)

        s = MLStripper()
        s.feed(html)
        return " ".join(s._parts)
    except Exception:
        import re
        return re.sub(r"<[^>]+>", " ", html)
