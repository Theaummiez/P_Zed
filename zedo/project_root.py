"""Locate the P_Zed / zedo project root when resolving default workspace."""

from __future__ import annotations

from pathlib import Path


def is_zedo_project_root(path: Path) -> bool:
    try:
        r = path.resolve()
    except OSError:
        return False
    return (r / "zedo" / "__init__.py").is_file() and (r / "pyproject.toml").is_file()


def discover_project_root(start: Path | None = None) -> Path:
    """Walk upward from start (default cwd) until we find this repo (zedo package + pyproject)."""
    start_path = (start or Path.cwd()).resolve()
    cur = start_path
    for _ in range(24):
        if is_zedo_project_root(cur):
            return cur.resolve()
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    guess = start_path / "P_Zed"
    if is_zedo_project_root(guess):
        return guess.resolve()
    return start_path
