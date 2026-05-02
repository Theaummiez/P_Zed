"""Locate the P_Zed / jarvis project root when resolving default workspace."""

from __future__ import annotations

from pathlib import Path


def is_jarvis_project_root(path: Path) -> bool:
    try:
        r = path.resolve()
    except OSError:
        return False
    return (r / "jarvis" / "__init__.py").is_file() and (r / "pyproject.toml").is_file()


def discover_project_root(start: Path | None = None) -> Path:
    """Walk upward from start (default cwd) until we find this repo (jarvis package + pyproject)."""
    start_path = (start or Path.cwd()).resolve()
    cur = start_path
    for _ in range(24):
        if is_jarvis_project_root(cur):
            return cur.resolve()
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    # Often cwd is a parent folder (e.g. …/Maison) while the repo is …/Maison/P_Zed
    guess = start_path / "P_Zed"
    if is_jarvis_project_root(guess):
        return guess.resolve()
    return start_path
