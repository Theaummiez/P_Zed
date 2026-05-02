"""Sandboxed file access under a single workspace root (no path escape)."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

READ_MAX_BYTES = 512 * 1024
LIST_MAX_ENTRIES = 400
WRITE_MAX_BYTES = 2 * 1024 * 1024

# WordPress-friendly / common web & office formats (create & overwrite)
ALLOWED_WRITE_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".html",
        ".htm",
        ".csv",
        ".tsv",
        ".json",
        ".xml",
        ".css",
        ".docx",
        ".pdf",
    }
)

TEXT_WRITE_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".html",
        ".htm",
        ".csv",
        ".tsv",
        ".json",
        ".xml",
        ".css",
    }
)


class WorkspaceError(ValueError):
    pass


def _safe_relative(rel: str) -> Path:
    if not rel or not isinstance(rel, str):
        return Path()
    p = Path(rel.strip())
    if p.is_absolute():
        raise WorkspaceError("paths must be relative to the workspace root")
    parts = p.parts
    if ".." in parts:
        raise WorkspaceError("path must not contain '..'")
    return p


def resolve_under_root(root: Path, relative: str) -> Path:
    root = root.resolve()
    rel = _safe_relative(relative)
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as e:
        raise WorkspaceError("path escapes workspace sandbox") from e
    return candidate


def normalize_workspace_relative(rel: str) -> str:
    """Map leading docs/ to Docs/ so lowercase paths match the repo folder on disk."""
    r = rel.strip().replace("\\", "/")
    if len(r) >= 5 and r[:5].lower() == "docs/" and not r.startswith("Docs/"):
        return "Docs/" + r[5:]
    return r


def list_workspace(root: Path, relative_dir: str = "", *, recursive: bool = False) -> str:
    """List files under relative_dir (default root). One level unless recursive."""
    relative_dir = normalize_workspace_relative(relative_dir)
    base = resolve_under_root(root, relative_dir)
    if not base.exists():
        return json.dumps({"error": "path does not exist", "path": relative_dir})
    if not base.is_dir():
        return json.dumps({"error": "not a directory", "path": relative_dir})

    entries: list[dict[str, str]] = []
    if recursive:
        count = 0
        for dirpath, dirnames, filenames in os.walk(base, topdown=True):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith("."):
                    continue
                fp = Path(dirpath) / name
                try:
                    rel = fp.relative_to(root)
                except ValueError:
                    continue
                entries.append({"path": str(rel).replace("\\", "/"), "type": "file"})
                count += 1
                if count >= LIST_MAX_ENTRIES:
                    break
            if count >= LIST_MAX_ENTRIES:
                break
    else:
        for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith("."):
                continue
            try:
                rel = child.relative_to(root)
            except ValueError:
                continue
            t = "dir" if child.is_dir() else "file"
            entries.append({"path": str(rel).replace("\\", "/"), "type": t})

    return json.dumps({"root": str(root), "entries": entries}, ensure_ascii=False)


def _read_docx_text(path: Path) -> str:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as e:
        raise WorkspaceError("python-docx not installed; pip install python-docx") from e
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError as e:
        raise WorkspaceError("pypdf not installed; pip install pypdf") from e
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n\n".join(parts)


def read_workspace_file(root: Path, relative_path: str) -> str:
    path = resolve_under_root(root, normalize_workspace_relative(relative_path))
    if not path.is_file():
        return json.dumps({"error": "not a file or missing", "path": relative_path})
    size = path.stat().st_size
    if size > READ_MAX_BYTES:
        return json.dumps(
            {
                "error": "file too large",
                "path": relative_path,
                "max_bytes": READ_MAX_BYTES,
                "size": size,
            }
        )
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            text = _read_pdf_text(path)
            return json.dumps({"path": relative_path, "content": text, "format": "pdf_text"})
        except WorkspaceError as e:
            return json.dumps({"error": str(e), "path": relative_path})
    if ext == ".docx":
        try:
            text = _read_docx_text(path)
            return json.dumps({"path": relative_path, "content": text, "format": "docx_text"})
        except WorkspaceError as e:
            return json.dumps({"error": str(e), "path": relative_path})

    text = path.read_text(encoding="utf-8", errors="replace")
    return json.dumps({"path": relative_path, "content": text}, ensure_ascii=False)


def _write_docx(path: Path, content: str) -> None:
    try:
        from docx import Document  # type: ignore[import-untyped]
    except ImportError as e:
        raise WorkspaceError("python-docx not installed; pip install python-docx") from e
    doc = Document()
    for block in content.replace("\r\n", "\n").split("\n"):
        doc.add_paragraph(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def _write_pdf(path: Path, content: str) -> None:
    try:
        from fpdf import FPDF  # type: ignore[import-untyped]
    except ImportError as e:
        raise WorkspaceError("fpdf2 not installed; pip install fpdf2") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    w = pdf.w - pdf.l_margin - pdf.r_margin
    for line in content.replace("\r\n", "\n").split("\n"):
        pdf.multi_cell(w, 6, line or " ")
    pdf.output(str(path))


def write_workspace_file(root: Path, relative_path: str, content: str) -> str:
    """Create or overwrite allowed file types; folders created as needed."""
    if not isinstance(content, str):
        content = str(content)
    if len(content.encode("utf-8")) > WRITE_MAX_BYTES:
        return json.dumps({"error": "content too large", "max_bytes": WRITE_MAX_BYTES})
    rel_norm = normalize_workspace_relative(relative_path)
    ext = Path(rel_norm).suffix.lower()
    if ext not in ALLOWED_WRITE_EXTENSIONS:
        return json.dumps(
            {
                "error": "extension not allowed",
                "path": relative_path,
                "allowed": sorted(ALLOWED_WRITE_EXTENSIONS),
            }
        )
    path = resolve_under_root(root, rel_norm)
    if path.exists() and not path.is_file():
        return json.dumps({"error": "path exists and is not a file", "path": relative_path})

    try:
        if ext in TEXT_WRITE_EXTENSIONS:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        elif ext == ".docx":
            _write_docx(path, content)
        elif ext == ".pdf":
            _write_pdf(path, content)
        else:
            return json.dumps({"error": f"unhandled extension {ext}", "path": relative_path})
    except WorkspaceError as e:
        return json.dumps({"error": str(e), "path": relative_path})
    except Exception as e:
        return json.dumps({"error": str(e), "path": relative_path})

    nbytes = path.stat().st_size if path.exists() else len(content.encode("utf-8"))
    return json.dumps({"ok": True, "path": rel_norm, "bytes": nbytes})


def write_workspace_markdown(root: Path, relative_path: str, content: str) -> str:
    """Backward-compatible: only .md via general writer."""
    return write_workspace_file(root, relative_path, content)


def delete_workspace_file(root: Path, relative_path: str) -> str:
    """Delete a single file under the sandbox (not directories)."""
    rel_norm = normalize_workspace_relative(relative_path)
    path = resolve_under_root(root, rel_norm)
    if not path.exists():
        return json.dumps({"error": "not found", "path": relative_path})
    if not path.is_file():
        return json.dumps(
            {"error": "path is not a file (use empty dir cleanup manually)", "path": relative_path}
        )
    try:
        path.unlink()
    except OSError as e:
        return json.dumps({"error": str(e), "path": relative_path})
    return json.dumps({"ok": True, "deleted": True, "path": rel_norm})


OLLAMA_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "workspace_delete_file",
            "description": "Delete one file under the workspace (files only, not directories). Required for any delete/remove request.",
            "parameters": {
                "type": "object",
                "required": ["relative_path"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "File path relative to workspace root (e.g. Docs/sport/old.docx).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_list",
            "description": "List files and folders inside the workspace sandbox. Paths are relative to project root; cannot escape.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Directory relative to workspace (empty string = root).",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true, list files recursively (capped); if false, one level only.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read_file",
            "description": "Read a file under the workspace. Text formats as UTF-8; .pdf and .docx return extracted plain text.",
            "parameters": {
                "type": "object",
                "required": ["relative_path"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "File path relative to workspace root.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write_file",
            "description": "Create or overwrite a file under the workspace. Allowed extensions: .md .txt .html .htm .csv .tsv .json .xml .css .docx .pdf — plain text content (for Word/PDF the text is converted). Prefer Docs/ for user documents.",
            "parameters": {
                "type": "object",
                "required": ["relative_path", "content"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Target path with allowed extension, relative to workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "File body: markdown/html/csv/json/xml/css as text; for .docx/.pdf use plain text (line breaks preserved).",
                    },
                },
            },
        },
    },
]


def run_tool(root: Path, name: str, arguments: dict | str | None) -> str:
    args = arguments
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}

    try:
        if name == "workspace_list":
            rel = args.get("relative_path") or args.get("path") or ""
            rec = bool(args.get("recursive", False))
            return list_workspace(root, str(rel), recursive=rec)
        if name == "workspace_read_file":
            rp = args.get("relative_path") or args.get("path")
            if not rp:
                return json.dumps({"error": "missing relative_path"})
            return read_workspace_file(root, str(rp))
        if name in ("workspace_write_file", "workspace_write_markdown"):
            rp = args.get("relative_path") or args.get("path")
            content = args.get("content", "")
            if not rp:
                return json.dumps({"error": "missing relative_path"})
            return write_workspace_file(root, str(rp), str(content))
        if name == "workspace_delete_file":
            rp = args.get("relative_path") or args.get("path")
            if not rp:
                return json.dumps({"error": "missing relative_path"})
            return delete_workspace_file(root, str(rp))
    except WorkspaceError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool {name}"})
