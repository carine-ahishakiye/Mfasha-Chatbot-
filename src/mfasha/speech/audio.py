"""WAV helpers using only the standard library and numpy.

The browser converts the recording to 16 kHz mono 16-bit WAV before upload (frontend/app.js), so the
server needs no ffmpeg. Resampling is still done here for files that arrive at another rate.
"""
from __future__ import annotations

import io
import wave

import numpy as np

from mfasha.domain.errors import InvalidAudioError

TARGET_RATE = 16_000


def decode_wav(data: bytes, max_seconds: float = 30.0) -> tuple[np.ndarray, int]:
    """Return (mono float32 samples in -1..1, sample rate). Raises InvalidAudioError on bad input."""
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels, width, rate, frames = (wav.getnchannels(), wav.getsampwidth(),
                                             wav.getframerate(), wav.getnframes())
            if width != 2:
                raise InvalidAudioError("only 16-bit PCM WAV is supported")
            if rate <= 0 or frames == 0:
                raise InvalidAudioError("the audio file is empty")
            if frames / rate > max_seconds:
                raise InvalidAudioError(f"audio is longer than {max_seconds:.0f} seconds")
            raw = wav.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise InvalidAudioError("the file is not a valid WAV recording") from exc

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != TARGET_RATE:
        samples = _resample(samples, rate, TARGET_RATE)
        rate = TARGET_RATE
    return samples, rate


def _resample(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear interpolation. Good enough for speech at 8-48 kHz going to 16 kHz."""
    n_out = int(round(len(samples) * dst / src))
    positions = np.linspace(0, len(samples) - 1, n_out)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()
