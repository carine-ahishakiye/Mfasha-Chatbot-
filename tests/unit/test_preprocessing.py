from mfasha.nlp import TextCleaner, tokenize


def test_clean_fixes_spaces_before_punctuation_and_apostrophes():
    assert TextCleaner().clean("Ibigori , n' ibishyimbo  ?") == "Ibigori, n'ibishyimbo?"


def test_clean_normalises_curly_apostrophes():
    assert TextCleaner().clean("n\u2019ibishyimbo") == "n'ibishyimbo"


def test_greeting_is_removed_when_enough_words_remain():
    out = TextCleaner().preprocess_question("Muraho, ndashaka kubaza uko nahinga ibigori")
    assert out.lower().startswith("uko nahinga")


def test_greeting_kept_when_it_is_all_there_is():
    assert TextCleaner().preprocess_question("Muraho") == "Muraho"


def test_empty_and_none_inputs():
    assert TextCleaner().clean("") == ""
    assert TextCleaner().clean(None) == ""


def test_tokenize_lowercases_and_splits_on_punctuation():
    assert tokenize("Ibigori, BITERA!") == ["ibigori", "bitera"]
