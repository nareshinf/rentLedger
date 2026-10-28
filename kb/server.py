"""MCP server exposing search_kb over the local knowledge base. Run: python kb/server.py"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # `python kb/server.py` puts kb/, not the repo root, on sys.path
    sys.path.insert(0, str(ROOT))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from kb.embedding import KbDependencyError, default_embedder  # noqa: E402
from kb.store import EmbedderMismatchError, EmptyIndexError, KnowledgeBase  # noqa: E402

KINDS = ("doc", "design", "code")

server = MCPServer("kb", instructions="Semantic search over RentLedger docs, designs and code.")


def _kb_path() -> Path:
    return Path(os.environ.get("RENTLEDGER_KB_PATH", ROOT / ".kb"))


@server.tool()
def search_kb(query: str, k: int = 5, kind: str | None = None) -> list[dict]:
    """Search the RentLedger knowledge base (docs/, docs/design/, app/).

    Returns the top k chunks, best first, each with path, title (heading trail or code
    symbol), kind (doc, design or code), text and score. Filter with kind if given.
    """
    if not query.strip():
        raise ToolError("query must not be empty")
    if not 1 <= k <= 20:
        raise ToolError("k must be between 1 and 20")
    if kind is not None and kind not in KINDS:
        raise ToolError(f"kind must be one of {', '.join(KINDS)}")
    try:
        hits = KnowledgeBase(_kb_path(), default_embedder()).search(query, k, kind)
    except (EmptyIndexError, EmbedderMismatchError, KbDependencyError) as exc:
        raise ToolError(str(exc)) from exc
    return [
        {"path": h.path, "title": h.title, "kind": h.kind, "text": h.text, "score": h.score}
        for h in hits
    ]


if __name__ == "__main__":  # pragma: no cover - stdio entry point used by .mcp.json
    server.run("stdio")
