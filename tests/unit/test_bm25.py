import pytest

from mfasha.domain.models import Passage
from mfasha.retrieval import BM25Retriever


def corpus():
    return [Passage("a", "ibigori bitera mu mvura nyinshi", "crop production"),
            Passage("b", "inka zikenera amazi meza", "livestock management"),
            Passage("c", "ibigori n'ibishyimbo bihingwa hamwe", "crop production")]


def test_best_passage_is_ranked_first():
    r = BM25Retriever()
    r.index(corpus())
    assert r.search("inka amazi", 3)[0].passage.pid == "b"


def test_scores_are_normalised_between_zero_and_one():
    r = BM25Retriever()
    r.index(corpus())
    assert all(0 <= h.score <= 1 for h in r.search("ibigori bitera mvura", 3))


def test_unknown_terms_return_nothing():
    r = BM25Retriever()
    r.index(corpus())
    assert r.search("xyz qwerty") == []


def test_empty_query_and_empty_index_do_not_crash():
    r = BM25Retriever()
    assert r.search("ibigori") == []
    r.index(corpus())
    assert r.search("") == []


def test_k_limits_results():
    r = BM25Retriever()
    r.index(corpus())
    assert len(r.search("ibigori", 1)) == 1


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        BM25Retriever(k1=0)
    with pytest.raises(ValueError):
        BM25Retriever(b=1.5)


def test_shorter_document_wins_on_equal_term_counts():
    docs = [Passage("long", "ibigori " + "x " * 50, "c"), Passage("short", "ibigori", "c")]
    r = BM25Retriever()
    r.index(docs)
    assert r.search("ibigori")[0].passage.pid == "short"
