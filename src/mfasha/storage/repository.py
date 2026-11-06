"""All database access goes through this class (Repository pattern). The API never builds a query."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload, sessionmaker

from mfasha.domain.models import AnswerStatus, PipelineResult
from mfasha.storage.orm import AnswerRow, ExpertReviewRow, FeedbackRow, QuestionRow

VERDICTS = {"correct", "partially_correct", "incorrect"}


class InteractionRepository:
    def __init__(self, session_factory: sessionmaker):
        self._sessions = session_factory

    def log_interaction(self, result: PipelineResult, input_type: str, components: dict) -> int:
        """Store the question and its answer. Returns the answer id the client uses for feedback."""
        with self._sessions.begin() as session:
            question = QuestionRow(input_type=input_type, question_text=result.question,
                                   transcription=result.heard)
            answer = AnswerRow(
                question=question, status=result.status.value,
                referral_reason=result.referral_reason.value if result.referral_reason else None,
                answer_text=result.answer, passage_id=result.passage_id,
                retrieval_score=result.retrieval_score, margin=result.margin,
                predicted_category=result.predicted_category, review_status=result.review_status,
                latency_ms=result.latency_ms, components=components)
            session.add_all([question, answer])
            session.flush()
            return answer.id

    def answer_exists(self, answer_id: int) -> bool:
        with self._sessions() as session:
            return session.get(AnswerRow, answer_id) is not None

    def add_feedback(self, answer_id: int, rating: int, is_useful: bool, comment: Optional[str]) -> int:
        with self._sessions.begin() as session:
            row = FeedbackRow(answer_id=answer_id, rating=rating, is_useful=is_useful, comment=comment)
            session.add(row)
            session.flush()
            return row.id

    def add_expert_review(self, answer_id: int, reviewer: str, verdict: str, is_relevant: bool,
                          is_clear: bool, is_safe: bool, remarks: Optional[str]) -> int:
        if verdict not in VERDICTS:
            raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
        with self._sessions.begin() as session:
            row = ExpertReviewRow(answer_id=answer_id, reviewer=reviewer, verdict=verdict,
                                  is_relevant=is_relevant, is_clear=is_clear, is_safe=is_safe, remarks=remarks)
            session.add(row)
            session.flush()
            return row.id

    def stats(self) -> dict:
        """Numbers for the administrator dashboard and for the pilot evaluation in proposal 3.12."""
        with self._sessions() as session:
            total = session.scalar(select(func.count(AnswerRow.id))) or 0
            referred = session.scalar(select(func.count(AnswerRow.id)).where(
                AnswerRow.status == AnswerStatus.REFERRED.value)) or 0
            by_input = dict(session.execute(
                select(QuestionRow.input_type, func.count(QuestionRow.id)).group_by(QuestionRow.input_type)).all())
            avg_latency = session.scalar(select(func.avg(AnswerRow.latency_ms))) or 0.0
            avg_rating = session.scalar(select(func.avg(FeedbackRow.rating)))
            useful = session.scalar(select(func.count(FeedbackRow.id)).where(FeedbackRow.is_useful.is_(True))) or 0
            n_feedback = session.scalar(select(func.count(FeedbackRow.id))) or 0
            verdicts = dict(session.execute(
                select(ExpertReviewRow.verdict, func.count(ExpertReviewRow.id)).group_by(ExpertReviewRow.verdict)).all())
        n_reviews = sum(verdicts.values())
        ok = verdicts.get("correct", 0) + verdicts.get("partially_correct", 0)
        return {
            "questions": total, "answered": total - referred, "referred": referred,
            "referral_rate": round(referred / total, 3) if total else 0.0,
            "by_input_type": by_input, "avg_latency_ms": round(float(avg_latency), 1),
            "feedback_count": n_feedback, "avg_rating": round(float(avg_rating), 2) if avg_rating else None,
            "useful_rate": round(useful / n_feedback, 3) if n_feedback else None,
            "expert_reviews": n_reviews, "officer_correct_or_partial_rate":
                round(ok / n_reviews, 3) if n_reviews else None,   # objective 3 target: >= 0.70
        }


    @staticmethod
    def _answer_dict(r: AnswerRow) -> dict:
        return {
            "answer_id": r.id, "question": r.question.question_text, "answer": r.answer_text,
            "status": r.status, "referral_reason": r.referral_reason,
            "retrieval_score": r.retrieval_score, "predicted_category": r.predicted_category,
            "passage_id": r.passage_id, "review_status": r.review_status,
            "submitted_at": r.generated_at.isoformat() if r.generated_at else None,
        }

    def list_answers(self, unreviewed: bool = True, limit: int = 50) -> list[dict]:
        with self._sessions() as session:
            stmt = (select(AnswerRow).options(selectinload(AnswerRow.question))
                    .order_by(AnswerRow.id.desc()).limit(limit))
            if unreviewed:
                stmt = stmt.where(~AnswerRow.reviews.any())
            return [self._answer_dict(r) for r in session.scalars(stmt).all()]

    def get_answer(self, answer_id: int) -> Optional[dict]:
        with self._sessions() as session:
            row = session.get(AnswerRow, answer_id, options=[selectinload(AnswerRow.question)])
            return self._answer_dict(row) if row else None