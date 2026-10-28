import math
import sys

import pytest

from kb import embedding
from kb.embedding import HashingEmbedder, KbDependencyError

pytestmark = pytest.mark.jira("REN-6")


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_embedder_deterministic_and_normalised():
    embedder = HashingEmbedder()
    first, again = embedder.embed(["Lease balance"]), embedder.embed(["Lease balance"])
    assert first == again
    assert len(first[0]) == HashingEmbedder.dim
    assert math.isclose(math.sqrt(sum(v * v for v in first[0])), 1.0)


def test_hashing_embedder_similar_text_closer():
    a, b, c = HashingEmbedder().embed(
        ["lease balance charged paid", "balance of a lease", "tenant email address"]
    )
    assert _cos(a, b) > _cos(a, c)


def test_hashing_embedder_empty_text_nonzero():
    (vector,) = HashingEmbedder().embed(["!!!"])
    assert any(vector)


def test_default_embedder_env_selects_hashing(monkeypatch):
    monkeypatch.setenv("RENTLEDGER_KB_EMBEDDER", "hashing")
    embedding.default_embedder.cache_clear()
    try:
        assert embedding.default_embedder().name == "hashing-v1"
    finally:
        embedding.default_embedder.cache_clear()


def test_missing_sentence_transformers_gives_install_hint(monkeypatch):
    monkeypatch.delenv("RENTLEDGER_KB_EMBEDDER", raising=False)
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    embedding.default_embedder.cache_clear()
    try:
        with pytest.raises(KbDependencyError, match=r"pip install -e '\.\[kb\]'"):
            embedding.default_embedder()
    finally:
        embedding.default_embedder.cache_clear()
