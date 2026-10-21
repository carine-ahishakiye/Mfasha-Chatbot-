from __future__ import annotations

import io
import os
import re
import sys
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path

TTS_ID = "facebook/mms-tts-kin"   # change with the TTS_MODEL_ID environment variable
SEED = 0                          # same text -> same voice every time
MAX_CHARS = 600                  # cap on how much one answer is read aloud (shorter = faster)
MAX_SENTENCES = 5                # read only the first sentences of an answer (biggest speed gain)
PIECE_MAX = 220                   # longest piece sent to the voice at once
PAUSE_SECONDS = 0.30
CACHE_SIZE = 64                   # how many finished answers are kept in memory

_lock = threading.Lock()
_infer_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_state: dict = {}


def _local_model() -> str | None:
    """models/mms-tts-kin next to the project, if it was saved there."""
    here = Path(__file__).resolve().parent
    root = next((p for p in [here, *here.parents] if (p / "src").exists()), here.parent)
    folder = root / "models" / "mms-tts-kin"
    return str(folder) if (folder / "config.json").exists() else None


def load(model_id: str | None = None, device: str | None = None) -> dict:
    """Load the voice model (once). Safe to call many times."""
    with _lock:
        if _state:
            return _state
        import torch
        from transformers import AutoTokenizer, VitsModel

        model_id = model_id or os.environ.get("TTS_MODEL_ID") or _local_model() or TTS_ID
        device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        threads = os.environ.get("TTS_THREADS")
        if threads and threads.isdigit():
            torch.set_num_threads(int(threads))
        print(f"[tts] loading {model_id} on {device} ...", file=sys.stderr)
        t0 = time.time()
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = VitsModel.from_pretrained(model_id).to(device)
        model.eval()
        _state.update(tokenizer=tokenizer, model=model, device=device, model_id=model_id,
                      sample_rate=int(model.config.sampling_rate))
        print(f"[tts] ready in {time.time() - t0:.0f} s (sample rate {_state['sample_rate']} Hz)", file=sys.stderr)
        return _state


def status() -> dict:
    return {"loaded": bool(_state), "model": _state.get("model_id"), "device": _state.get("device"),
            "cached_answers": len(_cache)}


# ----------------------------------------------------------------- text preparation
def prepare(text: str, max_chars: int = MAX_CHARS, max_sentences: int | None = MAX_SENTENCES):
    """Text -> (pieces to speak, notes). Pure text work: no model needed."""
    notes: list[str] = []
    t = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text or "")           # drop bracketed parts
    if t != (text or ""):
        notes.append("text in brackets is not read aloud")
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)                  # no space before punctuation
    t = re.sub(r"([,.;:!?])(\s*[,;])+", r"\1", t)           # ": ," left behind by a dropped bracket
    t = re.sub(r"\s+", " ", t).strip()

    sentences = [s.strip() for s in re.split(r"(?<=[.?!;:])\s+", t) if s.strip()]
    kept, skipped = [], 0
    for s in sentences:
        if any(ch.isdigit() for ch in s):
            skipped += 1
        else:
            kept.append(s)
    if skipped:
        notes.append(f"{skipped} sentence(s) with numbers are not read aloud: read the text")

    if max_sentences and len(kept) > max_sentences:
        kept = kept[:max_sentences]
        notes.append(f"only the first {max_sentences} sentences are read aloud")

    pieces, cur, used, truncated = [], "", 0, False
    for s in kept:
        separator = 1 if used else 0
        available = max_chars - used - separator
        if available <= 0:
            truncated = True
            break
        if len(s) > available:
            clipped = s[:available].rstrip()
            if " " in clipped:
                clipped = clipped.rsplit(" ", 1)[0]
            if not clipped:
                clipped = s[:available]
            truncated = True
        else:
            clipped = s

        for word in clipped.split():
            while len(word) > PIECE_MAX:
                part, word = word[:PIECE_MAX], word[PIECE_MAX:]
                if cur:
                    pieces.append(cur)
                    cur = ""
                pieces.append(part)
            if cur and len(cur) + 1 + len(word) > PIECE_MAX:
                pieces.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        used += separator + len(clipped)
        if truncated:
            break
    if cur:
        pieces.append(cur)
    if truncated:
        notes.append("only the first part is read aloud")
    return pieces, notes


# ----------------------------------------------------------------- speech
def to_wav_bytes(samples, sample_rate: int) -> bytes:
    """float samples in [-1, 1] -> 16-bit mono WAV file as bytes."""
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _synth(piece: str):
    """One short piece of text -> float32 numpy samples (or None if nothing can be spoken)."""
    import torch
    st = load()
    inputs = st["tokenizer"](piece, return_tensors="pt")
    if inputs["input_ids"].shape[-1] == 0:      # only characters the voice does not know
        return None
    inputs = inputs.to(st["device"])
    with _infer_lock:
        torch.manual_seed(SEED)
        with torch.inference_mode():
            out = st["model"](**inputs)
    wave_ = getattr(out, "waveform", None)
    if wave_ is None:
        wave_ = out.audio
    return wave_[0].float().cpu().numpy()


def _cache_get(key: tuple):
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
        return hit


def _cache_put(key: tuple, value: dict) -> None:
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)


def speak(text: str, max_chars: int = MAX_CHARS, max_sentences: int | None = MAX_SENTENCES) -> dict:
    """Text -> {"wav": bytes or None, "sample_rate", "seconds", "spoken_chars", "notes"}.

    Repeated answers come from a small in-memory cache, so they play instantly."""
    import numpy as np

    pieces, notes = prepare(text, max_chars, max_sentences)
    if not pieces:
        return {"wav": None, "sample_rate": None, "seconds": 0.0, "spoken_chars": 0,
                "notes": notes + ["nothing to read aloud"]}

    key = (os.environ.get("TTS_MODEL_ID", TTS_ID), tuple(pieces))
    cached = _cache_get(key)
    if cached is not None:
        return {**cached, "notes": list(notes), "synthesis_time": 0.0, "cached": True}

    t0 = time.time()
    sr = load()["sample_rate"]
    pause = np.zeros(int(PAUSE_SECONDS * sr), dtype=np.float32)
    chunks = []
    for p in pieces:
        y = _synth(p)
        if y is not None:
            chunks += [y, pause]
    if not chunks:
        return {"wav": None, "sample_rate": sr, "seconds": 0.0, "spoken_chars": 0,
                "notes": notes + ["the voice could not read this text"]}
    audio = np.concatenate(chunks[:-1])
    result = {"wav": to_wav_bytes(audio, sr), "sample_rate": sr, "seconds": round(len(audio) / sr, 1),
              "spoken_chars": sum(len(p) for p in pieces)}
    _cache_put(key, result)
    return {**result, "notes": notes, "synthesis_time": round(time.time() - t0, 1), "cached": False}


def warmup() -> float:
    t0 = time.time()
    _synth("Muraho")
    return time.time() - t0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: python src/tts.py "text to read" [out.wav]')
    res = speak(sys.argv[1])
    print("notes:", res["notes"] or "none")
    if res["wav"] is None:
        sys.exit("nothing was spoken")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "tts_test.wav")
    out.write_bytes(res["wav"])
    print(f"saved {out} | {res['seconds']} s of audio | made in {res['synthesis_time']} s")