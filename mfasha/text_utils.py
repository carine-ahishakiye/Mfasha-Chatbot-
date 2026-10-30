"""Text cleaning and small text checks. Pure Python, no heavy imports."""
import re


def clean_text(t: str) -> str:
    """Same cleaning the retrieval data got in the notebook."""
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"(?<=\w)'\s+(?=\w)", "'", t)
    t = re.sub(r"(\.\s*){2,}", "... ", t)
    t = re.sub(r"\s+([,.;:!?)\]])", r"\1", t)
    t = re.sub(r"([(\[])\s+", r"\1", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def tidy(text: str) -> str:
    """Tidy a passage before showing and speaking it."""
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = text.replace("*", "")
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)      # a heading stuck to the next word
    text = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_key(t: str) -> str:
    """Lowercase, no punctuation: for matching and for scoring."""
    t = str(t).lower().replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"[^\w' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_sentences(text: str):
    return [p.strip() for p in re.split(r"(?<=[.!?;])\s+", text) if p.strip()]


def num_tokens(s: str) -> set:
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", s)}


def ungrounded_numbers(answer: str, passages) -> list:
    """Whole-number match: '5' is not accepted just because '15' is in a passage."""
    allowed = num_tokens(" ".join(passages))
    return sorted(num_tokens(answer) - allowed)


def verbatim_share(answer: str, passages) -> float:
    context = tidy(" ".join(passages))
    parts = split_sentences(tidy(answer))
    return sum(p in context for p in parts) / len(parts) if parts else 0.0
