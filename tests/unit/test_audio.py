import pytest

from mfasha.domain.errors import InvalidAudioError
from mfasha.speech.audio import decode_wav
from tests.conftest import make_wav


def test_valid_wav_is_decoded_to_mono_16k():
    samples, rate = decode_wav(make_wav(1.0))
    assert rate == 16000 and len(samples) == 16000


def test_stereo_44k_is_mixed_down_and_resampled():
    samples, rate = decode_wav(make_wav(1.0, rate=44100, channels=2))
    assert rate == 16000 and abs(len(samples) - 16000) <= 1


def test_garbage_bytes_are_rejected():
    with pytest.raises(InvalidAudioError):
        decode_wav(b"this is not audio")


def test_too_long_audio_is_rejected():
    with pytest.raises(InvalidAudioError):
        decode_wav(make_wav(3.0), max_seconds=2.0)
