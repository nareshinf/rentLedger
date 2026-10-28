"""AC5 with the real embedding model (HLD decision K1).

Runs only when sentence-transformers is installed and all-MiniLM-L6-v2 is already in the local
Hugging Face cache; it never downloads anything. CI does neither, so there it is skipped.
"""

import os

import pytest

from kb import index
from kb.store import KnowledgeBase

pytestmark = [pytest.mark.jira("REN-6"), pytest.mark.kb_model]

QUESTION = "How is a lease balance calculated?"
BALANCE_RULE_DOC = "docs/design/REN-5-hld.md"


@pytest.fixture
def real_embedder(monkeypatch):
    monkeypatch.setitem(os.environ, "HF_HUB_OFFLINE", "1")
    monkeypatch.delenv("RENTLEDGER_KB_EMBEDDER", raising=False)
    pytest.importorskip("sentence_transformers", reason="install with: pip install -e '.[kb]'")
    from kb.embedding import SentenceTransformerEmbedder

    try:
        return SentenceTransformerEmbedder()
    except Exception as exc:  # model not cached locally → offline load fails
        pytest.skip(f"embedding model not cached locally: {exc}")


def test_ac5_balance_question_finds_balance_rule_doc(root, tmp_path, real_embedder):
    chunks, skipped = index.build_chunks(root)
    assert skipped == []
    kb = KnowledgeBase(tmp_path / ".kb", real_embedder)
    kb.sync(chunks)

    hits = kb.search(QUESTION, k=3)
    print("\nAC5 top 3:", *(f"{h.score:.3f} {h.path} :: {h.title}" for h in hits), sep="\n  ")
    assert BALANCE_RULE_DOC in [h.path for h in hits]
