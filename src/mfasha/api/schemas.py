"""Request and response models. Pydantic validates every input before it reaches the pipeline."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from mfasha.auth import PIN_PATTERN


class TextQuestion(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Kinyarwanda question")


class AskResponse(BaseModel):
    answer_id: int
    status: str
    answer: str
    referral_reason: Optional[str] = None
    question: str
    heard: Optional[str] = None
    passage_id: Optional[str] = None
    retrieval_score: Optional[float] = None
    margin: Optional[float] = None
    predicted_category: Optional[str] = None
    review_status: Optional[str] = None
    source: Optional[str] = None
    latency_ms: float
    stage_ms: dict


class FeedbackIn(BaseModel):
    answer_id: int = Field(..., ge=1)
    rating: int = Field(..., ge=1, le=5)
    is_useful: bool
    comment: Optional[str] = Field(None, max_length=1000)


class OfficerLoginIn(BaseModel):
    phone: str = Field(..., min_length=5, max_length=25)
    pin: str = Field(..., pattern=PIN_PATTERN, description="4 to 6 digits")


class OfficerRegisterIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    phone: str = Field(..., min_length=5, max_length=25)
    pin: str = Field(..., pattern=PIN_PATTERN, description="4 to 6 digits")
    code: str = Field(..., min_length=1, max_length=100, description="sign-up code given by the supervisor")


class ExpertReviewIn(BaseModel):
    answer_id: int = Field(..., ge=1)
    reviewer: str = Field(..., min_length=2, max_length=80)
    verdict: str = Field(..., pattern="^(correct|partially_correct|incorrect)$")
    is_relevant: bool
    is_clear: bool
    is_safe: bool
    remarks: Optional[str] = Field(None, max_length=1000)


class HealthResponse(BaseModel):
    status: str
    version: str
    passages: int
    reviewed_passages: int
    components: dict