"""Text preprocessing (pipeline stage 3). Ported from the notebook's `clean_text` and `qkey`."""
from __future__ import annotations

import re

_WORD = re.compile(r"\w+")

# "Muraho, ndashaka kubaza ..." -> the greeting carries no information about the topic
_FILLER = r"(?:ndashaka|nshaka|nifuza|ndifuza|kubaza|kubabaza|kumenya|ese)"
_GREETING = re.compile(
    rf"^\s*(?:muraho|mwaramutse|mwiriwe|bonjour|hello)\b.*?(?:\b{_FILLER}\b[\s,]*)+",
    re.IGNORECASE,
)


def tokenize(text: str) -> list[str]:
    """Lower-case word tokens. Shared by every lexical retriever so they all see the same terms."""
    return _WORD.findall(text.lower())


class TextCleaner:
    """Standardises spacing, apostrophes and punctuation so that typed text, speech-to-text output
    and knowledge-base passages all look the same to the models."""

    def __init__(self, strip_greeting: bool = True, min_words_after_greeting: int = 3):
        self._strip_greeting = strip_greeting
        self._min_words = min_words_after_greeting

    def clean(self, text: str) -> str:
        text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
        text = re.sub(r"(?<=\w)'\s+(?=\w)", "'", text)      # "n' ibishyimbo" -> "n'ibishyimbo"
        text = re.sub(r"(\.\s*){2,}", "... ", text)
        text = re.sub(r"\s+([,.;:!?)\]])", r"\1", text)      # no space before punctuation
        text = re.sub(r"([(\[])\s+", r"\1", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def preprocess_question(self, text: str) -> str:
        """Clean a farmer's question and drop a leading greeting if enough words remain."""
        cleaned = self.clean(text)
        if self._strip_greeting:
            without = _GREETING.sub("", cleaned)
            if len(without.split()) >= self._min_words:
                cleaned = without
        return cleaned
