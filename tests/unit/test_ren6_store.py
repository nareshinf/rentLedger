import pytest

from kb.chunking import Chunk
from kb.embedding import HashingEmbedder
from kb.store import EmbedderMismatchError, EmptyIndexError, KnowledgeBase

pytestmark = pytest.mark.jira("REN-6")


def _chunk(path, title, text, kind="doc", ordinal=0):
    return Chunk(path=path, title=title, kind=kind, text=text, ordinal=ordinal)


CHUNKS = [
    _chunk("docs/design/b.md", "Balance", "balance equals charged minus paid", "design"),
    _chunk("docs/guide.md", "Tenants", "tenant email and phone", "doc"),
    _chunk("app/services/rent.py", "due_dates", "def due_dates(): monthly rent due day", "code"),
]


class OtherEmbedder(HashingEmbedder):
    name = "other-v1"


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(tmp_path / ".kb", HashingEmbedder())


def test_ac1_sync_persists_to_directory(tmp_path, kb):
    kb.sync(CHUNKS)
    assert (tmp_path / ".kb").is_dir()
    assert KnowledgeBase(tmp_path / ".kb", HashingEmbedder()).count() == 3


def test_ac3_sync_twice_is_idempotent(kb):
    first = kb.sync(CHUNKS)
    second = kb.sync(CHUNKS)
    assert (first.indexed, first.removed) == (3, 0)
    assert (second.indexed, second.removed) == (3, 0)
    assert kb.count() == 3


def test_ac3_changed_text_updates_in_place(kb):
    kb.sync(CHUNKS)
    changed = [*CHUNKS[:2], _chunk("app/services/rent.py", "due_dates", "NEW BODY", "code")]
    kb.sync(changed)
    assert kb.count() == 3
    hits = kb.search("NEW BODY", k=3, kind="code")
    assert [h.text for h in hits] == ["NEW BODY"]


def test_ac3_removed_chunks_are_deleted(kb):
    kb.sync(CHUNKS)
    result = kb.sync(CHUNKS[:1])
    assert (result.indexed, result.removed) == (1, 2)
    assert {h.path for h in kb.search("tenant email", k=5)} == {"docs/design/b.md"}


def test_ac3_embedder_change_rebuilds_collection(tmp_path, kb):
    kb.sync(CHUNKS)
    other = KnowledgeBase(tmp_path / ".kb", OtherEmbedder())
    other.sync(CHUNKS[:2])
    assert other.count() == 2
    assert other.search("balance", k=1)[0].path == "docs/design/b.md"


def test_sync_rejects_duplicate_ids(kb):
    with pytest.raises(ValueError, match="duplicate"):
        kb.sync([CHUNKS[0], CHUNKS[0]])


def test_ac4_search_returns_ranked_hits_with_fields(kb):
    kb.sync(CHUNKS)
    hits = kb.search("balance charged minus paid", k=2)
    assert len(hits) == 2
    top = hits[0]
    assert (top.path, top.title, top.kind) == ("docs/design/b.md", "Balance", "design")
    assert top.text == "balance equals charged minus paid"
    assert hits[0].score >= hits[1].score
    assert 0 < top.score <= 1


def test_ac4_kind_filter(kb):
    kb.sync(CHUNKS)
    assert {h.kind for h in kb.search("balance", k=5, kind="code")} == {"code"}


def test_ac4_k_larger_than_index(kb):
    kb.sync(CHUNKS)
    assert len(kb.search("anything", k=20)) == 3


def test_ac4_search_empty_or_missing_index_raises(tmp_path, kb):
    with pytest.raises(EmptyIndexError, match="python kb/index.py"):
        kb.search("x", k=1)
    kb.sync([])
    with pytest.raises(EmptyIndexError):
        kb.search("x", k=1)
    assert kb.count() == 0


def test_ac4_search_embedder_mismatch_raises_without_rebuilding(tmp_path, kb):
    kb.sync(CHUNKS)
    other = KnowledgeBase(tmp_path / ".kb", OtherEmbedder())
    with pytest.raises(EmbedderMismatchError, match="hashing-v1"):
        other.search("balance", k=1)
    assert kb.count() == 3
