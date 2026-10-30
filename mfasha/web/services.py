"""Objects the routes share. One instance per application, so tests can build as many apps as they like."""
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .. import config
from ..confidence import ConfidencePolicy
from ..interfaces import SpeechSynthesizer
from ..pipeline import Mfasha
from ..ratelimit import RateLimiter
from ..voice import VoiceService


@dataclass
class Services:
    bot: Optional[Mfasha] = None
    feedback_file: Path = config.FEEDBACK_FILE
    confidence: ConfidencePolicy = field(default_factory=ConfidencePolicy.from_config)
    ask_limit: RateLimiter = field(default_factory=lambda: RateLimiter(20))
    audio_limit: RateLimiter = field(default_factory=lambda: RateLimiter(8))
    speak_limit: RateLimiter = field(default_factory=lambda: RateLimiter(40))
    voice: VoiceService = field(default_factory=VoiceService)
    asr_lock: threading.Lock = field(default_factory=threading.Lock)   # one job on the recogniser at a time

    @property
    def ready(self) -> bool:
        return self.bot is not None and self.voice.speaker is not None

    def attach_speaker(self, speaker: SpeechSynthesizer) -> None:
        self.voice.speaker = speaker
