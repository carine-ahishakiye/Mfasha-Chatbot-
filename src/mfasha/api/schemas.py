"""Request and response models. Pydantic validates every input before it reaches the pipeline."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TextQuestion(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Kinyarwanda question")
    with_audio: bool = False


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
    audio_base64: Optional[str] = None


class FeedbackIn(BaseModel):
    answer_id: int = Field(..., ge=1)
    rating: int = Field(..., ge=1, le=5)
    is_useful: bool
    comment: Optional[str] = Field(None, max_length=1000)


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
