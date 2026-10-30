
from abc import ABC, abstractmethod
from typing import List, NamedTuple, Tuple

import numpy as np


class Hit(NamedTuple):
    """One retrieved passage."""
    pid: str
    text: str
    score: float


class PassageSearcher(ABC):
    """Finds the stored passages that best answer a question."""

    @abstractmethod
    def search(self, question: str, k: int = None) -> List[Hit]:
        """Top-k passages for the question, best first."""


class SpeechRecognizer(ABC):
    """Turns audio into text."""

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """audio: float32 mono at 16 kHz."""


class SpeechSynthesizer(ABC):
    """Turns text into audio."""

    sr: int                                     # sampling rate of the audio it returns

    @abstractmethod
    def speak(self, text: str) -> Tuple[np.ndarray, str]:
        """Returns (float32 waveform, the text that was actually spoken)."""
