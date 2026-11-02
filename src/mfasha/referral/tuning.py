"""Choose the referral threshold and margin on validation data (notebook: `tune`).

The goal is the highest share of questions answered while keeping the share of WRONG answers served
below a safety target. This is a small grid search over quantiles of the observed top scores.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TuningResult:
    threshold: float
    margin: float
    answered: float
    wrong_served: float
    target_met: bool


def tune_thresholds(top_scores: Sequence[float], margins: Sequence[float], correct: Sequence[bool],
                    agree: Sequence[bool] | None = None, max_wrong_served: float = 0.05,
                    margin_grid: Sequence[float] = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08)) -> TuningResult:
    top = np.asarray(top_scores, dtype=float)
    mar = np.asarray(margins, dtype=float)
    ok_answer = np.asarray(correct, dtype=bool)
    agree_arr = np.ones_like(ok_answer) if agree is None else np.asarray(agree, dtype=bool)
    if not (len(top) == len(mar) == len(ok_answer) == len(agree_arr)) or len(top) == 0:
        raise ValueError("inputs must be non-empty and have the same length")

    candidates: list[TuningResult] = []
    for threshold in np.unique(np.quantile(top, np.linspace(0, 0.97, 98))):
        for margin in margin_grid:
            answered = (top >= threshold) & (mar >= margin) & agree_arr
            wrong = float((answered & ~ok_answer).mean())
            candidates.append(TuningResult(float(threshold), float(margin), float(answered.mean()),
                                           wrong, wrong <= max_wrong_served))

    safe = [c for c in candidates if c.target_met]
    if safe:  # most questions answered among the safe settings
        return max(safe, key=lambda c: c.answered)
    return min(candidates, key=lambda c: (c.wrong_served, -c.answered))  # nothing safe: least risky
