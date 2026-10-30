import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from mfasha import config
from mfasha.pipeline import ANSWERED, EMPTY, REFERRED, Mfasha
from mfasha.retriever import Retriever

PASSAGES = [
    {"pid": "A1", "text": "Intama ihaka iminsi 149-152, (amezi 5). Yonsa amezi atatu."},
    {"pid": "A2", "text": "Inkoko zirwaye zanduza izindi."},
]
EMB = np.array([[1, 0], [0, 1]], dtype=np.float32)


def make_bot(vec=(1.0, 0.0), threshold=0.0):
    retr = Retriever(PASSAGES, EMB, lambda q: np.array(vec, dtype=np.float32))
    asr = type("T", (), {"transcribe": lambda s, a: "intama zororoka gute"})()
    return Mfasha(retr, transcriber=asr, threshold=threshold)


def test_answer_is_the_stored_passage_unchanged():
    r = make_bot().ask(text="Intama zihaka igihe kingana iki?")
    assert r.status == ANSWERED and r.answer == PASSAGES[0]["text"]
    assert r.passage_id == "A1" and r.referral_reason is None and r.hits[0].pid == "A1"


def test_low_score_is_referred():
    r = make_bot(vec=(0.5, 0.5), threshold=0.9).ask(text="Perezida wa Amerika ni nde?")
    assert r.status == REFERRED and r.answer == config.REFERRAL_MESSAGE
    assert r.referral_reason == "low_retrieval_score" and r.passage_id is None


def test_score_at_the_threshold_is_answered():
    # the notebook refers only when the score is strictly below the threshold
    r = make_bot(vec=(1.0, 0.0), threshold=1.0).ask(text="Intama zororoka gute?")
    assert r.status == ANSWERED


def test_threshold_zero_never_refers():
    r = make_bot(vec=(0.5, 0.5), threshold=0.0).ask(text="Perezida wa Amerika ni nde?")
    assert r.status == ANSWERED


def test_empty_question():
    r = make_bot().ask(text="   ")
    assert r.status == EMPTY and r.referral_reason == "empty_question"


def test_no_retrieval_result_is_referred():
    retr = Retriever(PASSAGES, EMB, lambda q: np.array([1.0, 0.0], dtype=np.float32))
    retr.search = lambda q, k=None: []
    r = Mfasha(retr, threshold=0.0).ask(text="Intama zororoka gute?")
    assert r.status == REFERRED and r.referral_reason == "no_retrieval_result"


def test_voice_path_sets_heard():
    r = make_bot().ask(audio=np.zeros(16000, dtype=np.float32))
    assert r.heard == "intama zororoka gute" and r.status == ANSWERED


def test_default_threshold_comes_from_config(monkeypatch):
    monkeypatch.setattr(config, "REFERRAL_THRESHOLD", 0.9)
    retr = Retriever(PASSAGES, EMB, lambda q: np.array([0.5, 0.5], dtype=np.float32))
    assert Mfasha(retr).ask(text="Perezida wa Amerika ni nde?").status == REFERRED


def test_threshold_file_is_read(tmp_path, monkeypatch):
    f = tmp_path / "referral_threshold.json"
    f.write_text('{"threshold": 0.42, "coverage": 0.95}')
    monkeypatch.setattr(config, "REFERRAL_THRESHOLD_FILE", f)
    monkeypatch.delenv("REFERRAL_THRESHOLD", raising=False)
    assert config._load_referral_threshold() == 0.42
    monkeypatch.setenv("REFERRAL_THRESHOLD", "0.7")
    assert config._load_referral_threshold() == 0.7
    monkeypatch.delenv("REFERRAL_THRESHOLD")
    f.write_text("not json")
    assert config._load_referral_threshold() == 0.0
