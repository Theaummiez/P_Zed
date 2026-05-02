"""Load user-defined skills from Markdown files under the workspace (Skills/)."""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_SKILLS_DIR = "Skills"
PER_FILE_CAP = 12_000


def _parse_simple_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    """Split optional YAML-like --- ... --- header from body. Values are plain strings."""
    if not raw.startswith("---"):
        return {}, raw
    m = re.match(r"^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n([\s\S]*)$", raw.strip())
    if not m:
        return {}, raw
    header, body = m.group(1), m.group(2)
    meta: dict[str, str] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    return meta, body


def _meta_always(meta: dict[str, str]) -> bool:
    v = meta.get("always", "").lower()
    return v in ("true", "yes", "1", "on")


def _meta_keywords(meta: dict[str, str]) -> list[str]:
    raw = meta.get("keywords") or meta.get("match") or ""
    return [k.strip().lower() for k in raw.replace(";", ",").split(",") if k.strip()]


def skill_matches_user(meta: dict[str, str], user_lower: str) -> bool:
    """Whether this skill applies to the user message."""
    if _meta_always(meta):
        return True
    kws = _meta_keywords(meta)
    if not kws:
        return True
    return any(kw in user_lower for kw in kws)


def load_skills_markdown(
    workspace_root: Path,
    user_message: str,
    *,
    skills_subdir: str = DEFAULT_SKILLS_DIR,
    max_total_chars: int = 16_000,
    enabled: bool = True,
) -> str:
    """
    Concatenate relevant skill bodies into one system-injection string.
    Skills are *.md under workspace_root/skills_subdir (recursive, sorted by path).
    """
    if not enabled:
        return ""

    root = workspace_root.resolve()
    skills_dir = root / skills_subdir
    if not skills_dir.is_dir():
        alt = root / skills_subdir.lower()
        if alt.is_dir():
            skills_dir = alt
        else:
            return ""

    user_lower = user_message.lower()
    chunks: list[tuple[str, str]] = []

    for path in sorted(skills_dir.rglob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            raw_full = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta, body = _parse_simple_frontmatter(raw_full.strip())
        if not body.strip():
            continue
        if not skill_matches_user(meta, user_lower):
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path.name
        title_line = (meta.get("title") or path.stem).strip()
        body_trim = body.strip()
        if len(body_trim) > PER_FILE_CAP:
            body_trim = body_trim[:PER_FILE_CAP] + "\n… [truncated]"
        chunks.append((str(rel).replace("\\", "/"), f"### Skill: {title_line}\n{body_trim}"))

    if not chunks:
        return ""

    out_parts: list[str] = []
    total = 0
    header = (
        "The following USER SKILLS are permanent instructions you must follow "
        "(same role as project rules). They override generic habits when they conflict.\n\n"
    )
    total += len(header)

    for rel_path, block in chunks:
        piece = f"<!-- {rel_path} -->\n{block}\n\n"
        if total + len(piece) > max_total_chars:
            out_parts.append("\n… [more skills omitted: raise ZEDO_SKILLS_MAX_CHARS]\n")
            break
        out_parts.append(piece)
        total += len(piece)

    return header + "".join(out_parts).strip()
