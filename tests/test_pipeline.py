
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from mfasha import config
from mfasha.llm import NO_ANSWER
from mfasha.pipeline import Mfasha
from mfasha.retriever import Retriever

PASSAGES = [
    {"pid": "A1", "text": "Intama ihaka iminsi 149-152, (amezi 5). Yonsa amezi atatu."},
    {"pid": "A2", "text": "Inkoko zirwaye zanduza izindi."},
]
EMB = np.array([[1, 0], [0, 1]], dtype=np.float32)


def make_bot(llm, vec=(1.0, 0.0)):
    retr = Retriever(PASSAGES, EMB, lambda q: np.array(vec, dtype=np.float32))
    return Mfasha(retr, transcriber=type("T", (), {"transcribe": lambda s, a: "intama zororoka gute"})(), llm=llm)


def test_ok_answer():
    r = make_bot(lambda q, h: "Yonsa amezi atatu.").ask(text="Intama zihaka igihe kingana iki?")
    assert r.status == "ok" and r.answer == "Yonsa amezi atatu." and not r.guarded and r.hits[0].pid == "A1"


def test_refusal_passes_through():
    r = make_bot(lambda q, h: NO_ANSWER).ask(text="Ni nde watwaye igikombe cy'isi?")
    assert r.status == "refused" and r.answer == NO_ANSWER


def test_invented_number_is_blocked():
    r = make_bot(lambda q, h: "Intama ihaka iminsi 300.").ask(text="Intama zihaka igihe kingana iki?")
    assert r.guarded and "300" not in r.answer and "149-152" in r.answer


def test_llm_failure():
    r = make_bot(lambda q, h: None).ask(text="Intama zororoka gute?")
    assert r.status == "llm_error" and r.answer is None


def test_empty_question():
    assert make_bot(lambda q, h: "x").ask(text="   ").status == "empty"


def test_voice_path_sets_heard():
    r = make_bot(lambda q, h: "Yonsa amezi atatu.").ask(audio=np.zeros(16000, dtype=np.float32))
    assert r.heard == "intama zororoka gute" and r.status == "ok"


def test_min_score_refuses_without_calling_llm(monkeypatch):
    monkeypatch.setattr(config, "MIN_RETRIEVAL_SCORE", 0.9)
    called = []
    bot = make_bot(lambda q, h: called.append(1) or "x", vec=(0.5, 0.5))
    r = bot.ask(text="Perezida wa Amerika ni nde?")
    assert r.status == "refused" and not called
