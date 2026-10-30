
from dataclasses import dataclass
from typing import Optional, Sequence

from . import config
from .interfaces import Hit


@dataclass(frozen=True)
class ConfidencePolicy:
    min_score: float = 0.0                       # a best score below this is always "low"
    high_margin: Optional[float] = None          # gap between best and second-best score for "high"
    medium_margin: Optional[float] = None        # gap for "medium"; None means the level is never reached

    @classmethod
    def from_config(cls) -> "ConfidencePolicy":
        return cls(config.TIER_MIN_SCORE, config.TIER_HIGH_MARGIN, config.TIER_MEDIUM_MARGIN)

    def classify(self, top: float, margin: float) -> str:
        if top < self.min_score:
            return "low"
        if self.high_margin is not None and margin >= self.high_margin:
            return "high"
        if self.medium_margin is not None and margin >= self.medium_margin:
            return "medium"
        return "low"

    def for_hits(self, hits: Sequence[Hit]) -> str:
        top = hits[0].score
        margin = top - hits[1].score if len(hits) > 1 else top
        return self.classify(top, margin)
