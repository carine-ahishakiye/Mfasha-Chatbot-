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

for path in (HERE, HERE / "src"):
    sys.path.insert(0, str(path))

import chatbot as cb  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402


STATIC_DIR = HERE / "static"
# The page lives in static/index.html (a copy next to server.py also works).
INDEX_FILE = (
    STATIC_DIR / "index.html"
    if (STATIC_DIR / "index.html").exists()
    else HERE / "index.html"
)
LOG_FILE = HERE / "results" / "app_log.csv"
FEEDBACK_FILE = HERE / "results" / "feedback.csv"

RATE_LIMIT = 30
MAX_AUDIO_BYTES = 20 * 1024 * 1024

_hits = defaultdict(deque)
_file_lock = threading.Lock()
_bot_lock = threading.Lock()
_voice_modules = {}
_voice_lock = threading.Lock()   # warm-up thread and requests must not import a module twice


# ------------------------------------------------------------------ loading
def _is_sentence_transformer_model(path):
    """Return whether path looks like a saved SentenceTransformers model."""
    path = Path(path)
    weight_names = {
        "model.safetensors",
        "pytorch_model.bin",
        "model.bin",
        "model.safetensors.index.json",
    }

    # SentenceTransformers.save() commonly stores transformer weights in
    # 0_Transformer/, while older/manual layouts put them at the model root.
    has_weights = path.is_dir() and any(
        item.is_file() and item.name in weight_names
        for item in path.rglob("*")
    )
    return path.is_dir() and (path / "modules.json").is_file() and has_weights


def _model_ref(data_dir):
    """Prefer the local fine-tuned retriever used to build the chunk embeddings."""
    configured = os.getenv("MFASHA_MODEL_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = HERE / path

        if not _is_sentence_transformer_model(path):
            raise FileNotFoundError(
                f"MFASHA_MODEL_DIR is not a saved SentenceTransformers model: {path}"
            )

        return str(path.resolve())

    # Check likely locations for the locally saved fine-tuned retriever.
    candidates = (
        HERE / "models",
        HERE / "models" / "kinya-retriever-e5",
        HERE / "models" / "kinya-retriever",
        data_dir / "kinya-retriever-e5",
        data_dir / "kinya-retriever",
    )

    for path in candidates:
        if _is_sentence_transformer_model(path):
            return str(path.resolve())

    # Optional deployment fallback. This is the retrieval model, not the
    # source of answer text; answers still come from chunks.jsonl.
    return os.getenv("MODEL_ID", "").strip()


def load_bot():
    data_dir = Path(
        os.getenv("MFASHA_DATA_DIR", str(HERE / "data"))
    ).expanduser()

    if not data_dir.is_absolute():
        data_dir = HERE / data_dir

    data_dir = data_dir.resolve()

    chunks = Path(
        os.getenv(
            "MFASHA_CHUNKS_PATH",
            str(data_dir / "chunks.jsonl"),
        )
    ).expanduser()

    embeddings = Path(
        os.getenv(
            "MFASHA_EMBEDDINGS_PATH",
            str(data_dir / "chunk_emb_e5.npy"),
        )
    ).expanduser()

    if not chunks.is_absolute():
        chunks = HERE / chunks

    if not embeddings.is_absolute():
        embeddings = HERE / embeddings

    chunks = chunks.resolve()
    embeddings = embeddings.resolve()

    missing = [
        str(path)
        for path in (chunks, embeddings)
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Chatbot index files are missing: "
            + ", ".join(missing)
            + ". Set MFASHA_DATA_DIR or MFASHA_CHUNKS_PATH / "
            "MFASHA_EMBEDDINGS_PATH."
        )

    model_ref = _model_ref(data_dir)

    if not model_ref:
        raise FileNotFoundError(
            "Fine-tuned retriever not found. Place it in ./models, "
            "set MFASHA_MODEL_DIR, or configure MODEL_ID for deployment."
        )

    print("model     :", model_ref)
    print("chunks    :", chunks)
    print("embeddings:", embeddings)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        model_ref,
        device="cpu",
        token=os.getenv("HF_TOKEN") or None,
    )
    model.max_seq_length = 256

    return cb.Chatbot(
        chunks_path=chunks,
        emb_path=embeddings,
        model=model,
    )


# ------------------------------------------------------------------ helpers
def append_row(path, header, row):
    with _file_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not path.exists()

        with open(path, "a", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(header)
            writer.writerow(row)


def too_many(ip):
    now = time.time()
    requests = _hits[ip]

    while requests and now - requests[0] > 60:
        requests.popleft()

    if len(requests) >= RATE_LIMIT:
        return True

    requests.append(now)
    return False


def _voice_file(name):
    """Find an optional speech module in src/ or beside server.py."""
    candidates = (
        HERE / "src" / f"{name}.py",
        HERE / f"{name}.py",
    )
    return next((path for path in candidates if path.is_file()), None)


def _voice_module(name):
    """Import ASR/TTS lazily so text chat starts without speech configured."""
    with _voice_lock:
        if name in _voice_modules:
            return _voice_modules[name]

        path = _voice_file(name)
        if path is None:
            raise HTTPException(
                503,
                f"{name}.py is missing; put it in src/ or beside server.py.",
            )

        try:
            spec = importlib.util.spec_from_file_location(
                f"_mfasha_{name}",
                path,
            )

            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {path.name}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        except Exception as exc:
            raise HTTPException(
                503,
                f"Could not load {name}.py: {type(exc).__name__}: {exc}",
            ) from exc

        _voice_modules[name] = module
        return module


def _warm_voice():
    """Load and warm up ASR and TTS in the background, so the first mic click is not slow.

    Set MFASHA_WARMUP=0 to turn this off. A failure here is only printed: text chat keeps working."""
    for name in ("asr", "tts"):
        try:
            module = _voice_module(name)
            t0 = time.time()
            module.load()
            module.warmup()
            print(f"[warmup] {name} ready in {time.time() - t0:.0f} s")
        except Exception as exc:
            detail = getattr(exc, "detail", exc)
            print(f"[warmup] {name} not ready: {type(exc).__name__}: {detail}")


def _voice_status(name):
    """Report speech module state without loading the large speech model."""
    if _voice_file(name) is None:
        return {"module_found": False, "loaded": False}

    try:
        module = _voice_module(name)
        return {"module_found": True, **module.status()}
    except HTTPException as exc:
        return {
            "module_found": True,
            "loaded": False,
            "error": exc.detail,
        }


# ------------------------------------------------------------------ request models
class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)


class SpeakIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)   # tts.py trims it to what is read aloud


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
        if os.getenv("MFASHA_WARMUP", "1") != "0":
            threading.Thread(target=_warm_voice, name="voice-warmup", daemon=True).start()
        yield

    app = FastAPI(
        title="Mfasha",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/")
    def index():
        if not INDEX_FILE.exists():
            raise HTTPException(
                500,
                "index.html not found. Put it in the static folder: "
                + str(STATIC_DIR),
            )

        return FileResponse(
            INDEX_FILE,
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/api/health")
    def health(request: Request):
        return {
            "ok": True,
            "chunks": len(request.app.state.bot.chunks),
            "voice": {
                "asr": _voice_status("asr"),
                "tts": _voice_status("tts"),
            },
        }

    @app.post("/api/ask")
    def ask(body: AskIn, request: Request):
        ip = request.client.host if request.client else "unknown"

        if too_many(ip):
            raise HTTPException(
                429,
                "Too many questions, please wait a moment.",
            )

        question = body.question.strip()
        if not question:
            raise HTTPException(400, "Empty question.")

        started = time.time()

        with _bot_lock:
            result = request.app.state.bot.ask(question)

        seconds = round(time.time() - started, 2)

        append_row(
            LOG_FILE,
            [
                "time",
                "question",
                "refused",
                "tier",
                "confidence",
                "passage_id",
                "seconds",
            ],
            [
                datetime.now().isoformat(timespec="seconds"),
                question,
                result["refused"],
                result["tier"],
                round(result["confidence"], 3),
                result["passage_id"],
                seconds,
            ],
        )

        return {
            "refused": result["refused"],
            "answer": result["answer"],
            "tier": result["tier"],
            "confidence": round(result["confidence"], 3),
            "passage_id": result["passage_id"],
            "alternatives": [
                alternative["text"]
                for alternative in result["alternatives"]
            ],
        }

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        """Accept raw audio bytes (WAV recommended; browser WebM needs ffmpeg)."""
        ip = request.client.host if request.client else "unknown"

        if too_many(ip):
            raise HTTPException(
                429,
                "Too many requests, please wait a moment.",
            )

        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > MAX_AUDIO_BYTES
        ):
            raise HTTPException(
                413,
                "Audio is too large; the limit is 20 MB.",
            )

        audio = bytearray()

        async for chunk in request.stream():
            if len(audio) + len(chunk) > MAX_AUDIO_BYTES:
                raise HTTPException(
                    413,
                    "Audio is too large; the limit is 20 MB.",
                )
            audio.extend(chunk)

        if not audio:
            raise HTTPException(400, "No audio was received.")

        try:
            text = await run_in_threadpool(
                _voice_module("asr").transcribe,
                bytes(audio),
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
            raise HTTPException(
                503,
                f"Speech synthesis failed: {type(exc).__name__}: {exc}",
            ) from exc

        if not result.get("wav"):
            notes = result.get("notes", [])
            raise HTTPException(
                422,
                "; ".join(notes or ["No speech was generated."]),
            )

        return Response(
            content=result["wav"],
            media_type="audio/wav",
            headers={
                "X-Audio-Sample-Rate": str(
                    result.get("sample_rate") or ""
                ),
                "X-Spoken-Seconds": str(
                    result.get("seconds") or 0
                ),
                "X-Cached": "1" if result.get("cached") else "0",
                "X-Notes": "; ".join(result.get("notes") or [])
                .encode("ascii", "ignore")
                .decode(),
            },
        )

    @app.post("/api/feedback")
    def feedback(body: VoteIn):
        append_row(
            FEEDBACK_FILE,
            ["time", "question", "passage_id", "vote"],
            [
                datetime.now().isoformat(timespec="seconds"),
                body.question,
                body.passage_id,
                body.vote,
            ],
        )
        return {"ok": True}

    if STATIC_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=STATIC_DIR),
            name="static",
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        default="0.0.0.0" if os.getenv("PORT") else "127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8000")),
    )

    args = parser.parse_args()

    print(
        "page  :",
        INDEX_FILE,
        "(found)" if INDEX_FILE.exists() else "(MISSING)",
    )
    print(
        f"open  : http://"
        f"{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:"
        f"{args.port}"
    )

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
    )