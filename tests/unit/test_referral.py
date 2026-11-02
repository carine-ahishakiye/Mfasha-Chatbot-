import pytest

from mfasha.domain.models import Passage, ReferralReason, RetrievalHit
from mfasha.referral import ReferralContext, ReferralPolicy, tune_thresholds


def ctx(score=0.9, margin=0.3, predicted="crop production", category="crop production", reviewed=True):
    hit = RetrievalHit(Passage("p", "t", category, reviewed), score)
    return ReferralContext(hit, margin, predicted)


def test_good_answer_passes_every_rule():
    assert ReferralPolicy.standard(0.3, 0.05).evaluate(ctx()) is None


@pytest.mark.parametrize("kwargs, reason", [
    (dict(score=0.1), ReferralReason.LOW_RETRIEVAL_SCORE),
    (dict(margin=0.0), ReferralReason.AMBIGUOUS_TOP_PASSAGES),
    (dict(predicted="animal health"), ReferralReason.CLASSIFIER_RETRIEVER_DISAGREE),
    (dict(reviewed=False), ReferralReason.PASSAGE_NOT_REVIEWED),
])
def test_each_rule_fires_with_its_own_reason(kwargs, reason):
    assert ReferralPolicy.standard(0.3, 0.05).evaluate(ctx(**kwargs)) == reason


def test_serve_unreviewed_switch_and_agreement_switch():
    policy = ReferralPolicy.standard(0.3, 0.05, use_agreement=False, serve_unreviewed=True)
    assert policy.evaluate(ctx(reviewed=False, predicted="animal health")) is None


def test_tuning_prefers_most_answered_among_safe_settings():
    top = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    margins = [0.5] * 6
    correct = [True, True, True, False, False, False]
    result = tune_thresholds(top, margins, correct, max_wrong_served=0.0)
    assert result.target_met and result.wrong_served == 0 and result.answered == 0.5


def test_tuning_falls_back_when_no_setting_is_safe():
    result = tune_thresholds([0.5, 0.5], [0.1, 0.1], [False, False], max_wrong_served=0.0)
    assert not result.target_met


def test_tuning_rejects_bad_input():
    with pytest.raises(ValueError):
        tune_thresholds([], [], [])
