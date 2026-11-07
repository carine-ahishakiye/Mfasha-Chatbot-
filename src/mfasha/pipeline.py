
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from mfasha.domain.errors import ServiceUnavailableError
from mfasha.domain.models import AnswerStatus, PipelineResult, ReferralReason
from mfasha.interfaces import Classifier, Retriever, SpeechToText
from mfasha.nlp.preprocessing import TextCleaner
from mfasha.referral.policy import ReferralContext, ReferralPolicy
from mfasha.speech.audio import decode_wav

log = logging.getLogger(__name__)


class StageTimer:
    """Collects the time spent in each stage, in milliseconds (non-functional requirement 3.4.2)."""

    def __init__(self) -> None:
        self.stage_ms: dict[str, float] = {}
        self._start = time.perf_counter()

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        began = time.perf_counter()
        try:
            yield
        finally:
            self.stage_ms[name] = round((time.perf_counter() - began) * 1000, 2)

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)


class MfashaPipeline:
    def __init__(self, cleaner: TextCleaner, classifier: Classifier, retriever: Retriever,
                 policy: ReferralPolicy, stt: SpeechToText,
                 referral_message: str, top_k: int = 5, source: str = ""):
        self._cleaner, self._classifier, self._retriever = cleaner, classifier, retriever
        self._policy, self._stt = policy, stt
        self._referral_message, self._top_k, self._source = referral_message, top_k, source

    # ------------------------------------------------------------------ public API
    def ask_text(self, text: str) -> PipelineResult:
        timer = StageTimer()
        result = self._answer(text, timer)
        return self._finish(result, timer)

    def ask_audio(self, wav_bytes: bytes, max_seconds: float = 30.0) -> PipelineResult:
        timer = StageTimer()
        with timer.stage("decode_audio"):
            samples, rate = decode_wav(wav_bytes, max_seconds)       # InvalidAudioError -> HTTP 422
        with timer.stage("speech_to_text"):
            heard = self._stt.transcribe(samples, rate)              # ServiceUnavailableError -> HTTP 503
        if not heard.strip():
            result = self._referral("", ReferralReason.SPEECH_NOT_UNDERSTOOD)
        else:
            result = self._answer(heard, timer)
        result.heard = heard
        return self._finish(result, timer)

    # ------------------------------------------------------------------ stages 3 to 6
    def _answer(self, text: str, timer: StageTimer) -> PipelineResult:
        with timer.stage("preprocess"):
            question = self._cleaner.preprocess_question(text)
        if not question:
            return self._referral(text or "", ReferralReason.EMPTY_QUESTION)

        with timer.stage("classify"):
            category = self._classifier.predict(question)
        with timer.stage("retrieve"):
            hits = self._retriever.search(question, self._top_k)
        if not hits:
            return self._referral(question, ReferralReason.NO_RETRIEVAL_RESULT, predicted_category=category)

        top = hits[0]
        margin = top.score - hits[1].score if len(hits) > 1 else top.score
        with timer.stage("referral_policy"):
            reason = self._policy.evaluate(ReferralContext(top, margin, category))

        common = dict(question=question, passage_id=top.passage.pid, retrieval_score=round(top.score, 4),
                      margin=round(margin, 4), predicted_category=category)
        if reason is not None:
            return self._referral(reason=reason, **common)
        return PipelineResult(status=AnswerStatus.ANSWERED, answer=top.passage.text,
                              review_status="reviewed" if top.passage.reviewed else "unreviewed",
                              source=top.passage.source or self._source, **common)

        OFF_TOPIC_MESSAGE = ("Mbabarira, iki kibazo ntikijyanye n'ibyo nshobora gusubiza. "
                         "Mfasha isubiza ibibazo ku buhinzi n'ubworozi gusa. "
                         "Nyamuneka baza ikibazo ku myaka, amatungo, indwara n'ibyonnyi cyangwa ifumbire.")

    def _referral(self, question: str, reason: ReferralReason, **extra) -> PipelineResult:
        off_topic = reason in (ReferralReason.LOW_RETRIEVAL_SCORE, ReferralReason.NO_RETRIEVAL_RESULT)
        message = self.OFF_TOPIC_MESSAGE if off_topic else self._referral_message
        return PipelineResult(question=question, status=AnswerStatus.REFERRED,
                              answer=message, referral_reason=reason, **extra)

    # ------------------------------------------------------------------ stages 7 and 8
    def _finish(self, result: PipelineResult, timer: StageTimer) -> PipelineResult:
        result.stage_ms = timer.stage_ms
        result.latency_ms = timer.total_ms
        return result

    # ------------------------------------------------------------------ introspection
    def describe(self) -> dict:
        return {"classifier": self._classifier.name, "retriever": self._retriever.name,
                "stt": self._stt.name}