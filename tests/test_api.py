
import io
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from mfasha import config
from mfasha.interfaces import SpeechRecognizer, SpeechSynthesizer
from mfasha.pipeline import Mfasha
from mfasha.retriever import Retriever
from mfasha.web import create_app
from mfasha.web.messages import MSG

FEEDBACK_TEST_FILE = Path(__file__).parent / "_feedback_test.jsonl"

PASSAGES = [
    {"pid": "A1", "text": "Intama ihaka iminsi 149-152, (amezi 5). Yonsa amezi atatu."},
    {"pid": "A2", "text": "Inkoko zirwaye zanduza izindi."},
    {"pid": "A3", "text": "Ingurube zonka amezi atatu, ibyumweru bitatu n'iminsi itatu."},
]
EMB = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)


class FakeSpeaker(SpeechSynthesizer):
    sr = 16000

    def speak(self, text):
        return np.zeros(self.sr // 2, dtype=np.float32), text


class FakeAsr(SpeechRecognizer):
    def transcribe(self, audio):
        return "intama zororoka gute"


def make_client(vec=(1.0, 0.0, 0.0), threshold=0.0):
    retr = Retriever(PASSAGES, EMB, lambda q: np.array(vec, dtype=np.float32))
    bot = Mfasha(retr, transcriber=FakeAsr(), threshold=threshold)
    return TestClient(create_app(bot=bot, speaker=FakeSpeaker(), feedback_file=FEEDBACK_TEST_FILE))


@pytest.fixture(autouse=True)
def clean_feedback():
    yield
    FEEDBACK_TEST_FILE.unlink(missing_ok=True)


def test_ask_returns_the_top_passage():
    r = make_client().post("/api/ask", json={"question": "Intama zihaka igihe kingana iki?"})
    body = r.json()
    assert r.status_code == 200 and body["refused"] is False and body["passage_id"] == "A1"
    assert "149-152" in body["answer"] and body["tier"] in {"high", "medium", "low"}


def test_ask_gives_related_passages():
    body = make_client(vec=(1.0, 0.5, 0.0)).post("/api/ask", json={"question": "Intama zororoka gute?"}).json()
    assert body["alternatives"] and all("Intama" not in a for a in body["alternatives"])


def test_off_topic_question_is_referred():
    c = make_client(vec=(0.5, 0.5, 0.5), threshold=0.9)
    body = c.post("/api/ask", json={"question": "Perezida wa Amerika ni nde?"}).json()
    assert body == {"answer": config.REFERRAL_MESSAGE, "refused": True, "passage_id": None}


def test_empty_question_is_rejected():
    for q in ("", "    "):
        r = make_client().post("/api/ask", json={"question": q})
        assert r.status_code == 400


def test_too_long_question_is_rejected():
    r = make_client().post("/api/ask", json={"question": "a" * (config.MAX_QUESTION_CHARS + 1)})
    assert r.status_code == 400


def test_missing_question_field_is_an_empty_question():
    assert make_client().post("/api/ask", json={}).status_code == 400


def test_bot_crash_gives_a_friendly_error():
    broken = Mfasha(Retriever(PASSAGES, EMB, lambda q: 1 / 0), threshold=0.0)
    c2 = TestClient(create_app(bot=broken, speaker=FakeSpeaker()))
    r = c2.post("/api/ask", json={"question": "Intama zororoka gute?"})
    assert r.status_code == 500 and r.json()["detail"] == MSG["error"]


def test_rate_limit_blocks_the_21st_question_in_a_minute():
    c = make_client()
    codes = [c.post("/api/ask", json={"question": "Intama zororoka gute?"}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_transcribe_returns_text_for_wav_audio():
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000, dtype=np.float32), 16000, format="WAV")
    r = make_client().post("/api/transcribe", content=buf.getvalue())
    assert r.status_code == 200 and r.json() == {"text": "intama zororoka gute"}


def test_transcribe_rejects_empty_and_broken_audio():
    c = make_client()
    assert c.post("/api/transcribe", content=b"").status_code == 400
    assert c.post("/api/transcribe", content=b"this is not audio").status_code == 400


def test_speak_returns_a_wav_file():
    r = make_client().post("/api/speak", json={"text": "Yonsa amezi atatu."})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"


def test_speak_rejects_empty_text():
    assert make_client().post("/api/speak", json={"text": "  "}).status_code == 400


def test_feedback_is_saved_and_bad_votes_are_rejected():
    c = make_client()
    ok = c.post("/api/feedback", json={"question": "q", "passage_id": "A1", "vote": "helpful"})
    assert ok.status_code == 200 and FEEDBACK_TEST_FILE.exists()
    assert c.post("/api/feedback", json={"question": "q", "vote": "maybe"}).status_code == 422


def test_health_and_pages():
    c = make_client()
    assert c.get("/health").json() == {"ready": True}
    assert c.get("/").status_code == 200 and c.get("/chat").status_code == 200


def test_search_is_fast():
    c = make_client()
    t0 = time.perf_counter()
    for _ in range(10):
        c.post("/api/ask", json={"question": "Intama zororoka gute?"})
    assert (time.perf_counter() - t0) / 10 < 0.5
