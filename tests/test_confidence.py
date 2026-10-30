from mfasha.confidence import ConfidencePolicy
from mfasha.interfaces import Hit

POLICY = ConfidencePolicy(min_score=0.6, high_margin=0.04, medium_margin=0.015)


def hits(*scores):
    return [Hit(f"P{i}", "text", s) for i, s in enumerate(scores)]


def test_big_gap_is_high():
    assert POLICY.for_hits(hits(0.90, 0.70)) == "high"


def test_small_gap_is_medium_then_low():
    assert POLICY.for_hits(hits(0.80, 0.78)) == "medium"
    assert POLICY.for_hits(hits(0.80, 0.795)) == "low"


def test_weak_best_score_is_always_low():
    assert POLICY.for_hits(hits(0.50, 0.10)) == "low"


def test_single_hit_uses_its_score_as_the_gap():
    assert POLICY.for_hits(hits(0.90)) == "high"


def test_missing_cutoffs_are_never_reached():
    only_medium = ConfidencePolicy(high_margin=None, medium_margin=0.02)
    assert only_medium.classify(top=0.9, margin=0.5) == "medium"
    assert ConfidencePolicy().classify(top=0.9, margin=0.5) == "low"
