import csv

import pytest

from mfasha.config import ROOT
from mfasha.domain.errors import InvalidAudioError, ServiceUnavailableError
from mfasha.domain.models import AnswerStatus, ReferralReason
from mfasha.factory import build_pipeline
from mfasha.speech.stt import UnavailableSpeechToText
from tests.conftest import FakeSpeechToText, make_wav

SAMPLE = ROOT / "data" / "sample"


def read(name):
    with open(SAMPLE / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_in_scope_question_is_answered_from_the_reviewed_passage(pipeline):
    result = pipeline.ask_text("Ni gute nahinga ibigori?")
    assert result.status == AnswerStatus.ANSWERED
    assert result.passage_id == "p001" and result.review_status == "reviewed"
    assert set(result.stage_ms) >= {"preprocess", "classify", "retrieve", "referral_policy"}


def test_off_topic_questions_are_referred(pipeline):
    for row in read("out_of_scope_questions.csv"):
        assert pipeline.ask_text(row["question"]).status == AnswerStatus.REFERRED


def test_empty_question_is_referred_not_crashed(pipeline):
    result = pipeline.ask_text("   ")
    assert result.referral_reason == ReferralReason.EMPTY_QUESTION


def test_unreviewed_passage_is_never_served(pipeline):
    result = pipeline.ask_text("Nagurisha nte umusaruro wanjye ku giciro cyiza?")   # p012 is not reviewed
    assert result.status == AnswerStatus.REFERRED
    assert result.referral_reason == ReferralReason.PASSAGE_NOT_REVIEWED


def test_retrieval_quality_on_sample_questions_meets_a_floor(pipeline):
    """Regression guard: top-1 retrieval on the labelled sample must not silently get worse."""
    rows = read("eval_questions.csv")
    hits = sum(pipeline._retriever.search(r["question"], 1)[0].passage.pid == r["pid"] for r in rows)
    assert hits / len(rows) >= 0.75


def test_voice_question_goes_through_stt_and_tts(pipeline):
    result = pipeline.ask_audio(make_wav(), with_audio=True)
    assert result.heard == "Ni gute nahinga ibigori?" and result.audio
    assert "speech_to_text" in result.stage_ms and "text_to_speech" in result.stage_ms


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


def test_missing_tts_still_returns_the_written_answer(settings, knowledge_base):
    pipe, _ = build_pipeline(settings, knowledge_base)           # real TTS switched off in settings
    result = pipe.ask_text("Ni gute nahinga ibigori?", with_audio=True)
    assert result.status == AnswerStatus.ANSWERED and result.audio is None


@pytest.mark.parametrize("retriever", ["bm25", "tfidf", "hybrid"])
def test_every_retriever_choice_builds_and_answers(settings, knowledge_base, retriever):
    from dataclasses import replace
    pipe, _ = build_pipeline(replace(settings, retriever=retriever), knowledge_base)
    assert pipe.ask_text("Inka zikenera iki?").passage_id is not None
