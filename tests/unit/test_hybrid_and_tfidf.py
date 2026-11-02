import pytest

from mfasha.domain.models import Passage
from mfasha.retrieval import BM25Retriever, HybridRetriever, TfidfRetriever

DOCS = [Passage("a", "indwara y'ibishyimbo ihindura ibibabi", "crop pests and diseases"),
        Passage("b", "inka zikenera amazi meza", "livestock management")]


def test_tfidf_char_ngrams_match_prefix_variants():
    r = TfidfRetriever()
    r.index(DOCS)
    assert r.search("ndwara y'ibishyimbo")[0].passage.pid == "a"      # indwara vs ndwara


@pytest.mark.parametrize("fusion", ["weighted", "rrf"])
def test_hybrid_returns_best_passage_and_bounded_scores(fusion):
    h = HybridRetriever([BM25Retriever(), TfidfRetriever()], fusion=fusion)
    h.index(DOCS)
    hits = h.search("inka amazi")
    assert hits[0].passage.pid == "b" and 0 <= hits[0].score <= 1


def test_hybrid_validates_arguments():
    with pytest.raises(ValueError):
        HybridRetriever([])
    with pytest.raises(ValueError):
        HybridRetriever([BM25Retriever()], weights=[1, 2])
    with pytest.raises(ValueError):
        HybridRetriever([BM25Retriever()], fusion="magic")
