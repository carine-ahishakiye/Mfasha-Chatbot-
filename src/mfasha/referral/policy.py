
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Optional

from mfasha.domain.models import ReferralReason, RetrievalHit


@dataclass(frozen=True)
class ReferralContext:
    top: RetrievalHit
    margin: float                 # top score minus second score (the top score when only one hit)
    predicted_category: Optional[str]


class ReferralRule(ABC):
    @abstractmethod
    def check(self, ctx: ReferralContext) -> Optional[ReferralReason]:
        """Return a reason to refer, or None when this rule has no objection."""


class LowScoreRule(ReferralRule):
    def __init__(self, threshold: float):
        self.threshold = threshold

    def check(self, ctx):
        return ReferralReason.LOW_RETRIEVAL_SCORE if ctx.top.score < self.threshold else None


class AmbiguityRule(ReferralRule):
    """Refer when the best two passages are almost tied: the system is not sure which one is right."""

    def __init__(self, min_margin: float):
        self.min_margin = min_margin

    def check(self, ctx):
        return ReferralReason.AMBIGUOUS_TOP_PASSAGES if ctx.margin < self.min_margin else None


class AgreementRule(ReferralRule):
    """Refer when the classifier and the retriever point to different topics (proposal section 3.5)."""

    def check(self, ctx):
        if ctx.predicted_category is None:
            return None
        return (ReferralReason.CLASSIFIER_RETRIEVER_DISAGREE
                if ctx.predicted_category != ctx.top.passage.category else None)


class ReviewedRule(ReferralRule):
    """Only passages signed off by an agricultural officer may be shown (proposal section 3.6)."""

    def __init__(self, serve_unreviewed: bool = False):
        self.serve_unreviewed = serve_unreviewed

    def check(self, ctx):
        if self.serve_unreviewed or ctx.top.passage.reviewed:
            return None
        return ReferralReason.PASSAGE_NOT_REVIEWED


class ReferralPolicy:
    def __init__(self, rules: Sequence[ReferralRule]):
        self._rules = list(rules)

    def evaluate(self, ctx: ReferralContext) -> Optional[ReferralReason]:
        for rule in self._rules:
            reason = rule.check(ctx)
            if reason is not None:
                return reason
        return None

    @classmethod
    def standard(cls, threshold: float, margin: float, use_agreement: bool = True,
                 serve_unreviewed: bool = False) -> ReferralPolicy:
        rules: list[ReferralRule] = [LowScoreRule(threshold), AmbiguityRule(margin)]
        if use_agreement:
            rules.append(AgreementRule())
        rules.append(ReviewedRule(serve_unreviewed))
        return cls(rules)
