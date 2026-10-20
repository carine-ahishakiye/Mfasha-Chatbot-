"""
server.py - Mfasha web server (FastAPI).

Serves static/index.html and a small JSON API on top of src/chatbot.py.

    python server.py                    -> http://127.0.0.1:8000
    python server.py --host 0.0.0.0     -> reachable from a phone on the same Wi-Fi

Routes
    GET  /              the web page (static/index.html)
    POST /api/ask       {"question": "..."}  -> answer, confidence tier, related passages
    POST /api/transcribe raw audio bytes     -> recognized text
    POST /api/speak     {"text": "..."}      -> audio/wav
    POST /api/feedback  {"question", "passage_id", "vote"}  -> saved to results/feedback.csv
    GET  /api/health    chatbot and speech-module status

Needs: src/chatbot.py, chunks.jsonl, chunk_emb_e5.npy and the fine-tuned model in ./models
(or set MODEL_ID to a Hugging Face model repo, plus HF_TOKEN if it is private).
"""
import argparse
import csv
import importlib.util
import os
import sys
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "src"):
    sys.path.insert(0, str(p))
import chatbot as cb  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

STATIC_DIR = HERE / "static"
# the page lives in static/index.html (a copy next to server.py also works)
INDEX_FILE = STATIC_DIR / "index.html" if (STATIC_DIR / "index.html").exists() else HERE / "index.html"
LOG_FILE = HERE / "results" / "app_log.csv"
FEEDBACK_FILE = HERE / "results" / "feedback.csv"

RATE_LIMIT = 30                 # questions per minute per visitor (protects a shared demo)
MAX_AUDIO_BYTES = 20 * 1024 * 1024
_hits = defaultdict(deque)
_file_lock = threading.Lock()
_bot_lock = threading.Lock()    # the model answers one question at a time
_voice_modules = {}


# ------------------------------------------------------------------ loading
def load_bot():
    chunks = cb.locate(HERE, "chunks.jsonl")
    emb = cb.locate(HERE, "chunk_emb_e5.npy")
    if not chunks or not emb:
        sys.exit("Could not find chunks.jsonl or chunk_emb_e5.npy under " + str(HERE))

    local = HERE / "models"
    if (local / "model.safetensors").exists():
        model_ref = str(local)                          # your laptop layout
    else:
        model_ref = os.getenv("MODEL_ID", "")           # deployment: a Hugging Face repo id
        if not model_ref:
            sys.exit("No local model in ./models and MODEL_ID is not set.")
    print("model :", model_ref)
    print("chunks:", chunks)

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_ref, device="cpu", token=os.getenv("HF_TOKEN") or None)
    model.max_seq_length = 256
    return cb.Chatbot(chunks_path=chunks, emb_path=emb, model=model)


# ------------------------------------------------------------------ helpers
def append_row(path, header, row):
    with _file_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(header)
            w.writerow(row)


def too_many(ip):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def _voice_file(name):
    """Find the optional speech module in src/ or beside server.py."""
    return next((p for p in (HERE / "src" / f"{name}.py", HERE / f"{name}.py")
                 if p.is_file()), None)


def _voice_module(name):
    """Import ASR/TTS lazily so text chat still starts if speech isn't configured."""
    if name in _voice_modules:
        return _voice_modules[name]
    path = _voice_file(name)
    if path is None:
        raise HTTPException(503, f"{name}.py is missing; put it in src/ or beside server.py.")
    try:
        spec = importlib.util.spec_from_file_location(f"_mfasha_{name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        raise HTTPException(503, f"Could not load {name}.py: {type(exc).__name__}: {exc}") from exc
    _voice_modules[name] = module
    return module


def _voice_status(name):
    """Report file/module state without loading the large speech model."""
    if _voice_file(name) is None:
        return {"module_found": False, "loaded": False}
    try:
        module = _voice_module(name)
        return {"module_found": True, **module.status()}
    except HTTPException as exc:
        return {"module_found": True, "loaded": False, "error": exc.detail}


class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=600)


class VoteIn(BaseModel):
    question: str = Field(..., max_length=500)
    passage_id: Optional[str] = None
    vote: Literal["helpful", "not_helpful"]


# ------------------------------------------------------------------ the app
def create_app(bot=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.bot = bot if bot is not None else load_bot()
        print("ready:", len(app.state.bot.chunks), "chunks")
        yield

    app = FastAPI(title="Mfasha", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.get("/")
    def index():
        if not INDEX_FILE.exists():
            raise HTTPException(500, "index.html not found. Put it in the static folder: " + str(STATIC_DIR))
        return FileResponse(INDEX_FILE, media_type="text/html",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/api/health")
    def health(request: Request):
        return {
            "ok": True,
            "chunks": len(request.app.state.bot.chunks),
            "voice": {"asr": _voice_status("asr"), "tts": _voice_status("tts")},
        }

    @app.post("/api/ask")
    def ask(body: AskIn, request: Request):
        ip = request.client.host if request.client else "unknown"
        if too_many(ip):
            raise HTTPException(429, "Too many questions, please wait a moment.")
        question = body.question.strip()
        if not question:
            raise HTTPException(400, "Empty question.")

        t0 = time.time()
        with _bot_lock:
            r = request.app.state.bot.ask(question)
        seconds = round(time.time() - t0, 2)

        append_row(LOG_FILE,
                   ["time", "question", "refused", "tier", "confidence", "passage_id", "seconds"],
                   [datetime.now().isoformat(timespec="seconds"), question, r["refused"],
                    r["tier"], round(r["confidence"], 3), r["passage_id"], seconds])
        return {
            "refused": r["refused"],
            "answer": r["answer"],
            "tier": r["tier"],                       # high | medium | low | none
            "confidence": round(r["confidence"], 3),
            "passage_id": r["passage_id"],
            "alternatives": [a["text"] for a in r["alternatives"]],
        }

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        """Accept raw audio bytes (WAV recommended; browser WebM needs ffmpeg)."""
        ip = request.client.host if request.client else "unknown"
        if too_many(ip):
            raise HTTPException(429, "Too many requests, please wait a moment.")
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Audio is too large; the limit is 20 MB.")
        audio = bytearray()
        async for chunk in request.stream():
            if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                raise HTTPException(413, "Audio is too large; the limit is 20 MB.")
            audio.extend(chunk)
        if not audio:
            raise HTTPException(400, "No audio was received.")
        try:
            text = await run_in_threadpool(
                _voice_module("asr").transcribe, bytes(audio),
                content_type=request.headers.get("content-type", ""),
            )
        except ValueError as exc:
            raise HTTPException(415, str(exc)) from exc
        text = (text or "").strip()
        return {"text": text, "empty": not bool(text)}

    @app.post("/api/speak")
    def speak(body: SpeakIn):
        """Synthesize Kinyarwanda text and return a browser-playable WAV."""
        try:
            result = _voice_module("tts").speak(body.text)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, f"Speech synthesis failed: {type(exc).__name__}: {exc}") from exc
        if not result.get("wav"):
            raise HTTPException(422, "; ".join(result.get("notes", []) or ["No speech was generated."]))
        return Response(
            content=result["wav"],
            media_type="audio/wav",
            headers={
                "X-Audio-Sample-Rate": str(result.get("sample_rate") or ""),
                "X-Spoken-Seconds": str(result.get("seconds") or 0),
            },
        )

    @app.post("/api/feedback")
    def feedback(body: VoteIn):
        append_row(FEEDBACK_FILE,
                   ["time", "question", "passage_id", "vote"],
                   [datetime.now().isoformat(timespec="seconds"), body.question,
                    body.passage_id, body.vote])
        return {"ok": True}

    if STATIC_DIR.exists():                      # any other files you add later (logo, images)
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    args = ap.parse_args()
    print("page  :", INDEX_FILE, "(found)" if INDEX_FILE.exists() else "(MISSING)")
    print(f"open  : http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")