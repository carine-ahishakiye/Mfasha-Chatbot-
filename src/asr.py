from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

SAMPLE_RATE = 16_000
ASR_ID = "facebook/mms-1b-all"
ASR_LANG = "kin"
ADAPTER_NAME = "mms_kin_adapter_finetuned.pt"
MAX_SECONDS = 30  # longer recordings are cut, to keep memory and time under control

_lock = threading.Lock()        # protects loading
_infer_lock = threading.Lock()  # one recording at a time (the model is big)
_state: dict = {}               # filled by load(): processor, model, device, adapter


def _find_root() -> Path:
    here = Path(__file__).resolve().parent
    return next((p for p in [here, *here.parents] if (p / "src").exists()), here.parent)


def _find_adapter(adapter_path=None) -> Path | None:
    """Explicit path, then $ASR_ADAPTER, then data/, models/, models/asr/, project root."""
    candidates = []
    if adapter_path:
        candidates.append(Path(adapter_path))
    if os.environ.get("ASR_ADAPTER"):
        candidates.append(Path(os.environ["ASR_ADAPTER"]))
    root = _find_root()
    folders = [root / "data", root / "models", root / "models" / "asr", root]
    candidates += [f / ADAPTER_NAME for f in folders]
    found = next((c for c in candidates if c.exists()), None)
    if found:
        return found
    # a second download is renamed by Windows, e.g. "mms_kin_adapter_finetuned(1).pt": newest wins
    stem = Path(ADAPTER_NAME).stem
    similar = [p for f in folders if f.is_dir() for p in f.glob(stem + "*.pt")]
    return max(similar, key=lambda p: p.stat().st_mtime) if similar else None


def _unwrap(weights) -> dict:
    """Accept a plain state dict, or one saved inside {"state_dict": ...} or with 'module.' prefixes."""
    if isinstance(weights, dict) and isinstance(weights.get("state_dict"), dict):
        weights = weights["state_dict"]
    return {(k[7:] if k.startswith("module.") else k): v for k, v in weights.items()}


def load(adapter_path=None, device: str | None = None, use_finetuned: bool = True) -> dict:
    """Load the speech model (once). Safe to call many times."""
    with _lock:
        if _state:
            return _state
        import torch
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        model_id = os.environ.get("ASR_MODEL_ID", ASR_ID)
        print(f"[asr] loading {model_id} ({ASR_LANG}) on {device} ...", file=sys.stderr)
        t0 = time.time()

        path = None
        if use_finetuned:
            path = _find_adapter(adapter_path)
            if path is None and os.environ.get("ASR_ALLOW_ORIGINAL") != "1":
                raise FileNotFoundError(
                    f"{ADAPTER_NAME} was not found in data/, models/ or models/asr/. "
                    "Copy it there, or set ASR_ALLOW_ORIGINAL=1 to run the original (not fine-tuned) adapter.")

        processor = AutoProcessor.from_pretrained(model_id, target_lang=ASR_LANG)
        model = Wav2Vec2ForCTC.from_pretrained(
            model_id, target_lang=ASR_LANG, ignore_mismatched_sizes=True
        ).to(device)
        model.eval()

        adapter = "original"
        if path is not None:
            try:
                weights = torch.load(path, map_location="cpu", weights_only=True)
            except TypeError:                      # older torch has no weights_only
                weights = torch.load(path, map_location="cpu")
            weights = _unwrap(weights)
            n = 0
            with torch.no_grad():
                for name, p in model.named_parameters():
                    if name in weights:
                        p.copy_(weights[name].to(p.device))
                        n += 1
            if n == 0:
                raise RuntimeError("the adapter file does not match this model: 0 tensors were loaded")
            if n != len(weights):
                print(f"[asr] WARNING: only {n} of {len(weights)} adapter tensors matched", file=sys.stderr)
            adapter = "finetuned"
            print(f"[asr] fine-tuned adapter loaded ({n} tensors) from {path}", file=sys.stderr)

        if device == "cpu" and os.environ.get("ASR_QUANTIZE") == "1":
            # EXPERIMENTAL: smaller and often faster on a CPU, but you must re-measure WER with it
            model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
            adapter += "+int8"
            print("[asr] dynamic int8 quantization on (experimental)", file=sys.stderr)

        _state.update(processor=processor, model=model, device=device, adapter=adapter)
        print(f"[asr] ready in {time.time() - t0:.0f} s (adapter: {adapter})", file=sys.stderr)
        return _state


def status() -> dict:
    """For /api/health: is the speech model loaded, and which adapter is active?"""
    return {"loaded": bool(_state), "adapter": _state.get("adapter"), "device": _state.get("device")}


def _audio_suffix(content_type: str | None, raw: bytes) -> str:
    """Choose a temporary-file suffix so ffmpeg can decode browser recordings."""
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    suffixes = {
        "audio/wav": ".wav", "audio/wave": ".wav", "audio/x-wav": ".wav",
        "audio/webm": ".webm", "video/webm": ".webm",
        "audio/ogg": ".ogg", "application/ogg": ".ogg",
        "audio/mp4": ".m4a", "video/mp4": ".mp4", "audio/x-m4a": ".m4a",
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/flac": ".flac",
    }
    if mime in suffixes:
        return suffixes[mime]
    if raw.startswith((b"RIFF", b"RIFX")):
        return ".wav"
    if raw.startswith(b"OggS"):
        return ".ogg"
    if raw.startswith(b"fLaC"):
        return ".flac"
    if len(raw) > 12 and raw[4:8] == b"ftyp":
        return ".m4a"
    if raw.startswith(b"ID3"):
        return ".mp3"
    return ".wav"


def to_audio(source, sr: int = SAMPLE_RATE, content_type: str | None = None):
    """File path, raw bytes, or numpy array -> mono float32 array at 16 kHz."""
    import numpy as np

    if isinstance(source, np.ndarray):
        if np.issubdtype(source.dtype, np.integer):     # int16 PCM must be scaled to [-1, 1]
            y = source.astype(np.float32) / float(np.iinfo(source.dtype).max + 1)
        else:
            y = source.astype(np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1 if y.shape[1] <= 8 else 0)
        if sr != SAMPLE_RATE:
            import librosa
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
    elif isinstance(source, (bytes, bytearray)):
        import librosa
        raw = bytes(source)
        temp_path = None
        try:
            # A real filename lets librosa/audioread hand compressed browser
            # formats (WebM/Opus, Ogg, MP4) to ffmpeg when it is installed.
            with tempfile.NamedTemporaryFile(suffix=_audio_suffix(content_type, raw),
                                             delete=False) as tmp:
                tmp.write(raw)
                temp_path = tmp.name
            y, _ = librosa.load(temp_path, sr=SAMPLE_RATE, mono=True,
                                duration=MAX_SECONDS)
        except Exception as e:
            raise ValueError("could not read this audio. Send a WAV file (16-bit, mono is best). "
                             "Compressed browser formats such as WebM/Opus need ffmpeg installed. "
                             f"({type(e).__name__}: {e})") from e
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    else:
        import librosa
        y, _ = librosa.load(str(source), sr=SAMPLE_RATE, mono=True,
                            duration=MAX_SECONDS)
    return y[: MAX_SECONDS * SAMPLE_RATE]


def transcribe(source, sr: int = SAMPLE_RATE, content_type: str | None = None) -> str:
    """Speech -> text. `source` can be a file path, bytes, or a float array."""
    import torch

    st = load()
    audio = to_audio(source, sr, content_type=content_type)
    if len(audio) < 1600:  # under 0.1 s: nothing to recognise
        return ""
    with _infer_lock:
        inputs = st["processor"](audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").to(st["device"])
        with torch.inference_mode():
            logits = st["model"](**inputs).logits
        return st["processor"].decode(torch.argmax(logits, dim=-1)[0]).strip()


def warmup() -> float:
    """Run one second of silence, so the first real request is not slow. Returns seconds taken."""
    import numpy as np
    t0 = time.time()
    transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32))
    return time.time() - t0


def ask_any(bot, text: str | None = None, audio=None, sr: int = SAMPLE_RATE):
   
    if audio is not None:
        text = transcribe(audio, sr)
    text = (text or "").strip()
    if not text:
        return "", None
    return text, bot.ask(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python src/asr.py question.wav [more.wav ...]")
    load()
    print("warm-up: %.1f s" % warmup())
    for f in sys.argv[1:]:
        t0 = time.time()
        heard = transcribe(f)
        print(f"{f}\n  heard: {heard!r}\n  time : {time.time() - t0:.1f} s")