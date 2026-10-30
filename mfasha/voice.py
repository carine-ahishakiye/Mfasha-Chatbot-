
import hashlib
import re
import threading
import time
from collections import OrderedDict
from typing import Optional, Tuple

from . import config
from .audio import wav_bytes
from .interfaces import SpeechSynthesizer
from .text_utils import split_sentences, tidy


def spoken_part(text: str, max_chars: int = config.MAX_SPOKEN_CHARS) -> Tuple[str, bool]:
    """The part of the answer that is read aloud, never longer than max_chars. Returns (text, was_cut)."""
    text = tidy(text or "")[:5000]
    pieces = []
    for sentence in split_sentences(text) or ([text] if text else []):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
        else:                                  # a very long sentence: split it at commas and semicolons
            pieces.extend(p.strip() for p in re.split(r"(?<=[,;:])\s+", sentence) if p.strip())
    spoken, truncated = "", False
    for piece in pieces:
        if len(spoken) + len(piece) + 1 > max_chars:
            truncated = True
            if not spoken:                     # one piece alone is too long: cut it at a space
                cut = piece[:max_chars]
                spoken = cut[:cut.rfind(" ")] if " " in cut else cut
            break
        spoken = (spoken + " " + piece).strip()
    if truncated and spoken and spoken[-1] not in ".!?":
        spoken = spoken.rstrip(",;:") + "."
    return spoken, truncated


class VoiceService:
    """Makes the voice for an answer once, keeps recent voices, and never makes the same one twice at once."""

    def __init__(self, speaker: Optional[SpeechSynthesizer] = None,
                 max_chars: int = config.MAX_SPOKEN_CHARS, cache_size: int = config.VOICE_CACHE_SIZE):
        self.speaker = speaker
        self.max_chars, self.cache_size = max_chars, cache_size
        self._tts_lock = threading.Lock()          # one job on the speech model at a time
        self._cache_lock = threading.Lock()
        self._cache: "OrderedDict[str, tuple]" = OrderedDict()
        self._inflight = {}                        # voices being made right now

    def has_speech(self, text: str) -> bool:
        return bool(spoken_part(text, self.max_chars)[0])

    def get(self, text: str) -> Optional[Tuple[bytes, str]]:
        """(wav bytes, note) from the cache, or made now. None if it failed."""
        spoken, truncated = spoken_part(text, self.max_chars)
        if not spoken:
            return None
        key = hashlib.sha1(spoken.encode()).hexdigest()
        with self._cache_lock:
            if key in self._cache:
                return self._cache[key]
            done = self._inflight.get(key)
            mine = done is None
            if mine:
                done = self._inflight[key] = threading.Event()
        if not mine:                               # someone is already making it: wait for that
            done.wait(180)
            with self._cache_lock:
                return self._cache.get(key)
        try:
            t0 = time.time()
            with self._tts_lock:
                wav, _ = self.speaker.speak(spoken)
            result = (wav_bytes(wav, self.speaker.sr), "first part only" if truncated else "")
            with self._cache_lock:
                self._cache[key] = result
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            print(f"[timing] voice {time.time() - t0:.1f}s for {len(spoken)} characters")
            return result
        except Exception as e:
            print("speak error:", e)
            return None
        finally:
            with self._cache_lock:
                self._inflight.pop(key, None)
            done.set()

    def prefetch(self, text: str) -> None:
        """Start making the voice in the background while the farmer reads."""
        threading.Thread(target=self.get, args=(text,), daemon=True).start()
