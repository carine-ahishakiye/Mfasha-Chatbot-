"""The whole chatbot: question (text or voice) -> retrieve -> grounded answer. Speech output is added by the app."""
from dataclasses import dataclass, field
from typing import List, Optional

from . import config
from .llm import NO_ANSWER, ask_llm
from .retriever import Hit
from .text_utils import clean_text, split_sentences, tidy, ungrounded_numbers


@dataclass
class Result:
    status: str                         # ok | refused | empty | llm_error
    question: str = ""
    heard: Optional[str] = None         # what the ASR heard, when the question was spoken
    answer: Optional[str] = None
    hits: List[Hit] = field(default_factory=list)
    guarded: bool = False               # True when the number guard replaced the LLM's answer


class Mfasha:
    def __init__(self, retriever, transcriber=None, llm=ask_llm):
        self.retriever = retriever
        self.transcriber = transcriber
        self.llm = llm

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
            return Result("empty", heard=heard)

        hits = self.retriever.search(question)

        # optional cheap refusal: the best passage is too far from the question
        if config.MIN_RETRIEVAL_SCORE and hits[0].score < config.MIN_RETRIEVAL_SCORE:
            return Result("refused", question, heard, NO_ANSWER, hits)

        reply = self.llm(question, hits)
        if not reply:
            return Result("llm_error", question, heard, None, hits)
        reply = tidy(reply)
        if reply == NO_ANSWER:
            return Result("refused", question, heard, NO_ANSWER, hits)

        # numbers that are not in the retrieved passages are never shown. Fall back to the top passage itself
        if ungrounded_numbers(reply, [h.text for h in hits]):
            fallback = " ".join(split_sentences(tidy(hits[0].text))[:3])
            return Result("ok", question, heard, fallback, hits, guarded=True)

        return Result("ok", question, heard, reply, hits)
