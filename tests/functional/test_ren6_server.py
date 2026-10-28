import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from kb import embedding
from kb.chunking import Chunk
from kb.embedding import HashingEmbedder
from kb.server import server
from kb.store import KnowledgeBase

pytestmark = pytest.mark.jira("REN-6")


@pytest.fixture
def kb_path(tmp_path, monkeypatch):
    path = tmp_path / ".kb"
    monkeypatch.setenv("RENTLEDGER_KB_PATH", str(path))
    monkeypatch.setenv("RENTLEDGER_KB_EMBEDDER", "hashing")
    embedding.default_embedder.cache_clear()
    yield path
    embedding.default_embedder.cache_clear()


@pytest.fixture
def indexed(kb_path):
    chunks = [
        Chunk(
            path=f"docs/design/d{i}.md",
            title=f"Design {i}",
            kind="design",
            text=f"lease balance note {i}",
            ordinal=0,
        )
        for i in range(6)
    ] + [
        Chunk(
            path="app/services/balance.py",
            title="compute_balance",
            kind="code",
            text="def compute_balance(): ...",
            ordinal=0,
        )
    ]
    KnowledgeBase(kb_path, HashingEmbedder()).sync(chunks)
    return kb_path


def _call(**arguments):
    result = asyncio.run(server.call_tool("search_kb", arguments))
    return result.structured_content["result"]


def test_ac4_search_kb_returns_top_k_with_path_title_text(indexed):
    hits = _call(query="lease balance", k=3)
    assert len(hits) == 3
    for hit in hits:
        assert set(hit) == {"path", "title", "kind", "text", "score"}
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_ac4_search_kb_default_k_is_5(indexed):
    assert len(_call(query="lease balance")) == 5


def test_ac4_search_kb_kind_filter(indexed):
    hits = _call(query="balance", k=5, kind="code")
    assert [(h["path"], h["title"]) for h in hits] == [
        ("app/services/balance.py", "compute_balance")
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"query": "x", "k": 0}, "k must be between 1 and 20"),
        ({"query": "x", "k": 21}, "k must be between 1 and 20"),
        ({"query": "x", "kind": "x"}, "kind must be one of doc, design, code"),
        ({"query": "   "}, "query must not be empty"),
    ],
)
def test_ac4_search_kb_rejects_bad_arguments(indexed, arguments, message):
    with pytest.raises(ToolError, match=message):
        _call(**arguments)


def test_ac4_search_kb_empty_index_tells_you_to_run_indexer(kb_path):
    with pytest.raises(ToolError, match="python kb/index.py"):
        _call(query="anything")


def test_ac4_search_kb_listed_by_server():
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert "search_kb" in tools
    assert set(tools["search_kb"].input_schema["properties"]) == {"query", "k", "kind"}
