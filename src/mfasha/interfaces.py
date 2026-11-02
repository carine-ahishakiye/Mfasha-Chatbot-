"""Abstractions (Dependency Inversion). The pipeline depends on these, never on a concrete model.

Every candidate from the proposal (baseline or pretrained) implements one of these, so a
component can be swapped by changing configuration and nothing else (proposal sections 3.8, 3.9).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from mfasha.domain.models import Passage, RetrievalHit


class Retriever(ABC):
    """Finds the knowledge-base passages that best match a question."""

    name: str = "retriever"

    @abstractmethod
    def index(self, passages: Sequence[Passage]) -> None:
        """Build whatever structure is needed to search `passages`."""

    @abstractmethod
    def search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        """Return up to `k` hits ordered best first, with scores normalised to 0..1."""


class Classifier(ABC):
    """Assigns a question to one agricultural category."""

    name: str = "classifier"

    @abstractmethod
    def predict(self, text: str) -> str:
        ...


class SpeechToText(ABC):
    name: str = "stt"

    @abstractmethod
    def transcribe(self, samples, sample_rate: int) -> str:
        """`samples` is a mono float32 numpy array."""


class TextToSpeech(ABC):
    name: str = "tts"

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Return a WAV file as bytes."""
