"""Dense retriever backed by a sentence-transformers model, e.g. the fine-tuned multilingual-e5-large
from the notebook (`kinya-e5-large/best`). The heavy imports happen lazily so the API starts without
torch installed when a lighter retriever is configured."""
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from mfasha.domain.errors import ServiceUnavailableError
from mfasha.domain.models import Passage, RetrievalHit
from mfasha.interfaces import Retriever


class EmbeddingRetriever(Retriever):
    name = "embedding"

    def __init__(self, model_path: str, query_prefix: str = "query: ",
                 passage_prefix: str = "passage: ", max_seq_length: int = 256,
                 cache_dir: Path | None = None):
        self._model_path = model_path
        self._q_pre, self._p_pre = query_prefix, passage_prefix
        self._max_len = max_seq_length
        self._cache_dir = cache_dir
        self._model = None
        self._passages: list[Passage] = []
        self._matrix: np.ndarray | None = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise ServiceUnavailableError(
                    "sentence-transformers is not installed: pip install -r requirements-ml.txt") from exc
            self._model = SentenceTransformer(self._model_path)
            self._model.max_seq_length = self._max_len
        return self._model

    def index(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        texts = [self._p_pre + p.text for p in self._passages]
        cache = self._cache_file(texts)
        if cache is not None and cache.exists():
            self._matrix = np.load(cache)  # same passages as last time: skip the slow encoding
            return
        self._matrix = self._load().encode(
            texts, batch_size=16, normalize_embeddings=True).astype(np.float32)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, self._matrix)

    def search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        if self._matrix is None or not query.strip():
            return []
        q = self._load().encode([self._q_pre + query], normalize_embeddings=True).astype(np.float32)
        sims = (q @ self._matrix.T)[0]
        top = np.argsort(-sims, kind="stable")[:k]
        return [RetrievalHit(self._passages[i], float(max(sims[i], 0.0))) for i in top]

    def _cache_file(self, texts: list[str]) -> Path | None:
        if self._cache_dir is None:
            return None
        digest = hashlib.md5("\n".join(texts).encode("utf-8")).hexdigest()[:10]
        return self._cache_dir / f"passages_{digest}.npy"
