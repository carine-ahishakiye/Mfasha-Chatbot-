
"""All database access goes through this class (Repository pattern).
The API never builds a query.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, sessionmaker

from mfasha.domain.models import AnswerStatus, PipelineResult
from mfasha.auth import hash_pin
from mfasha.storage.orm import (
    AnswerRow,
    ExpertReviewRow,
    FeedbackRow,
    OfficerRow,
    QuestionRow,
)

VERDICTS = {"correct", "partially_correct", "incorrect"}


class InteractionRepository:
    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    def log_interaction(
        self, result: PipelineResult, input_type: str, components: dict
    ) -> int:
        """Store a question and its answer. Returns the answer ID."""
        with self._sessions.begin() as session:
            question = QuestionRow(
                input_type=input_type,
                question_text=result.question,
                transcription=result.heard,
            )

            answer = AnswerRow(
                question=question,
                status=result.status.value,
                referral_reason=(
                    result.referral_reason.value
                    if result.referral_reason
            else None
                ),
                answer_text=result.answer,
                passage_id=result.passage_id,
                retrieval_score=result.retrieval_score,
                margin=result.margin,
                predicted_category=result.predicted_category,
                review_status=result.review_status,
                latency_ms=result.latency_ms,
                components=components,
            )

            session.add_all([question, answer])
            session.flush()
            return answer.id

    def answer_exists(self, answer_id: int) -> bool:
        with self._sessions() as session:
            return session.get(AnswerRow, answer_id) is not None

    def add_feedback(
        self,
        answer_id: int,
        rating: int,
        is_useful: bool,
        comment: Optional[str],
    ) -> int:
        with self._sessions.begin() as session:
            row = FeedbackRow(
                answer_id=answer_id,
                rating=rating,
                is_useful=is_useful,
                comment=comment,
            )
            session.add(row)
            session.flush()
            return row.id

    def add_expert_review(
        self,
        answer_id: int,
        reviewer: str,
        verdict: str,
        is_relevant: bool,
        is_clear: bool,
        is_safe: bool,
        remarks: Optional[str],
    ) -> int:
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")

        with self._sessions.begin() as session:
            row = ExpertReviewRow(
                answer_id=answer_id,
                reviewer=reviewer,
                verdict=verdict,
                is_relevant=is_relevant,
                is_clear=is_clear,
                is_safe=is_safe,
                remarks=remarks,
            )
            session.add(row)
            session.flush()
            return row.id

    # ---------------------------------------------------------------
    # Officers
    # ---------------------------------------------------------------

    def upsert_officer(self, phone: str, name: str, pin: str) -> bool:
        """Create an officer or update an existing officer's name and PIN."""
        salt, digest = hash_pin(pin)

        with self._sessions.begin() as session:
            row = session.scalar(
                select(OfficerRow).where(OfficerRow.phone == phone)
            )

            created = row is None

            if created:
                row = OfficerRow(
                    phone=phone,
                    name=name,
                    pin_salt=salt,
                    pin_hash=digest,
                    active=True,
                )
                session.add(row)
            else:
                row.name = name
                row.pin_salt = salt
                row.pin_hash = digest
                row.active = True

            return created

    def create_officer(self, phone: str, name: str, pin: str) -> bool:
        """Create a new officer. Return False if the phone is already used."""
        salt, digest = hash_pin(pin)

        with self._sessions.begin() as session:
            existing = session.scalar(
                select(OfficerRow).where(OfficerRow.phone == phone)
            )

            if existing is not None:
                return False

            session.add(
                OfficerRow(
                    phone=phone,
                    name=name,
                    pin_salt=salt,
                    pin_hash=digest,
                    active=True,
                )
            )
            return True

    def set_officer_active(self, phone: str, active: bool) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(
                select(OfficerRow).where(OfficerRow.phone == phone)
            )

            if row is None:
                return False

            row.active = active
            return True

    def get_officer(self, phone: str) -> Optional[dict]:
        with self._sessions() as session:
            row = session.scalar(
                select(OfficerRow).where(OfficerRow.phone == phone)
            )

            if row is None:
                return None

            return {
                "phone": row.phone,
                "name": row.name,
                "pin_salt": row.pin_salt,
                "pin_hash": row.pin_hash,
                "active": row.active,
            }

    def list_officers(self) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(
                select(OfficerRow).order_by(OfficerRow.id)
            ).all()

            return [
                {
                    "phone": row.phone,
                    "name": row.name,
                    "active": row.active,
                }
                for row in rows
            ]

    # ---------------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------------

    def stats(self) -> dict:
        """Return statistics for the administrator dashboard and evaluation."""
        with self._sessions() as session:
            total = (
                session.scalar(select(func.count(AnswerRow.id))) or 0
            )

            referred = (
                session.scalar(
                    select(func.count(AnswerRow.id)).where(
                        AnswerRow.status == AnswerStatus.REFERRED.value
                    )
                )
                or 0
            )

            by_input = dict(
                session.execute(
                    select(
                        QuestionRow.input_type,
                        func.count(QuestionRow.id),
                    ).group_by(QuestionRow.input_type)
                ).all()
            )

            avg_latency = (
                session.scalar(select(func.avg(AnswerRow.latency_ms)))
                or 0.0
            )

            avg_rating = session.scalar(
                select(func.avg(FeedbackRow.rating))
            )

            useful = (
                session.scalar(
                    select(func.count(FeedbackRow.id)).where(
                        FeedbackRow.is_useful.is_(True)
                    )
                )
                or 0
            )

            n_feedback = (
                session.scalar(select(func.count(FeedbackRow.id))) or 0
            )

            verdicts = dict(
                session.execute(
                    select(
                        ExpertReviewRow.verdict,
                        func.count(ExpertReviewRow.id),
                    ).group_by(ExpertReviewRow.verdict)
                ).all()
            )

        n_reviews = sum(verdicts.values())
        ok = (
            verdicts.get("correct", 0)
            + verdicts.get("partially_correct", 0)
        )

        return {
            "questions": total,
            "answered": total - referred,
            "referred": referred,
            "referral_rate": round(referred / total, 3) if total else 0.0,
            "by_input_type": by_input,
            "avg_latency_ms": round(float(avg_latency), 1),
            "feedback_count": n_feedback,
            "avg_rating": (
                round(float(avg_rating), 2) if avg_rating else None
            ),
            "useful_rate": (
                round(useful / n_feedback, 3) if n_feedback else None
            ),
            "expert_reviews": n_reviews,
            "officer_correct_or_partial_rate": (
                round(ok / n_reviews, 3) if n_reviews else None
            ),  # Objective 3 target: >= 0.70
        }

    # ---------------------------------------------------------------
    # Answers
    # ---------------------------------------------------------------

    @staticmethod
    def _answer_dict(row: AnswerRow) -> dict:
        return {
            "answer_id": row.id,
            "question": row.question.question_text,
            "answer": row.answer_text,
            "status": row.status,
            "referral_reason": row.referral_reason,
            "retrieval_score": row.retrieval_score,
            "predicted_category": row.predicted_category,
            "passage_id": row.passage_id,
            "review_status": row.review_status,
            "submitted_at": (
                row.generated_at.isoformat() if row.generated_at else None
            ),
        }

    def list_answers(
        self, unreviewed: bool = True, limit: int = 50
    ) -> list[dict]:
        limit = min(max(limit, 1), 200)

        with self._sessions() as session:
            stmt = (
                select(AnswerRow)
                .options(selectinload(AnswerRow.question))
                .order_by(AnswerRow.id.desc())
                .limit(limit)
            )

            if unreviewed:
                stmt = stmt.where(~AnswerRow.reviews.any())

            rows = session.scalars(stmt).all()
            return [self._answer_dict(row) for row in rows]

    def get_answer(self, answer_id: int) -> Optional[dict]:
        with self._sessions() as session:
            row = session.get(
                AnswerRow,
                answer_id,
                options=[selectinload(AnswerRow.question)],
            )

            return self._answer_dict(row) if row else None

    # ---------------------------------------------------------------
    # Admin: read-only database records
    # ---------------------------------------------------------------

    def list_admin_records(self, limit: int = 100) -> dict:
        """Return read-only question, answer, review, and feedback records."""
        limit = min(max(limit, 1), 200)

        with self._sessions() as session:

            # Questions
            questions = session.scalars(
                select(QuestionRow)
                .order_by(QuestionRow.id.desc())
                .limit(limit)
            ).all()

            question_records = [
                {
                    "id": row.id,
                    "input_type": row.input_type,
                    "question_text": row.question_text,
                    "transcription": row.transcription,
                    "submitted_at": (
                        row.submitted_at.isoformat()
                        if row.submitted_at
                        else None
                    ),
                }
                for row in questions
            ]

            # Answers
            answers = session.scalars(
                select(AnswerRow)
                .options(selectinload(AnswerRow.question))
                .order_by(AnswerRow.id.desc())
                .limit(limit)
            ).all()

            answer_records = [
                self._answer_dict(row) for row in answers
            ]

            # Expert reviews
            reviews = session.scalars(
                select(ExpertReviewRow)
                .order_by(ExpertReviewRow.id.desc())
                .limit(limit)
            ).all()

            review_records = [
                {
                    "id": row.id,
                    "answer_id": row.answer_id,
                    "reviewer": row.reviewer,
                    "verdict": row.verdict,
                    "is_relevant": row.is_relevant,
                    "is_clear": row.is_clear,
                    "is_safe": row.is_safe,
                    "remarks": row.remarks,
                    "reviewed_at": (
                        row.reviewed_at.isoformat()
                        if row.reviewed_at
                        else None
                    ),
                }
                for row in reviews
            ]

            # Feedback
            feedback = session.scalars(
                select(FeedbackRow)
                .order_by(FeedbackRow.id.desc())
                .limit(limit)
            ).all()

            feedback_records = [
                {
                    "id": row.id,
                    "answer_id": row.answer_id,
                    "rating": row.rating,
                    "is_useful": row.is_useful,
                    "comment": row.comment,
                    "created_at": (
                        row.created_at.isoformat()
                        if row.created_at
                        else None
                    ),
                }
                for row in feedback
            ]

            return {
                "questions": question_records,
                "answers": answer_records,
                "expert_reviews": review_records,
                "feedback": feedback_records,
            }
