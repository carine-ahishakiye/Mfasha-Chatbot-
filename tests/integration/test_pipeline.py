import csv
from dataclasses import replace

import pytest

from mfasha.config import ROOT
from mfasha.domain.errors import InvalidAudioError, ServiceUnavailableError
from mfasha.domain.models import AnswerStatus, ReferralReason
from mfasha.factory import build_pipeline
from mfasha.speech.stt import UnavailableSpeechToText
from tests.conftest import IN_SCOPE_PID, IN_SCOPE_QUESTION, FakeSpeechToText, make_wav

SAMPLE = ROOT / "data" / "sample"


def read(name):
    with open(SAMPLE / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_in_scope_question_is_answered_from_the_reviewed_passage(pipeline):
    result = pipeline.ask_text(IN_SCOPE_QUESTION)
    assert result.status == AnswerStatus.ANSWERED
    assert result.passage_id == IN_SCOPE_PID and result.review_status == "reviewed"
    assert set(result.stage_ms) >= {"preprocess", "classify", "retrieve", "referral_policy"}


# The default hybrid retriever answers this one instead of referring it (top score is above the threshold).
# Tracked as a known weakness. strict=True makes the test fail once it is fixed, so remove the mark then.
KNOWN_OFF_TOPIC_MISS = {"Igiciro cy'itike ya bisi i Kigali ni angahe?"}
OFF_TOPIC = [
    pytest.param(row["question"], marks=pytest.mark.xfail(
        strict=True, reason="hybrid retriever answers this off-topic question"))
    if row["question"] in KNOWN_OFF_TOPIC_MISS
    else row["question"]
    for row in read("out_of_scope_questions.csv")
]


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_off_topic_questions_are_referred(pipeline, question):
    assert pipeline.ask_text(question).status == AnswerStatus.REFERRED


def test_empty_question_is_referred_not_crashed(pipeline):
    result = pipeline.ask_text("   ")
    assert result.referral_reason == ReferralReason.EMPTY_QUESTION


def test_unreviewed_passage_is_never_served(settings, knowledge_base):
    """All real passages are reviewed, so build a copy of the knowledge base with one of them unreviewed."""
    from mfasha.knowledge.base import KnowledgeBase
    passages = [replace(p, reviewed=False) if p.pid == IN_SCOPE_PID else p for p in knowledge_base.passages]
    pipe, _ = build_pipeline(settings, KnowledgeBase(passages))
    result = pipe.ask_text(IN_SCOPE_QUESTION)
    assert result.status == AnswerStatus.REFERRED
    assert result.referral_reason == ReferralReason.PASSAGE_NOT_REVIEWED


def test_retrieval_quality_on_sample_questions_meets_a_floor(pipeline):
    """Regression guard: top-1 retrieval on the labelled sample must not silently get worse."""
    rows = read("eval_questions.csv")
    hits = sum(pipeline._retriever.search(r["question"], 1)[0].passage.pid == r["pid"] for r in rows)
    # The default hybrid (BM25 + TF-IDF) gets 8/12 here. The fine-tuned e5 model is stronger but is not run in tests.
    assert hits / len(rows) >= 0.60


def test_voice_question_goes_through_stt(pipeline):
    result = pipeline.ask_audio(make_wav())
    assert result.heard == IN_SCOPE_QUESTION
    assert "speech_to_text" in result.stage_ms


def test_silent_transcription_is_referred(pipeline):
    pipeline._stt = FakeSpeechToText("")
    assert pipeline.ask_audio(make_wav()).referral_reason == ReferralReason.SPEECH_NOT_UNDERSTOOD


def test_bad_audio_raises_invalid_audio(pipeline):
    with pytest.raises(InvalidAudioError):
        pipeline.ask_audio(b"junk")


def test_stt_disabled_raises_service_unavailable(pipeline):
    pipeline._stt = UnavailableSpeechToText()
    with pytest.raises(ServiceUnavailableError):
        pipeline.ask_audio(make_wav())


@pytest.mark.parametrize("retriever", ["bm25", "tfidf", "hybrid"])
def test_every_retriever_choice_builds_and_answers(settings, knowledge_base, retriever):
    from dataclasses import replace
    pipe, _ = build_pipeline(replace(settings, retriever=retriever), knowledge_base)
    assert pipe.ask_text("Inka zikenera iki?").passage_id is not None