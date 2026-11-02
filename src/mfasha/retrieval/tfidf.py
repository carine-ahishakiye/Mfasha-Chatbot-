"""TF-IDF cosine retriever (baseline from proposal section 3.8). Character n-grams make it robust to
Kinyarwanda prefix changes (indwara / ndwara) and to spelling variation in speech-to-text output."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from mfasha.domain.models import Passage, RetrievalHit
from mfasha.interfaces import Retriever


class TfidfRetriever(Retriever):
    name = "tfidf"

    def __init__(self, analyzer: str = "char_wb", ngram_range: tuple[int, int] = (3, 5)):
        self._vectorizer = TfidfVectorizer(
            analyzer=analyzer, ngram_range=ngram_range, sublinear_tf=True, lowercase=True
        )
        self._passages: list[Passage] = []
        self._matrix = None

    def index(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        self._matrix = self._vectorizer.fit_transform([p.text for p in self._passages])

    def search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        if self._matrix is None or not query.strip():
            return []
        sims = (self._vectorizer.transform([query]) @ self._matrix.T).toarray().ravel()
        top = np.argsort(-sims, kind="stable")[:k]
        return [RetrievalHit(self._passages[i], float(sims[i])) for i in top if sims[i] > 0]
