"""Combine several retrievers. Scores are fused as a weighted average of the normalised scores, so
the fused score can still be compared with the referral threshold. Reciprocal Rank Fusion is offered
as an alternative ordering rule (notebook: `rrf`)."""
from __future__ import annotations

from collections.abc import Sequence

from mfasha.domain.models import Passage, RetrievalHit
from mfasha.interfaces import Retriever

_RRF_K = 60


class HybridRetriever(Retriever):
    name = "hybrid"

    def __init__(self, retrievers: Sequence[Retriever], weights: Sequence[float] | None = None,
                 fusion: str = "weighted", candidate_pool: int = 20):
        if not retrievers:
            raise ValueError("HybridRetriever needs at least one retriever")
        weights = list(weights) if weights is not None else [1.0] * len(retrievers)
        if len(weights) != len(retrievers) or any(w < 0 for w in weights) or sum(weights) == 0:
            raise ValueError("weights must be non-negative, non-zero in total, one per retriever")
        if fusion not in {"weighted", "rrf"}:
            raise ValueError("fusion must be 'weighted' or 'rrf'")
        total = sum(weights)
        self._retrievers = list(retrievers)
        self._weights = [w / total for w in weights]
        self._fusion = fusion
        self._pool = candidate_pool

    def index(self, passages: Sequence[Passage]) -> None:
        for retriever in self._retrievers:
            retriever.index(passages)

    def search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        passages: dict[str, Passage] = {}
        fused_score: dict[str, float] = {}
        fused_rank: dict[str, float] = {}
        for retriever, weight in zip(self._retrievers, self._weights, strict=True):
            for rank, hit in enumerate(retriever.search(query, self._pool), start=1):
                pid = hit.passage.pid
                passages[pid] = hit.passage
                fused_score[pid] = fused_score.get(pid, 0.0) + weight * hit.score
                fused_rank[pid] = fused_rank.get(pid, 0.0) + weight / (_RRF_K + rank)

        order_by = fused_rank if self._fusion == "rrf" else fused_score
        ordered = sorted(order_by, key=lambda pid: (-order_by[pid], pid))[:k]
        return [RetrievalHit(passages[pid], min(fused_score[pid], 1.0)) for pid in ordered]
