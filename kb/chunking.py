"""Split docs and code into searchable chunks (one per heading, function, class or module)."""

import ast
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Chunk:
    path: str
    title: str
    kind: str
    text: str
    ordinal: int

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.path}\0{self.title}\0{self.ordinal}".encode()).hexdigest()


def kind_for(path: str) -> str:
    if path.startswith("docs/design/"):
        return "design"
    if path.startswith("docs/"):
        return "doc"
    if path.startswith("app/"):
        return "code"
    raise ValueError(f"{path} is outside docs/ and app/")


def _numbered(path: str, sections: list[tuple[str, str]]) -> list[Chunk]:
    kind = kind_for(path)
    seen: Counter[str] = Counter()
    chunks = []
    for title, text in sections:
        chunks.append(Chunk(path, title, kind, text, seen[title]))
        seen[title] += 1
    return chunks


def markdown_chunks(path: str, text: str) -> list[Chunk]:
    sections: list[tuple[str, str]] = []
    trail: list[tuple[int, str]] = []
    title, heading, body = PurePosixPath(path).name, None, []
    in_fence = False

    def flush() -> None:
        content = "\n".join(body).strip()
        if content:
            sections.append((title, f"{heading}\n{content}" if heading else content))

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        trail = [(lvl, name) for lvl, name in trail if lvl < level] + [(level, match.group(2))]
        title, heading, body = " › ".join(name for _, name in trail), line, []
    flush()
    return _numbered(path, sections)


def python_chunks(path: str, text: str) -> list[Chunk]:
    tree = ast.parse(text)
    lines = text.splitlines()

    def source(node: ast.stmt) -> str:
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
        return "\n".join(lines[first - 1 : node.end_lineno])

    sections, module_parts = [], []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            sections.append((node.name, source(node)))
        elif not isinstance(node, ast.Import | ast.ImportFrom):
            module_parts.append(source(node))
    if module_parts:
        sections.insert(0, ("<module>", "\n".join(module_parts)))
    return _numbered(path, sections)


def chunk_file(path: str, text: str) -> list[Chunk]:
    suffix = PurePosixPath(path).suffix
    if suffix == ".md":
        return markdown_chunks(path, text)
    if suffix == ".py":
        return python_chunks(path, text)
    raise ValueError(f"Unsupported file type: {path}")
