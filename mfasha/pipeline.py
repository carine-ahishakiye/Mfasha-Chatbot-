"""The whole chatbot: question (text or voice) -> retrieve -> answer with the best passage, or refer. Speech output is added by the app."""
from dataclasses import dataclass, field
from typing import List, Optional

from . import config
from .retriever import Hit
from .text_utils import clean_text

ANSWERED, REFERRED, EMPTY = "answered", "referred", "empty"


@dataclass
class Result:
    status: str                              # answered | referred | empty
    question: str = ""
    heard: Optional[str] = None              # what the ASR heard, when the question was spoken
    answer: Optional[str] = None             # the stored passage, unchanged, or the referral message
    referral_reason: Optional[str] = None    # why the question was referred (None when answered)
    hits: List[Hit] = field(default_factory=list)

    @property
    def passage_id(self) -> Optional[str]:
        return self.hits[0].pid if self.status == ANSWERED and self.hits else None

    @property
    def score(self) -> Optional[float]:
        return self.hits[0].score if self.hits else None


class Mfasha:
    def __init__(self, retriever, transcriber=None, threshold: Optional[float] = None):
        self.retriever = retriever
        self.transcriber = transcriber
        # the score the best passage must reach before it is shown as the answer
        self.threshold = config.REFERRAL_THRESHOLD if threshold is None else threshold

    @classmethod
    def load(cls):
        from .assets import ensure_assets
        from .asr import Transcriber
        from .retriever import Retriever
        ensure_assets()
        return cls(Retriever.load(), Transcriber())

    def ask(self, text: Optional[str] = None, audio=None) -> Result:
        heard = None
        if audio is not None:
            heard = self.transcriber.transcribe(audio)
            raw = heard
        else:
            raw = text or ""
        question = clean_text(raw)
        if not question:
            return Result(EMPTY, heard=heard, referral_reason="empty_question")

        hits = self.retriever.search(question)
        if not hits:
            return Result(REFERRED, question, heard, config.REFERRAL_MESSAGE, "no_retrieval_result", hits)

        # the best passage is too far from the question: refer instead of showing a wrong passage
        if hits[0].score < self.threshold:
            return Result(REFERRED, question, heard, config.REFERRAL_MESSAGE, "low_retrieval_score", hits)

        return Result(ANSWERED, question, heard, hits[0].text, None, hits)
