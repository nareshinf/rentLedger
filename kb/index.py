"""Index docs/**/*.md and app/**/*.py into the local knowledge base in .kb/.

Usage: python kb/index.py [--root PATH]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `python kb/index.py` puts kb/, not the repo root, on sys.path
    sys.path.insert(0, str(ROOT))

from kb.chunking import Chunk, chunk_file  # noqa: E402
from kb.embedding import Embedder, KbDependencyError, default_embedder  # noqa: E402
from kb.store import KnowledgeBase  # noqa: E402

GLOBS = ("docs/**/*.md", "app/**/*.py")


def collect_files(root: Path) -> list[str]:
    return sorted({p.relative_to(root).as_posix() for g in GLOBS for p in root.glob(g)})


def build_chunks(root: Path) -> tuple[list[Chunk], list[str]]:
    chunks, skipped = [], []
    for rel in collect_files(root):
        try:
            chunks.extend(chunk_file(rel, (root / rel).read_text(encoding="utf-8")))
        except SyntaxError as exc:
            skipped.append(f"{rel} ({exc.msg}, line {exc.lineno})")
    return chunks, skipped


def main(argv: list[str] | None = None, embedder: Embedder | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    root = parser.parse_args(argv).root.resolve()

    chunks, skipped = build_chunks(root)
    try:
        kb = KnowledgeBase(root / ".kb", embedder or default_embedder())
    except KbDependencyError as exc:
        print(exc, file=sys.stderr)
        return 1
    result = kb.sync(chunks)

    files = len({c.path for c in chunks})
    print(
        f"Indexed {result.indexed} chunks from {files} files into .kb/"
        f" (removed {result.removed} stale)"
    )
    for item in skipped:
        print(f"Skipped {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
