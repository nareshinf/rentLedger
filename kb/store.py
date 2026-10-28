"""Chroma-backed vector store: idempotent sync and read-only search."""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings
from chromadb.errors import NotFoundError

from kb.chunking import Chunk
from kb.embedding import Embedder

COLLECTION = "rentledger"
BATCH = 256


class EmptyIndexError(Exception):
    def __init__(self) -> None:
        super().__init__("Knowledge base is empty — run `python kb/index.py`")


class EmbedderMismatchError(Exception):
    pass


@dataclass(frozen=True)
class Hit:
    path: str
    title: str
    kind: str
    text: str
    score: float


@dataclass(frozen=True)
class SyncResult:
    indexed: int
    removed: int


class KnowledgeBase:
    def __init__(self, path: Path, embedder: Embedder):
        self.path = Path(path)
        self.embedder = embedder

    def _client(self):
        # Telemetry off: the KB must never make network calls (CLAUDE.md test rule).
        return chromadb.PersistentClient(
            path=str(self.path), settings=Settings(anonymized_telemetry=False)
        )

    def _existing(self, client):
        try:
            return client.get_collection(COLLECTION, embedding_function=None)
        except NotFoundError:
            return None

    def sync(self, chunks: list[Chunk]) -> SyncResult:
        ids = [c.id for c in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk ids")
        client = self._client()
        existing = self._existing(client)
        if existing is not None and existing.metadata.get("embedder") != self.embedder.name:
            client.delete_collection(COLLECTION)  # never mix vectors from different models
        collection = client.get_or_create_collection(
            COLLECTION,
            metadata={"hnsw:space": "cosine", "embedder": self.embedder.name},
            embedding_function=None,
        )
        before = set(collection.get(include=[])["ids"])
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            collection.upsert(
                ids=[c.id for c in batch],
                embeddings=self.embedder.embed([f"{c.title}\n{c.text}" for c in batch]),
                documents=[c.text for c in batch],
                metadatas=[{"path": c.path, "title": c.title, "kind": c.kind} for c in batch],
            )
        stale = sorted(before - set(ids))
        if stale:
            collection.delete(ids=stale)
        return SyncResult(indexed=len(chunks), removed=len(stale))

    def count(self) -> int:
        collection = self._existing(self._client())
        return 0 if collection is None else collection.count()

    def search(self, query: str, k: int, kind: str | None = None) -> list[Hit]:
        collection = self._existing(self._client())
        if collection is None or collection.count() == 0:
            raise EmptyIndexError()
        built_with = collection.metadata.get("embedder")
        if built_with != self.embedder.name:
            raise EmbedderMismatchError(
                f"Index built with {built_with} but searching with {self.embedder.name}"
                " — re-run `python kb/index.py`"
            )
        result = collection.query(
            query_embeddings=self.embedder.embed([query]),
            n_results=min(k, collection.count()),
            where={"kind": kind} if kind else None,
            include=["documents", "metadatas", "distances"],
        )
        return [
            Hit(meta["path"], meta["title"], meta["kind"], doc, round(1 - distance, 3))
            for doc, meta, distance in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0], strict=True
            )
        ]
