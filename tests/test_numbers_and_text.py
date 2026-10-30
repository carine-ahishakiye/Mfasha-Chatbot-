import sys
from pathlib import Path

from mfasha.kin_numbers import speech_prep, number_words
from mfasha.text_utils import clean_text, tidy, ungrounded_numbers, verbatim_share


def test_basic_numbers():
    assert number_words(0) == "zeru"
    assert number_words(5) == "gatanu"
    assert number_words(20) == "makumyabiri"
    assert number_words(100) == "ijana"
    assert number_words(1000) == "igihumbi"


def test_percent_unit_range_decimal():
    assert speech_prep("60 %") == "mirongo itandatu ku ijana"
    assert speech_prep("litiro 20") .startswith("litiro ")
    assert "kugeza kuri" in speech_prep("amezi 4-5")
    assert "virigule" in speech_prep("kg 2,5")
    assert speech_prep("2 kg") == "kabiri kilo"


def test_no_digits_left():
    for s in ["Ifumbire 17-17-17 ikoreshwa kuri 5%", "Igiciro ni 25000", "Intama ihaka iminsi 149-152"]:
        assert not any(ch.isdigit() for ch in speech_prep(s)), s


def test_clean_and_tidy():
    assert clean_text("inka , n' ibiryo .") == "inka, n'ibiryo."
    assert tidy("Umusaruro w'inkwavuIyo inkoko") == "Umusaruro w'inkwavu Iyo inkoko"


def test_number_guard_whole_number():
    passages = ["Intama ihaka iminsi 149-152, (amezi 5)", "ikibazo 15"]
    assert ungrounded_numbers("amezi 5", passages) == []
    assert ungrounded_numbers("iminsi 50", passages) == ["50"]      # '5' and '15' are in the passages, '50' is not
    assert ungrounded_numbers("12,5 kg", ["12.5 kg"]) == []          # comma and point are the same number


def test_verbatim_share():
    p = ["Inka zirya ibyatsi. Zinywa amazi menshi."]
    assert verbatim_share("Inka zirya ibyatsi.", p) == 1.0
    assert verbatim_share("Inka zirya ibyatsi. Zirya amabuye.", p) == 0.5
