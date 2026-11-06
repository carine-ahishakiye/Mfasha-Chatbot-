"""Tables from the ERD in proposal section 3.10.3, simplified: the transcription lives on the question
row and the model versions on the answer row, which avoids four joins for no benefit at this scale."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class QuestionRow(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    input_type: Mapped[str] = mapped_column(String(10))            # "text" or "voice"
    question_text: Mapped[str] = mapped_column(Text)
    transcription: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    answer: Mapped[AnswerRow] = relationship(back_populates="question", uselist=False)


class AnswerRow(Base):
    __tablename__ = "answers"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10))
    referral_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    answer_text: Mapped[str] = mapped_column(Text)
    passage_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    components: Mapped[dict] = mapped_column(JSON, default=dict)   # which model produced each stage
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    question: Mapped[QuestionRow] = relationship(back_populates="answer")
    feedback: Mapped[list[FeedbackRow]] = relationship(back_populates="answer")
    reviews: Mapped[list[ExpertReviewRow]] = relationship(back_populates="answer")


class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"))
    rating: Mapped[int] = mapped_column(Integer)
    is_useful: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    answer: Mapped[AnswerRow] = relationship(back_populates="feedback")


class ExpertReviewRow(Base):
    __tablename__ = "expert_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"))
    reviewer: Mapped[str] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(20))   # correct | partially_correct | incorrect
    is_relevant: Mapped[bool] = mapped_column(Boolean)
    is_clear: Mapped[bool] = mapped_column(Boolean)
    is_safe: Mapped[bool] = mapped_column(Boolean)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    answer: Mapped[AnswerRow] = relationship(back_populates="reviews")


class OfficerRow(Base):
    """An agricultural officer who may sign in to the review page (phone number + PIN)."""
    __tablename__ = "officers"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    pin_salt: Mapped[str] = mapped_column(String(32))
    pin_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)