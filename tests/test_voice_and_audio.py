import io

import numpy as np

from mfasha.audio import decode_audio, wav_bytes
from mfasha.interfaces import SpeechSynthesizer
from mfasha.voice import VoiceService, spoken_part


class CountingSpeaker(SpeechSynthesizer):
    sr = 16000

    def __init__(self):
        self.calls = 0

    def speak(self, text):
        self.calls += 1
        return np.zeros(self.sr // 10, dtype=np.float32), text


def test_short_text_is_spoken_whole():
    assert spoken_part("Yonsa amezi atatu.", 250) == ("Yonsa amezi atatu.", False)


def test_long_text_is_cut_at_a_sentence_and_flagged():
    text = "Inka zirya ibyatsi. " * 30
    spoken, cut = spoken_part(text, 100)
    assert cut and len(spoken) <= 100 and spoken.endswith(".")


def test_empty_text_has_no_speech():
    assert spoken_part("   ")[0] == ""


def test_voice_is_made_once_then_served_from_the_cache():
    speaker = CountingSpeaker()
    voice = VoiceService(speaker)
    first, second = voice.get("Yonsa amezi atatu."), voice.get("Yonsa amezi atatu.")
    assert first == second and speaker.calls == 1 and first[0][:4] == b"RIFF"


def test_cache_keeps_only_the_newest_voices():
    voice = VoiceService(CountingSpeaker(), cache_size=2)
    for text in ("Inka.", "Intama.", "Ingurube."):
        voice.get(text)
    assert len(voice._cache) == 2


def test_wav_round_trip():
    wave = np.sin(np.linspace(0, 100, 16000)).astype(np.float32) * 0.5
    decoded = decode_audio(wav_bytes(wave, 16000), sr=16000)
    assert len(decoded) == len(wave) and np.abs(decoded - wave).max() < 1e-3
