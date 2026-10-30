"""HTTP endpoints. Thin: each handler validates input, calls a service, and shapes the JSON."""
import json
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response

from .. import config
from ..audio import decode_audio
from ..pipeline import ANSWERED, EMPTY
from ..text_utils import tidy
from .messages import MSG
from .schemas import AskBody, FeedbackBody, SpeakBody
from .services import Services

TEMPLATES = Path(__file__).parent / "templates"


def visitor(request: Request) -> str:
    """Who is asking, for rate limiting. Behind a proxy the first forwarded address is the visitor."""
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def alternatives_for(hits, shown: str, count: int = 2, max_chars: int = 350):
    """Other close passages, shortened, skipping any that the shown answer already contains."""
    out = []
    for h in hits[1:1 + count]:
        text = tidy(h.text)
        if text and text not in shown:
            out.append(text[:max_chars] + ("…" if len(text) > max_chars else ""))
    return out


def build_router(sv: Services) -> APIRouter:
    router = APIRouter()
    landing_html = (TEMPLATES / "landing.html").read_text(encoding="utf-8")
    chat_html = (TEMPLATES / "chat.html").read_text(encoding="utf-8")

    # ------------------------------------------------------------------ pages
    @router.get("/")
    def home():
        return HTMLResponse(landing_html)

    @router.get("/chat")
    def chat():
        return HTMLResponse(chat_html)

    @router.get("/health")
    def health():
        return {"ready": sv.ready}

    # ------------------------------------------------------------------ api
    @router.post("/api/ask")
    def ask(body: AskBody, request: Request):
        if not sv.ask_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        question = (body.question or "").strip()
        if not question:
            raise HTTPException(400, MSG["empty"])
        if len(question) > config.MAX_QUESTION_CHARS:
            raise HTTPException(400, MSG["too_long"])
        try:
            t0 = time.time()
            res = sv.bot.ask(text=question)
            print(f"[timing] answer {time.time() - t0:.1f}s")
        except Exception as e:
            print("ask error:", e)
            raise HTTPException(500, MSG["error"])
        if res.status == EMPTY:
            raise HTTPException(400, MSG["empty"])
        if res.status != ANSWERED:                  # referred: the collection has no good answer for this question
            sv.voice.prefetch(res.answer)
            return {"answer": res.answer, "refused": True, "passage_id": None}

        shown = tidy(res.answer)
        sv.voice.prefetch(shown)                    # the voice is made while the farmer reads
        return {"answer": shown, "refused": False, "tier": sv.confidence.for_hits(res.hits),
                "alternatives": alternatives_for(res.hits, shown), "passage_id": res.hits[0].pid}

    @router.post("/api/transcribe")
    async def transcribe(request: Request):
        if not sv.audio_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        data = await request.body()
        if not data:
            raise HTTPException(400, MSG["no_audio"])
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, MSG["big_audio"])

        def work():
            audio = decode_audio(data)
            t0 = time.time()
            with sv.asr_lock:
                text = sv.bot.transcriber.transcribe(audio)
            print(f"[timing] transcribe {time.time() - t0:.1f}s ({len(audio) / config.ASR_SR:.1f}s of audio)")
            return text

        try:
            text = await run_in_threadpool(work)
        except Exception as e:
            print("transcribe error:", e)
            raise HTTPException(400, MSG["bad_audio"])
        return {"text": text}

    @router.post("/api/speak")
    def speak(body: SpeakBody, request: Request):
        if not sv.speak_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        if not sv.voice.has_speech(body.text):
            raise HTTPException(400, MSG["no_text"])
        result = sv.voice.get(body.text)
        if result is None:
            raise HTTPException(500, MSG["error"])
        data, note = result
        return Response(content=data, media_type="audio/wav", headers={"X-Notes": note} if note else {})

    @router.post("/api/feedback")
    def feedback(body: FeedbackBody):
        try:
            sv.feedback_file.parent.mkdir(exist_ok=True)
            with open(sv.feedback_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "question": body.question[:500],
                                    "passage_id": body.passage_id, "vote": body.vote}, ensure_ascii=False) + "\n")
        except Exception as e:
            print("feedback error:", e)
            raise HTTPException(500, MSG["error"])
        return {"ok": True}

    return router
