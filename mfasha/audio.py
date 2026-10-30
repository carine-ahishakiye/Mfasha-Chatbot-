
import io
from math import gcd

import numpy as np

from . import config


def _resample(y: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
    if from_sr == to_sr:
        return y
    from scipy.signal import resample_poly
    g = gcd(int(from_sr), to_sr)
    return resample_poly(y, to_sr // g, int(from_sr) // g).astype(np.float32)


def _decode_wav(data: bytes, sr: int) -> np.ndarray:
    """Plain WAV only (used when PyAV is not installed)."""
    import soundfile as sf
    y, file_sr = sf.read(io.BytesIO(data), dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    return _resample(y, file_sr, sr)


def _decode_any(data: bytes, sr: int) -> np.ndarray:
    """Any container PyAV can open (webm, ogg, mp4, wav) -> mono float32."""
    import av
    container = av.open(io.BytesIO(data))
    stream = next(s for s in container.streams if s.type == "audio")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
    chunks = []
    for frame in container.decode(stream):
        for out in resampler.resample(frame):
            chunks.append(out.to_ndarray().reshape(-1))
    for out in resampler.resample(None):                 # flush what is left
        chunks.append(out.to_ndarray().reshape(-1))
    container.close()
    if not chunks:
        raise ValueError("no audio found")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def decode_audio(data: bytes, sr: int = config.ASR_SR) -> np.ndarray:
    """What the browser records (webm/ogg/mp4/wav) -> 16 kHz mono float32."""
    try:
        import av  # noqa: F401
    except ImportError:
        return _decode_wav(data, sr)
    return _decode_any(data, sr)


def wav_bytes(wav: np.ndarray, sr: int) -> bytes:
    """float32 waveform in [-1, 1] -> 16-bit PCM WAV file."""
    from scipy.io import wavfile
    pcm = (np.clip(wav, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    wavfile.write(buf, sr, pcm)
    return buf.getvalue()
