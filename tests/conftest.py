import io
import wave
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from mfasha.api import create_app
from mfasha.config import ROOT, Settings
from mfasha.factory import build_knowledge_base, build_pipeline
from mfasha.interfaces import SpeechToText

SAMPLE = ROOT / "data" / "sample"

# A real question from the test_unseen split and the passage it belongs to (rice harvest timing).
IN_SCOPE_QUESTION = "igihe kiboneye cyo gusarura umuceri niryari?"
IN_SCOPE_PID = "A187T168"


class FakeSpeechToText(SpeechToText):
    """Returns a fixed sentence, whatever the audio is."""
    name = "fake-stt"

    def __init__(self, text=IN_SCOPE_QUESTION):
        self.text = text

    def transcribe(self, samples, sample_rate):
        return self.text


def make_wav(seconds=1.0, rate=16000, channels=1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.zeros(int(rate * seconds) * channels, dtype="<i2").tobytes())
    return buffer.getvalue()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return replace(Settings(), database_url="sqlite://", api_key="test-key")


@pytest.fixture(scope="session")
def knowledge_base(settings):
    return build_knowledge_base(settings)


@pytest.fixture()
def pipeline(settings, knowledge_base):
    pipe, _ = build_pipeline(settings, knowledge_base)
    pipe._stt = FakeSpeechToText()
    return pipe


@pytest.fixture()
def client(settings, knowledge_base, pipeline):
    app = create_app(settings=settings, pipeline=pipeline, knowledge_base=knowledge_base)
    with TestClient(app) as c:
        yield c