"""Plain data objects shared by every layer. They hold data and no behaviour that needs I/O."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    REFERRED = "referred"


class ReferralReason(str, Enum):
    """Why the system refused to answer. Mirrors the reasons used in the notebook."""

    EMPTY_QUESTION = "empty_question"
    NO_RETRIEVAL_RESULT = "no_retrieval_result"
    LOW_RETRIEVAL_SCORE = "low_retrieval_score"
    AMBIGUOUS_TOP_PASSAGES = "ambiguous_top_passages"
    CLASSIFIER_RETRIEVER_DISAGREE = "classifier_retriever_disagree"
    PASSAGE_NOT_REVIEWED = "passage_not_reviewed"
    SPEECH_NOT_UNDERSTOOD = "speech_not_understood"


@dataclass(frozen=True)
class Passage:
    """One entry of the verified knowledge base."""

    pid: str
    text: str
    category: str
    reviewed: bool = False
    source: str = ""


@dataclass(frozen=True)
class RetrievalHit:
    passage: Passage
    score: float  # always normalised to 0..1 so one threshold means the same thing for every retriever


@dataclass
class PipelineResult:
    """Everything the API needs to show an answer and to log the interaction."""

    question: str
    status: AnswerStatus
    answer: str
    referral_reason: Optional[ReferralReason] = None
    heard: Optional[str] = None  # transcription when the question came as voice
    passage_id: Optional[str] = None
    retrieval_score: Optional[float] = None
    margin: Optional[float] = None
    predicted_category: Optional[str] = None
    review_status: Optional[str] = None
    source: Optional[str] = None
    audio: Optional[bytes] = None  # WAV bytes of the spoken answer, when TTS ran
    latency_ms: float = 0.0
    stage_ms: dict = field(default_factory=dict)

    def to_dict(self, include_audio: bool = False) -> dict:
        data = {k: v for k, v in asdict(self).items() if k != "audio"}
        data["status"] = self.status.value
        data["referral_reason"] = self.referral_reason.value if self.referral_reason else None
        if include_audio:
            data["audio"] = self.audio
        return data
