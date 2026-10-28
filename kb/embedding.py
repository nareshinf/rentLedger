"""Text embedders: the real sentence-transformers model, and a deterministic one for tests."""

import functools
import hashlib
import math
import os
import re
from typing import Protocol

DEFAULT_MODEL = "all-MiniLM-L6-v2"
_TOKEN = re.compile(r"[a-z0-9]+")


class KbDependencyError(RuntimeError):
    pass


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Bag-of-words hashed into a fixed vector. No network, no model: for tests and CI only."""

    name = "hashing-v1"
    dim = 512

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            vector[int(hashlib.sha1(token.encode()).hexdigest()[:8], 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            vector[0], norm = 1.0, 1.0
        return [v / norm for v in vector]


class SentenceTransformerEmbedder:  # pragma: no cover - needs the [kb] extra; see kb_model test
    def __init__(self, model: str = DEFAULT_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise KbDependencyError(
                "sentence-transformers is not installed; run: pip install -e '.[kb]'"
            ) from exc
        self.name = f"st:{model}"
        self._model = SentenceTransformer(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()


@functools.cache
def default_embedder() -> Embedder:
    if os.environ.get("RENTLEDGER_KB_EMBEDDER") == "hashing":
        return HashingEmbedder()
    try:
        import sentence_transformers  # noqa: F401
    except ImportError as exc:
        raise KbDependencyError(
            "sentence-transformers is not installed; run: pip install -e '.[kb]'"
        ) from exc
    return SentenceTransformerEmbedder()  # pragma: no cover - needs the [kb] extra
