"""BM25 implemented from scratch with an inverted index.

Why not `rank_bm25`: the library scores every document for every query term, which is O(N x Q).
An inverted index only visits the documents that contain a query term, so search cost depends on the
number of matching postings and stays flat as the knowledge base grows. Scores are also normalised
to 0..1 (see `_upper_bound`) so the referral threshold has the same meaning as for cosine scores.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence

from mfasha.domain.models import Passage, RetrievalHit
from mfasha.interfaces import Retriever
from mfasha.nlp.preprocessing import tokenize


class BM25Retriever(Retriever):
    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("k1 must be > 0 and b must be in [0, 1]")
        self._k1, self._b = k1, b
        self._passages: list[Passage] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)  # term -> [(doc, tf)]
        self._doc_len: list[int] = []
        self._idf: dict[str, float] = {}
        self._avg_len = 0.0

    # ------------------------------------------------------------------ indexing
    def index(self, passages: Sequence[Passage]) -> None:
        self._passages = list(passages)
        self._postings = defaultdict(list)
        self._doc_len = []
        for doc_id, passage in enumerate(self._passages):
            counts = Counter(tokenize(passage.text))
            self._doc_len.append(sum(counts.values()))
            for term, tf in counts.items():
                self._postings[term].append((doc_id, tf))

        n_docs = len(self._passages)
        self._avg_len = (sum(self._doc_len) / n_docs) if n_docs else 0.0
        # the "+1" inside the log keeps idf positive even for terms that appear in most documents
        self._idf = {
            term: math.log(1 + (n_docs - len(post) + 0.5) / (len(post) + 0.5))
            for term, post in self._postings.items()
        }

    # ------------------------------------------------------------------ searching
    def search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        terms = [t for t in set(tokenize(query)) if t in self._idf]
        if not terms or not self._passages:
            return []

        scores: dict[int, float] = defaultdict(float)
        for term in terms:
            idf = self._idf[term]
            for doc_id, tf in self._postings[term]:
                norm = 1 - self._b + self._b * self._doc_len[doc_id] / self._avg_len
                scores[doc_id] += idf * tf * (self._k1 + 1) / (tf + self._k1 * norm)

        upper = self._upper_bound(terms)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:k]
        return [RetrievalHit(self._passages[d], min(s / upper, 1.0)) for d, s in ranked]

    def _upper_bound(self, terms: list[str]) -> float:
        """Largest score any document could reach for these terms: tf -> infinity gives idf * (k1 + 1).
        Dividing by it maps every score into 0..1."""
        return sum(self._idf[t] * (self._k1 + 1) for t in terms) or 1.0
