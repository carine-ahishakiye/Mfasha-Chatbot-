
import hashlib
import io
import json
import os
import threading
import time
from collections import OrderedDict, defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from scipy.io import wavfile

from mfasha import config
from mfasha.llm import NO_ANSWER
from mfasha.text_utils import split_sentences, tidy

ROOT = Path(__file__).resolve().parent
FEEDBACK_FILE = ROOT / "results" / "feedback.jsonl"

# settings 
MAX_QUESTION_CHARS = 500
MAX_SPOKEN_CHARS = 350            # longer answers are read only in part, to keep the wait short
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# confidence badge: PROVISIONAL cutoffs on the gap between best and second-best passage score.
# scripts/evaluate_answers.py can show accuracy per gap bucket so you can calibrate them
TIER_MIN_SCORE = float(os.getenv("TIER_MIN_SCORE", "0.60"))
TIER_HIGH_MARGIN = float(os.getenv("TIER_HIGH_MARGIN", "0.04"))
TIER_MEDIUM_MARGIN = float(os.getenv("TIER_MEDIUM_MARGIN", "0.015"))

# messages the page shows to the farmer
MSG = {
    "error": "Mbabarira, habaye ikibazo. Ongera ugerageze nyuma y'akanya gato.",
    "empty": "Andika ikibazo cyawe.",
    "too_long": "Ikibazo kirenze inyuguti 500. Gabanya inyandiko.",
    "busy": "Ibibazo ni byinshi cyane. Tegereza akanya, ongera ugerageze.",
    "no_audio": "Nta majwi yoherejwe. Ongera ugerageze.",
    "bad_audio": "Ntabwo amajwi yumvikanye. Ongera ugerageze.",
    "big_audio": "Amajwi ni manini cyane. Vuga igihe gito.",
    "no_text": "Nta nyandiko yo gusoma.",
}


def confidence_tier(hits) -> str:
    top = hits[0].score
    margin = top - hits[1].score if len(hits) > 1 else top
    if top < TIER_MIN_SCORE:
        return "low"
    if margin >= TIER_HIGH_MARGIN:
        return "high"
    if margin >= TIER_MEDIUM_MARGIN:
        return "medium"
    return "low"


def decode_audio(data: bytes, sr: int = config.ASR_SR) -> np.ndarray:
    """What the browser records (webm/ogg/mp4/wav) -> 16 kHz mono float32."""
    try:
        import av
    except ImportError:
        import soundfile as sf                           # without PyAV only plain WAV can be read
        y, file_sr = sf.read(io.BytesIO(data), dtype="float32")
        if y.ndim > 1:
            y = y.mean(axis=1)
        if file_sr != sr:
            from math import gcd
            from scipy.signal import resample_poly
            g = gcd(int(file_sr), sr)
            y = resample_poly(y, sr // g, int(file_sr) // g).astype(np.float32)
        return y
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


def wav_bytes(wav: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(wav, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    wavfile.write(buf, sr, pcm)
    return buf.getvalue()


class AskBody(BaseModel):
    question: str = ""


class SpeakBody(BaseModel):
    text: str = ""


class FeedbackBody(BaseModel):
    question: str = ""
    passage_id: Optional[str] = None
    vote: Literal["helpful", "not_helpful"]


class RateLimiter:
    """Per-visitor limit, so a public link cannot burn through your Groq quota."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self.seen = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            q = self.seen[key]
            while q and q[0] < now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def visitor(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def create_app(bot=None, speaker=None) -> FastAPI:
    holder = {"bot": bot, "speaker": speaker}
    asr_lock, tts_lock = threading.Lock(), threading.Lock()      # one job per speech model at a time
    cache_lock = threading.Lock()
    ask_limit, audio_limit, speak_limit = RateLimiter(20), RateLimiter(8), RateLimiter(40)
    voice_cache: "OrderedDict[str, tuple]" = OrderedDict()
    inflight = {}                                  # voice jobs running right now, so none is made twice

    def spoken_part(text):
        text = tidy(text or "")[:5000]
        spoken, truncated = "", False
        for sentence in split_sentences(text) or ([text] if text else []):
            if spoken and len(spoken) + len(sentence) > MAX_SPOKEN_CHARS:
                truncated = True
                break
            spoken = (spoken + " " + sentence).strip()
        return spoken, truncated

    def get_voice(text):
        """(wav bytes, note) from the cache, or made now. Returns None if it failed."""
        spoken, truncated = spoken_part(text)
        if not spoken:
            return None
        key = hashlib.sha1(spoken.encode()).hexdigest()
        with cache_lock:
            if key in voice_cache:
                return voice_cache[key]
            done = inflight.get(key)
            mine = done is None
            if mine:
                done = inflight[key] = threading.Event()
        if not mine:                               # someone is already making it: wait for that
            done.wait(180)
            with cache_lock:
                return voice_cache.get(key)
        try:
            t0 = time.time()
            with tts_lock:
                wav, _ = holder["speaker"].speak(spoken)
            result = (wav_bytes(wav, holder["speaker"].sr), "first part only" if truncated else "")
            with cache_lock:
                voice_cache[key] = result
                while len(voice_cache) > 32:
                    voice_cache.popitem(last=False)
            print(f"[timing] voice {time.time() - t0:.1f}s")
            return result
        except Exception as e:
            print("speak error:", e)
            return None
        finally:
            with cache_lock:
                inflight.pop(key, None)
            done.set()

    def prefetch_voice(text):
        threading.Thread(target=get_voice, args=(text,), daemon=True).start()

    @asynccontextmanager
    async def lifespan(_app):
        if holder["bot"] is None:
            print("loading models, this takes a few minutes the first time ...")
            from mfasha.pipeline import Mfasha
            holder["bot"] = Mfasha.load()
        if holder["speaker"] is None:
            from mfasha.tts import Speaker
            holder["speaker"] = Speaker()
        try:                                       # first calls are slow, so do one of each now
            t0 = time.time()
            holder["speaker"].speak("Muraho.")
            asr = getattr(holder["bot"], "transcriber", None)
            if asr:
                asr.transcribe(np.zeros(config.ASR_SR, dtype=np.float32))
            print(f"warm-up done in {time.time() - t0:.0f}s")
        except Exception as e:
            print("warm-up skipped:", e)
        print("ready")
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    def home():
        return HTMLResponse(LANDING)

    @app.get("/chat")
    def chat():
        return HTMLResponse(PAGE)

    @app.get("/static/config.js")
    def page_config():             # the page asks for this file. Empty = use this server for everything
        js = 'window.MFASHA_ASR_URL="";window.MFASHA_TTS_URL="";'
        return Response(js, media_type="text/javascript")

    @app.get("/health")
    def health():
        return {"ready": holder["bot"] is not None and holder["speaker"] is not None}

    @app.post("/api/ask")
    def ask(body: AskBody, request: Request):
        if not ask_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        question = (body.question or "").strip()
        if not question:
            raise HTTPException(400, MSG["empty"])
        if len(question) > MAX_QUESTION_CHARS:
            raise HTTPException(400, MSG["too_long"])
        try:
            res = holder["bot"].ask(text=question)
        except Exception as e:
            print("ask error:", e)
            raise HTTPException(500, MSG["error"])
        if res.status == "empty":
            raise HTTPException(400, MSG["empty"])
        if res.status == "llm_error":
            raise HTTPException(503, MSG["error"])
        if res.status == "refused":
            prefetch_voice(res.answer)
            return {"answer": res.answer, "refused": True, "passage_id": None}

        top = res.hits[0]
        tier = "low" if res.guarded else confidence_tier(res.hits)       # a guarded answer is never "high"
        shown = tidy(res.answer)
        alternatives = []
        for h in res.hits[1:3]:
            text = tidy(h.text)
            if text and text not in shown:
                alternatives.append(text[:350] + ("…" if len(text) > 350 else ""))
        prefetch_voice(shown)                       # the voice is made while the farmer reads
        return {"answer": shown, "refused": False, "tier": tier,
                "alternatives": alternatives, "passage_id": top.pid}

    @app.post("/api/transcribe")
    async def transcribe(request: Request):
        if not audio_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        data = await request.body()
        if not data:
            raise HTTPException(400, MSG["no_audio"])
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, MSG["big_audio"])

        def work():
            audio = decode_audio(data)
            with asr_lock:
                return holder["bot"].transcriber.transcribe(audio)

        try:
            text = await run_in_threadpool(work)
        except Exception as e:
            print("transcribe error:", e)
            raise HTTPException(400, MSG["bad_audio"])
        return {"text": text}

    @app.post("/api/speak")
    def speak(body: SpeakBody, request: Request):
        if not speak_limit.allow(visitor(request)):
            raise HTTPException(429, MSG["busy"])
        if not spoken_part(body.text)[0]:
            raise HTTPException(400, MSG["no_text"])
        result = get_voice(body.text)
        if result is None:
            raise HTTPException(500, MSG["error"])
        data, note = result
        return Response(content=data, media_type="audio/wav", headers={"X-Notes": note} if note else {})

    @app.post("/api/feedback")
    def feedback(body: FeedbackBody):
        try:
            FEEDBACK_FILE.parent.mkdir(exist_ok=True)
            with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"t": int(time.time()), "question": body.question[:500],
                                    "passage_id": body.passage_id, "vote": body.vote}, ensure_ascii=False) + "\n")
        except Exception as e:
            print("feedback error:", e)
            raise HTTPException(500, MSG["error"])
        return {"ok": True}

    return app


app = create_app()

#  THE UI PAGE

PAGE = r"""
<!doctype html>
<html lang="rw">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="Mfasha igufasha gushaka amakuru ku buhinzi n’ubworozi mu Kinyarwanda.">
<meta name="theme-color" content="#F5F6F3">
<title>Mfasha – Umufasha wawe mu buhinzi n’ubworozi</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#F5F6F3;--side:#EEF0EB;--surface:#FFFFFF;--primary:#2E7D32;--primary-hover:#276B2B;--primary-light:#E8F5E9;
  --text:#111827;--muted:#5F6672;--faint:#7A818C;--border:#E2E5DF;--hover:#E6E9E3;
  --amber:#92400E;--amber-tint:#FEF3C7;--red:#B91C1C;--red-tint:#FEE2E2;
  --shadow-sm:0 1px 2px rgba(17,24,39,.04);
  --shadow-md:0 4px 14px rgba(17,24,39,.06);
  --shadow-lg:0 8px 30px rgba(17,24,39,.08);
  --ease:cubic-bezier(.2,.7,.2,1);
  font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--text);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
::selection{background:var(--primary-light)}
button,textarea{font:inherit;color:inherit}
button{cursor:pointer;transition:background-color .18s var(--ease),border-color .18s var(--ease),color .18s var(--ease),box-shadow .2s var(--ease),transform .2s var(--ease),opacity .18s}
button:active:not(:disabled){transform:scale(.97)}
:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
[hidden]{display:none!important}
.sr-only{position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
*{scrollbar-width:thin;scrollbar-color:#D1D5DB transparent}

@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes fade{from{opacity:0}}
@keyframes ring{0%{box-shadow:0 0 0 0 rgba(185,28,28,.35)}100%{box-shadow:0 0 0 12px rgba(185,28,28,0)}}
@keyframes pulse{0%,100%{opacity:.45}50%{opacity:1}}

.app{display:flex;height:100vh;height:100dvh;background:var(--bg)}

/* Sidebar */
.sidebar{width:260px;flex:none;display:flex;flex-direction:column;padding:16px 12px 12px;background:var(--side);border-right:1px solid var(--border);overflow:hidden;white-space:nowrap;transition:width .28s var(--ease),padding .28s var(--ease)}
.side-top{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-bottom:16px}
.side-toggle{display:inline-flex;align-items:center;justify-content:center;flex:none;width:36px;height:36px;border:0;border-radius:8px;background:none;color:var(--muted)}
.side-toggle:hover{background:var(--hover);color:var(--text)}
.side-toggle svg{width:20px;height:20px}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px;font-size:1.0625rem;font-weight:700;letter-spacing:-.02em}
.brand svg{width:30px;height:30px;flex:none}
.btn-new{display:flex;align-items:center;justify-content:center;gap:8px;width:100%;height:42px;border:0;border-radius:10px;background:var(--primary);color:#fff;font-size:.9rem;font-weight:600}
.btn-new svg{width:16px;height:16px}
.btn-new:hover{background:var(--primary-hover);box-shadow:0 4px 12px rgba(46,125,50,.25)}
.sidebar h2{margin:22px 10px 8px;font-size:.75rem;font-weight:600;color:var(--faint);letter-spacing:.01em}
.history{flex:1;min-height:0;overflow-y:auto;padding-bottom:8px}
.history-item{display:block;width:100%;min-height:38px;padding:8px 10px;margin-bottom:2px;border:0;border-radius:8px;background:none;text-align:left;font-size:.875rem;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.history-item:hover{background:var(--hover)}
.history-item.active{background:#DDEBDE;font-weight:500}
.no-history{margin:0;padding:8px 10px;color:var(--muted);font-size:.875rem}
.sidebar-foot{padding-top:10px;border-top:1px solid var(--border)}
.link-btn{display:flex;align-items:center;gap:8px;width:100%;min-height:38px;padding:0 10px;border:0;border-radius:8px;background:none;color:var(--muted);font-size:.85rem;text-align:left}
.link-btn svg{width:16px;height:16px;flex:none}
.link-btn:hover{background:var(--hover);color:var(--red)}

/* Main */
.main{position:relative;flex:1;min-width:0;display:flex;flex-direction:column;background:var(--bg)}
.btn-menu{position:absolute;z-index:6;top:14px;left:14px;display:none;align-items:center;justify-content:center;width:40px;height:40px;border:1px solid var(--border);border-radius:10px;background:var(--surface);color:var(--text);box-shadow:var(--shadow-sm)}
.btn-menu:hover{background:var(--hover);box-shadow:var(--shadow-md)}
.btn-menu svg{width:20px;height:20px}
.scroll{flex:1;min-height:0;overflow-y:auto;scroll-behavior:smooth}
.column{width:min(100%,780px);min-height:100%;margin:0 auto;padding:64px 24px 32px;display:flex;flex-direction:column}

/* Landing */
.welcome{margin:auto 0;padding:24px 0;text-align:center}
.welcome>:not(.cards){animation:rise .6s var(--ease) backwards}
.welcome>:nth-child(2){animation-delay:.08s}
.welcome>:nth-child(3){animation-delay:.14s}
.welcome>:nth-child(5){animation-delay:.5s}
.logo{display:block;width:120px;height:120px;margin:0 auto 20px;transition:transform .5s var(--ease)}
.logo:hover{transform:rotate(-5deg) scale(1.04)}
.welcome h1{margin:0;font-size:clamp(2.5rem,7vw,3.5rem);font-weight:700;line-height:1.05;letter-spacing:-.04em}
.welcome .lead{margin:14px auto 0;max-width:420px;color:var(--muted);font-size:1.125rem}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin:40px auto 0;max-width:720px;text-align:left}
.card{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--border);border-radius:12px;background:var(--surface);box-shadow:var(--shadow-sm);text-align:left;animation:rise .5s var(--ease) backwards;animation-delay:calc(.22s + var(--i)*.05s)}
.card:hover{transform:translateY(-2px);border-color:#CFE3D0;box-shadow:var(--shadow-md)}
.card:active:not(:disabled){transform:translateY(0) scale(.99)}
.card-icon{display:inline-flex;align-items:center;justify-content:center;flex:none;width:34px;height:34px;border-radius:9px;background:var(--primary-light);color:#4B8B4F;transition:background-color .2s var(--ease),color .2s var(--ease)}
.card:hover .card-icon{background:var(--primary);color:#fff}
.card-icon svg{width:17px;height:17px}
.card-text{display:flex;flex-direction:column;min-width:0}
.card-title{font-size:.875rem;font-weight:600;line-height:1.35;color:var(--text)}
.card-sub{font-size:.78rem;line-height:1.4;color:var(--muted)}
.howto{margin:28px auto 0;max-width:520px;color:var(--faint);font-size:.8rem}
.howto strong{color:var(--muted);font-weight:600}

/* Conversation */
.turn{padding:14px 0;animation:rise .4s var(--ease) backwards}
.question{display:flex;justify-content:flex-end}
.question div{max-width:82%;padding:11px 16px;border-radius:18px 18px 4px 18px;background:#E0EDE1;white-space:pre-wrap;overflow-wrap:anywhere}
.answer{margin-top:14px;padding:16px 20px;border:1px solid var(--border);border-radius:18px 18px 18px 4px;background:var(--surface);box-shadow:var(--shadow-md)}
.answer.refused{background:var(--bg);box-shadow:none}
.badge{display:inline-block;margin-bottom:8px;padding:2px 10px;border-radius:999px;font-size:.78rem;font-weight:600}
.badge.high{background:var(--primary-light);color:var(--primary)}
.badge.medium{background:var(--amber-tint);color:var(--amber)}
.badge.low{background:var(--red-tint);color:var(--red)}
.note{margin:0 0 10px;font-size:.875rem;color:var(--muted)}
.answer-text{margin:0;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere;animation:rise .45s var(--ease) backwards}
.alternatives{margin-top:14px;font-size:.93rem}
.alternatives summary{cursor:pointer;color:var(--primary);font-weight:600}
.alternatives summary:hover{color:var(--primary-hover)}
.alternative{margin:8px 0 0;padding:10px 14px;background:var(--bg);border-radius:10px;white-space:pre-wrap}
.tools{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--border)}
.tool{min-height:34px;padding:0 12px;border:1px solid var(--border);border-radius:8px;background:var(--surface);font-size:.84rem;color:var(--muted)}
.tool:hover:not(:disabled){background:var(--hover);color:var(--text)}
.tool.selected{border-color:var(--primary);background:var(--primary-light);color:var(--primary)}
.tool:disabled{opacity:.7;cursor:default}
.thinking{margin:0;color:var(--muted);animation:pulse 1.3s ease-in-out infinite}
.error{margin:0;color:var(--red)}

/* Input */
.composer-area{flex:none;padding:8px 24px max(16px,env(safe-area-inset-bottom));background:var(--bg)}
.composer-wrap{width:min(100%,780px);margin:0 auto}
.composer{display:flex;align-items:flex-end;gap:6px;padding:8px 8px 8px 20px;border:1px solid var(--border);border-radius:28px;background:var(--surface);box-shadow:var(--shadow-lg);transition:border-color .2s var(--ease),box-shadow .2s var(--ease)}
.composer:focus-within{border-color:#A5D6A7;box-shadow:0 0 0 4px rgba(46,125,50,.10),var(--shadow-lg)}
.composer textarea{flex:1;min-width:0;min-height:44px;max-height:160px;resize:none;padding:11px 0;border:0;background:transparent;font-size:1rem;line-height:1.45}
.composer textarea::placeholder{color:var(--faint)}
.composer textarea:focus{outline:none}
.icon-btn{display:inline-flex;align-items:center;justify-content:center;flex:none;width:44px;height:44px;border:0;border-radius:50%}
.icon-btn svg{width:20px;height:20px}
.mic{background:transparent;color:var(--muted)}
.mic:hover:not(:disabled){background:var(--primary-light);color:var(--primary)}
.mic.recording{background:var(--red);color:#fff;animation:ring 1.4s ease-out infinite}
.send{background:var(--primary);color:#fff}
.send:hover:not(:disabled){background:var(--primary-hover);box-shadow:0 4px 12px rgba(46,125,50,.28)}
.mic:disabled,.send:disabled{opacity:.4;cursor:default}
.status{min-height:22px;margin:8px 12px 0;font-size:.84rem;color:var(--muted)}
.disclaimer{margin:0 12px;font-size:.75rem;color:var(--faint);text-align:center}
.scrim{display:none}

@media(min-width:821px){
  .app.collapsed .sidebar{width:0;padding-left:0;padding-right:0;border-right-width:0;visibility:hidden;transition:width .28s var(--ease),padding .28s var(--ease),visibility 0s linear .28s}
  .app.collapsed .btn-menu{display:inline-flex}
}
@media(max-width:820px){
  .sidebar{position:fixed;z-index:20;top:0;bottom:0;left:0;width:min(86vw,300px);transform:translateX(-102%);visibility:hidden;box-shadow:var(--shadow-lg);transition:transform .25s var(--ease),visibility 0s linear .25s}
  .app.open .sidebar{transform:none;visibility:visible;transition:transform .25s var(--ease)}
  .app.open .scrim{display:block;position:fixed;z-index:19;inset:0;border:0;background:rgba(17,24,39,.35);animation:fade .2s ease backwards}
  .btn-menu{display:inline-flex}
  .column{padding:64px 16px 24px}
  .composer-area{padding-left:12px;padding-right:12px}
  .logo{width:96px;height:96px;margin-bottom:16px}
  .cards{margin-top:28px}
}
@media(max-width:480px){
  .composer{padding-left:16px}
  .answer{padding:14px 16px}
  .cards{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
body{background:#F6F4EC}:root{--bg:#F6F4EC;--side:#EFEBDD;--border:#E3DFD0;--hover:#E8E4D3}
.welcome h1,.brand,.answer-text{font-family:Fraunces,Georgia,serif}.welcome h1{letter-spacing:-.03em}
.answer-text{font-size:1.06rem;line-height:1.75}.answer{border-left:4px solid var(--primary);box-shadow:0 2px 10px rgba(20,32,26,.05)}
.history-row{display:flex;align-items:center;gap:2px;margin-bottom:2px;border-radius:8px}.history-row:hover{background:var(--hover)}.history-row .history-item{flex:1;min-width:0;margin:0}
.history-row .history-item:hover{background:none}.history-del{flex:none;width:30px;height:30px;margin-right:4px;border:0;border-radius:7px;background:none;color:var(--faint);opacity:0;display:grid;place-items:center}
.history-del svg{width:16px;height:16px}.history-row:hover .history-del,.history-del:focus-visible{opacity:1}.history-del:hover{background:var(--red-tint);color:var(--red)}
@media(hover:none){.history-del{opacity:.7}}
.alternatives summary{padding:8px 0}.alternative{border-left:3px solid #BFD7B3;border-radius:4px 10px 10px 4px;background:#F6F4EC;line-height:1.65}
</style>
</head>
<body>
<div class="app" id="app">
  <aside class="sidebar" id="sidebar" aria-label="Ibiganiro">
    <div class="side-top"><div class="brand"><svg viewBox="0 0 120 120" aria-hidden="true"><use href="#logo-mark"/></svg><span class="brand-name">Mfasha</span></div><button class="side-toggle" id="collapse-sidebar" type="button" aria-controls="sidebar" aria-expanded="true" aria-label="Funga ibiganiro byashize" title="Funga ibiganiro byashize"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg></button></div>
    <button class="btn-new" id="new-chat" type="button" aria-label="Ikiganiro gishya" title="Ikiganiro gishya"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg><span class="btn-new-label">Ikiganiro gishya</span></button>
    <h2 id="history-title">Ibiganiro byashize</h2>
    <nav class="history" id="history-list" aria-labelledby="history-title"></nav>
    <div class="sidebar-foot"><button class="link-btn" id="clear-history" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v5M14 11v5"/></svg>Siba ibiganiro byose</button></div>
  </aside>
  <button class="scrim" id="scrim" type="button" aria-label="Funga" tabindex="-1"></button>

  <main class="main">
    <button class="btn-menu" id="toggle-history" type="button" aria-label="Funga ibiganiro byashize" aria-controls="sidebar" aria-expanded="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/></svg></button>

    <div class="scroll" id="chat-scroll">
      <div class="column">
        <section class="welcome" id="empty-state" aria-labelledby="welcome-title">
          <svg class="logo" viewBox="0 0 120 120" role="img" aria-label="Mfasha"><use href="#logo-mark"/></svg>
          <h1 id="welcome-title">Mfasha</h1>
          <p class="lead">Umufasha wawe mu buhinzi n’ubworozi</p>
          <div class="cards" role="group" aria-label="Ibibazo bisanzwe">
              <button class="card" type="button" style="--i:0" data-question="Ni gute nakongera umusaruro w'ibigori?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10Z"/><path d="M2 21c0-3 1.9-5.4 5.1-6C9.5 14.5 12 13 13 12"/></svg></span><span class="card-text"><span class="card-title">Ibigori</span><span class="card-sub">Kongera umusaruro</span></span></button>
              <button class="card" type="button" style="--i:1" data-question="Nakumira nte indwara mu bihingwa?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></span><span class="card-text"><span class="card-title">Indwara z’ibihingwa</span><span class="card-sub">Uko wazikumira</span></span></button>
              <button class="card" type="button" style="--i:2" data-question="Nakora iki ngo inka yongere kurya neza?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/></svg></span><span class="card-text"><span class="card-title">Inka</span><span class="card-sub">Kurya neza</span></span></button>
              <button class="card" type="button" style="--i:3" data-question="Ni ifumbire iki nakoresha ku bihingwa byanjye?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 22a7 7 0 0 0 7-7c0-2-1-3.9-3-5.5s-3.5-4-4-6.5c-.5 2.5-2 4.9-4 6.5C6 11.1 5 13 5 15a7 7 0 0 0 7 7z"/></svg></span><span class="card-text"><span class="card-title">Ifumbire</span><span class="card-sub">Ikwiye ibihingwa byawe</span></span></button>
              <button class="card" type="button" style="--i:4" data-question="Nabungabunga nte ubutaka bwanjye?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 2 10 5-10 5L2 7z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/></svg></span><span class="card-text"><span class="card-title">Ubutaka</span><span class="card-sub">Kububungabunga</span></span></button>
              <button class="card" type="button" style="--i:5" data-question="Ni ryari ngomba gutera imbuto?"><span class="card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></span><span class="card-text"><span class="card-title">Igihe cyo gutera</span><span class="card-sub">Igihe gikwiye</span></span></button>
          </div>
          <p class="howto"><strong>Uko wabikoresha:</strong> andika ikibazo hasi, cyangwa ukande mikoro maze ubaze mu ijwi. Ushobora no gukanda “Soma igisubizo” ukumva igisubizo gisomwa.</p>
        </section>
        <div id="thread" role="log" aria-live="polite" aria-label="Ikiganiro"></div>
      </div>
    </div>

    <footer class="composer-area">
      <div class="composer-wrap">
        <form class="composer" id="chat-form">
          <label for="question" class="sr-only">Ikibazo cyawe</label>
          <textarea id="question" rows="1" maxlength="500" placeholder="Andika ikibazo cyawe hano" autocomplete="off"></textarea>
          <button class="icon-btn mic" id="microphone" type="button" aria-label="Tangira gufata amajwi"><svg id="mic-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/></svg><span class="sr-only" id="mic-label">Vuga</span></button>
          <button class="icon-btn send" id="send-button" type="submit" aria-label="Ohereza"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7"/></svg></button>
        </form>
        <p class="status" id="status-line" role="status" aria-live="polite"></p>
        <p class="disclaimer">Ibisubizo bishingiye ku nyandiko ziri muri Mfasha. Ikibazo cyihutirwa, baza umukozi w’ubuhinzi cyangwa veterineri.</p>
      </div>
    </footer>
  </main>
</div>

<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
  <defs>
    <symbol id="logo-mark" viewBox="0 0 120 120">
      <clipPath id="lg-clip"><circle cx="58" cy="72" r="34"/></clipPath>
      <path d="M31 56a34 34 0 1 0 54 -10" fill="none" stroke="#1F6B35" stroke-width="7" stroke-linecap="round"/>
      <g clip-path="url(#lg-clip)">
        <path d="M24 70q22-14 70-8v10q-40-6-70 8z" fill="#A4C42B"/>
        <path d="M24 82q26-14 70-6v10q-42-8-70 8z" fill="#A4C42B"/>
        <path d="M30 98q24-22 64-14v26H30z" fill="#7FA51F"/>
      </g>
      <path d="M52 62C44 56 44 42 54 32c9 9 8 24-2 30z" fill="#1F6B35"/>
      <path d="M62 60C58 44 68 26 88 18c4 22-8 38-26 42z" fill="#1F6B35"/>
    </symbol>
  </defs>
</svg>

<script src="/static/config.js"></script><script>(function(){
  'use strict';
  var STORAGE_KEY='mfasha-conversations-v1';var ASR_URL=window.MFASHA_ASR_URL||'';var TTS_URL=window.MFASHA_TTS_URL||'';async function fetchWithFallback(remote,local,opts){if(remote){try{var c=new AbortController();var t=setTimeout(function(){c.abort();},8000);var r=await fetch(remote,Object.assign({signal:c.signal},opts));clearTimeout(t);if(r.ok)return r;}catch(e){}}return fetch(local,opts);}
  var $=function(id){return document.getElementById(id);};
  var app=$('app'),chatForm=$('chat-form'),questionBox=$('question'),sendButton=$('send-button'),microphoneButton=$('microphone'),micIcon=$('mic-icon'),micLabel=$('mic-label'),statusLine=$('status-line'),thread=$('thread'),emptyState=$('empty-state'),historyList=$('history-list'),chatScroll=$('chat-scroll');
  var conversations=[],activeConversationId=null,isBusy=false,recorder=null,micStream=null,recordTimer=null,audioPlayer=null,audioUrl=null,activeSpeakButton=null,speechRequestId=0;

  function setStatus(text){statusLine.textContent=text||'';}
  function saveConversations(){try{localStorage.setItem(STORAGE_KEY,JSON.stringify(conversations));}catch(e){setStatus('Ntabwo amateka yabitswe kuri iki gikoresho.');}}
  function loadConversations(){try{var saved=JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]');if(Array.isArray(saved))conversations=saved;}catch(e){conversations=[];}conversations=conversations.filter(function(c){return c&&c.id&&Array.isArray(c.items);});renderHistory();}
  function getActiveConversation(){return conversations.find(function(c){return c.id===activeConversationId;})||null;}

  function renderHistory(){
    historyList.replaceChildren();
    if(!conversations.length){var empty=document.createElement('p');empty.className='no-history';empty.textContent='Nta kiganiro kiraboneka.';historyList.appendChild(empty);return;}
    conversations.slice().sort(function(a,b){return(b.updated||b.created||0)-(a.updated||a.created||0);}).forEach(function(c){
      var row=document.createElement('div');row.className='history-row';var button=document.createElement('button');button.type='button';button.className='history-item'+(c.id===activeConversationId?' active':'');button.textContent=c.title||'Ikiganiro gishya';button.title=button.textContent;button.addEventListener('click',function(){openConversation(c.id);});var del=document.createElement('button');del.type='button';del.className='history-del';del.setAttribute('aria-label','Siba iki kiganiro');del.title='Siba iki kiganiro';del.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>';del.addEventListener('click',function(ev){ev.stopPropagation();deleteConversation(c.id);});row.appendChild(button);row.appendChild(del);historyList.appendChild(row);
    });
  }

  function deleteConversation(id){if(!window.confirm('Urashaka gusiba iki kiganiro?'))return;conversations=conversations.filter(function(c){return c.id!==id;});saveConversations();if(id===activeConversationId)beginNewChat();else renderHistory();}
  function showEmpty(show){emptyState.hidden=!show;}
  function beginNewChat(){stopSpeech();activeConversationId=null;thread.replaceChildren();showEmpty(true);renderHistory();chatScroll.scrollTop=0;app.classList.remove('open');questionBox.focus();}
  function openConversation(id){
    var c=conversations.find(function(item){return item.id===id;});if(!c)return;stopSpeech();activeConversationId=id;thread.replaceChildren();showEmpty(false);
    c.items.forEach(function(item){var turn=createTurn(item.question);if(item.answer)renderAnswer(turn,item.answer,item,true);else showAnswerError(turn,'Iki gisubizo nticyabitswe.');});
    renderHistory();chatScroll.scrollTop=chatScroll.scrollHeight;app.classList.remove('open');
  }

  function createTurn(question){
    var article=document.createElement('article');article.className='turn';var row=document.createElement('div');row.className='question';var bubble=document.createElement('div');bubble.textContent=question;row.appendChild(bubble);article.appendChild(row);
    var card=document.createElement('section');card.className='answer';var body=document.createElement('div');card.appendChild(body);article.appendChild(card);thread.appendChild(article);return{article:article,card:card,body:body};
  }
  function showThinking(turn){var p=document.createElement('p');p.className='thinking';p.textContent='Ndimo gushaka igisubizo…';turn.body.appendChild(p);chatScroll.scrollTop=chatScroll.scrollHeight;}
  function makeButton(text){var b=document.createElement('button');b.type='button';b.className='tool';b.textContent=text;return b;}
  async function feedback(item,passageId,vote,button){if(item.vote||item.feedbackPending)return;item.feedbackPending=true;button.disabled=true;try{var response=await fetch('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:item.question,passage_id:passageId||null,vote:vote})});if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');}item.vote=vote;button.classList.add('selected');saveConversations();}catch(error){setStatus(error.message||'Ntabwo igitekerezo cyawe cyabitswe. Ongera ugerageze.');}finally{item.feedbackPending=false;button.disabled=!!item.vote;}}

  function renderAnswer(turn,answer,item,quiet){
    turn.body.replaceChildren();turn.card.classList.toggle('refused',!!answer.refused);
    if(!answer.refused&&answer.tier){
      var badge=document.createElement('span');badge.className='badge '+answer.tier;badge.textContent='Icyizere: '+({high:'kinshi',medium:'giciriritse',low:'gike'}[answer.tier]||'ntikizwi');turn.body.appendChild(badge);
      if(answer.tier==='medium'||answer.tier==='low'){var note=document.createElement('p');note.className='note';note.textContent=answer.tier==='low'?'Iki gisubizo nticyizewe bihagije. Genzura n’andi makuru.':'Genzura n’andi makuru kugira ngo wemeze iki gisubizo.';turn.body.appendChild(note);}}
    var text=document.createElement('p');text.className='answer-text';text.textContent=answer.answer||'Nta gisubizo cyagarutse.';turn.body.appendChild(text);
    if(!answer.refused&&answer.alternatives&&answer.alternatives.length){var details=document.createElement('details');details.className='alternatives';var summary=document.createElement('summary');summary.textContent='Ibindi bisubizo bishoboka ('+answer.alternatives.length+')';details.appendChild(summary);answer.alternatives.forEach(function(value){var p=document.createElement('p');p.className='alternative';p.textContent=value;details.appendChild(p);});turn.body.appendChild(details);}
    var tools=document.createElement('div');tools.className='tools';var speaker=makeButton('Soma igisubizo');speaker.addEventListener('click',function(){speakAnswer(answer.answer||'',speaker);});tools.appendChild(speaker);
    if(!answer.refused){
      var yes=makeButton(item.vote==='helpful'?'Byamfashije ✓':'Byamfashije');yes.disabled=!!item.vote;yes.addEventListener('click',function(){feedback(item,answer.passage_id,'helpful',yes);});
      var no=makeButton(item.vote==='not_helpful'?'Ntibyamfashije ✓':'Ntibyamfashije');no.disabled=!!item.vote;no.addEventListener('click',function(){feedback(item,answer.passage_id,'not_helpful',no);});
      var copy=makeButton('Koporora');copy.addEventListener('click',function(){if(!navigator.clipboard){setStatus('Iyi mushakisha ntishobora gukoporora.');return;}navigator.clipboard.writeText(answer.answer||'').then(function(){setStatus('Igisubizo cyakoporowe.');setTimeout(function(){setStatus('');},1600);}).catch(function(){setStatus('Ntabwo igisubizo cyakoporowe.');});});
      tools.appendChild(yes);tools.appendChild(no);tools.appendChild(copy);}
    turn.body.appendChild(tools);if(!quiet)turn.article.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function showAnswerError(turn,message){turn.body.replaceChildren();var p=document.createElement('p');p.className='error';p.textContent=message;turn.body.appendChild(p);}

  function resetSpeakButton(){if(activeSpeakButton){activeSpeakButton.classList.remove('selected');activeSpeakButton.textContent='Soma igisubizo';activeSpeakButton=null;}}
  function stopSpeech(){speechRequestId++;if(audioPlayer){audioPlayer.onended=null;audioPlayer.onerror=null;audioPlayer.pause();audioPlayer=null;}if(audioUrl){URL.revokeObjectURL(audioUrl);audioUrl=null;}resetSpeakButton();}
  function speechNote(header){var h=(header||'').toLowerCase();if(h.indexOf('number')>-1)return 'Interuro zirimo imibare ntizasomwe. Zisome mu nyandiko.';if(h.indexOf('first')>-1)return 'Hasomwe igice cya mbere gusa.';return '';}
  async function speakAnswer(text,button){
    if(button&&activeSpeakButton===button){stopSpeech();setStatus('');return;}
    stopSpeech();var requestId=speechRequestId;activeSpeakButton=button||null;if(button){button.classList.add('selected');button.textContent='Hagarika gusoma';}setStatus('Ndimo gutegura amajwi…');
    try{
      var response=await fetchWithFallback(TTS_URL,'/api/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:(text||'').slice(0,5000)})});
      if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ijwi ntiryakunze.');}
      var note=speechNote(response.headers.get('X-Notes'));var blob=await response.blob();if(requestId!==speechRequestId)return;
      audioUrl=URL.createObjectURL(blob);audioPlayer=new Audio(audioUrl);setStatus(note?'Ndimo gusoma. '+note:'Ndimo gusoma igisubizo…');
      audioPlayer.onended=function(){if(requestId!==speechRequestId)return;stopSpeech();setStatus(note);};
      audioPlayer.onerror=function(){if(requestId!==speechRequestId)return;stopSpeech();setStatus('Ntabwo ijwi ryakinnye. Ongera ukande “Soma igisubizo”.');};
      await audioPlayer.play();
    }catch(error){if(requestId!==speechRequestId)return;stopSpeech();setStatus(error.message||'Ijwi ntiryakunze.');}
  }

  function resizeQuestion(){questionBox.style.height='auto';questionBox.style.height=Math.min(questionBox.scrollHeight,140)+'px';}
  function setMicIcon(recording){microphoneButton.classList.toggle('recording',recording);microphoneButton.setAttribute('aria-label',recording?'Hagarika gufata amajwi':'Tangira gufata amajwi');micLabel.textContent=recording?'Rangiza':'Vuga';micIcon.innerHTML=recording?'<rect x="6" y="6" width="12" height="12" rx="2"/>':'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/>';}
  function stopMicStream(){if(recordTimer){clearTimeout(recordTimer);recordTimer=null;}if(micStream){micStream.getTracks().forEach(function(track){track.stop();});micStream=null;}}
  function stopRecording(){if(!recorder||recorder.state!=='recording')return;microphoneButton.disabled=true;setStatus('Ndimo gutegura amajwi yawe…');try{recorder.stop();}catch(error){recorder=null;stopMicStream();setMicIcon(false);microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Ntabwo amajwi yafashwe. Ongera ugerageze.');}}

  async function startRecording(){
    if(isBusy||recorder)return;
    if(window.isSecureContext===false&&location.hostname!=='localhost'&&location.hostname!=='127.0.0.1'){setStatus('Koresha uru rubuga kuri HTTPS cyangwa localhost kugira ngo ufungure mikoro.');return;}
    if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia||!window.MediaRecorder){setStatus('Iyi mushakisha ntishobora gufata amajwi.');return;}
    setStatus('Emera gukoresha mikoro nibigusabwa.');
    try{
      micStream=await navigator.mediaDevices.getUserMedia({audio:true});
      var supported=['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'];
      var mimeType=MediaRecorder.isTypeSupported?(supported.find(function(type){return MediaRecorder.isTypeSupported(type);})||''):'';
      recorder=new MediaRecorder(micStream,mimeType?{mimeType:mimeType}:undefined);
      var activeRecorder=recorder,chunks=[],failed=false;
      activeRecorder.ondataavailable=function(event){if(event.data&&event.data.size)chunks.push(event.data);};
      activeRecorder.onerror=function(){failed=true;recorder=null;stopMicStream();setMicIcon(false);microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Ntabwo amajwi yafashwe. Reba uruhushya rwa mikoro.');};
      activeRecorder.onstop=async function(){
        var contentType=activeRecorder.mimeType||mimeType||'audio/webm';recorder=null;stopMicStream();setMicIcon(false);if(failed)return;
        var blob=new Blob(chunks,{type:contentType});
        if(!blob.size){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Nta majwi yafashwe. Ongera ugerageze.');return;}
        if(blob.size>20*1024*1024){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Amajwi ni manini cyane. Vuga igihe gito.');return;}
        setStatus('Ndimo kumva ibyo wavuze…');
        try{
          var response=await fetchWithFallback(ASR_URL,'/api/transcribe',{method:'POST',headers:{'Content-Type':contentType},body:blob});
          if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Ntabwo amajwi yahinduwe inyandiko.');}
          var data=await response.json();var transcript=(data.text||'').trim();
          if(!transcript){microphoneButton.disabled=false;sendButton.disabled=false;setStatus('Nta magambo numvise. Ongera ugerageze.');return;}
          questionBox.value=transcript;resizeQuestion();setStatus('');askQuestion(transcript,false);
        }catch(error){microphoneButton.disabled=false;sendButton.disabled=false;setStatus(error.message||'Ntabwo amajwi yahinduwe inyandiko.');}
      };
      recorder.start();sendButton.disabled=true;setMicIcon(true);setStatus('Ndakumva. Kanda “Rangiza” nurangiza kuvuga.');
      recordTimer=setTimeout(function(){if(recorder&&recorder.state==='recording')stopRecording();},30000);
    }catch(error){stopMicStream();recorder=null;setMicIcon(false);microphoneButton.disabled=false;setStatus('Ntabwo nashoboye gukoresha mikoro. Reba uruhushya rwa mushakisha.');}
  }

  async function askQuestion(question,voiceReply){
    question=(question||'').trim();
    if(question.length>500){setStatus('Ikibazo kirenze inyuguti 500. Gabanya inyandiko mbere yo kohereza.');return;}
    if(!question||isBusy)return;
    stopSpeech();setStatus('');isBusy=true;sendButton.disabled=true;microphoneButton.disabled=true;emptyState.hidden=true;questionBox.value='';resizeQuestion();
    var conversation=getActiveConversation();
    if(!conversation){conversation={id:'c'+Date.now().toString(36)+Math.random().toString(36).slice(2,7),title:question.slice(0,70),created:Date.now(),updated:Date.now(),items:[]};conversations.unshift(conversation);activeConversationId=conversation.id;}
    var item={question:question,answer:null,vote:null};conversation.items.push(item);
    var turn=createTurn(question);showThinking(turn);saveConversations();renderHistory();
    try{
      var response=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:question})});
      if(!response.ok){var info=await response.json().catch(function(){return{};});throw new Error(info.detail||'Habaye ikibazo mu gushaka igisubizo.');}
      var answer=await response.json();item.answer=answer;conversation.updated=Date.now();saveConversations();renderHistory();renderAnswer(turn,answer,item,false);
      if(voiceReply){var speaker=turn.body.querySelector('.tool');if(speaker)speakAnswer(answer.answer||'',speaker);}
    }catch(error){showAnswerError(turn,error.message||'Habaye ikibazo. Ongera ugerageze.');}
    finally{isBusy=false;sendButton.disabled=false;microphoneButton.disabled=false;questionBox.focus();}
  }

  document.querySelectorAll('[data-question]').forEach(function(button){button.addEventListener('click',function(){askQuestion(button.getAttribute('data-question')||'',false);});});
  chatForm.addEventListener('submit',function(event){event.preventDefault();askQuestion(questionBox.value,false);});
  questionBox.addEventListener('input',resizeQuestion);
  questionBox.addEventListener('keydown',function(event){if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();askQuestion(questionBox.value,false);}});
  microphoneButton.addEventListener('click',function(){if(recorder&&recorder.state==='recording')stopRecording();else if(!recorder&&!microphoneButton.disabled)startRecording();});
  $('new-chat').addEventListener('click',beginNewChat);
  var menuButtons=[$('toggle-history'),$('collapse-sidebar')],desktopQuery=window.matchMedia('(min-width:821px)');
  function syncMenu(){var expanded=desktopQuery.matches?!app.classList.contains('collapsed'):app.classList.contains('open');var label=expanded?'Funga ibiganiro byashize':'Fungura ibiganiro byashize';menuButtons.forEach(function(b){b.setAttribute('aria-expanded',expanded?'true':'false');b.setAttribute('aria-label',label);b.title=label;});}
  function toggleMenu(){if(desktopQuery.matches){app.classList.toggle('collapsed');try{localStorage.setItem('mfasha-sidebar',app.classList.contains('collapsed')?'closed':'open');}catch(e){}}else{app.classList.toggle('open');}}
  try{if(localStorage.getItem('mfasha-sidebar')==='closed')app.classList.add('collapsed');}catch(e){}
  menuButtons.forEach(function(b){b.addEventListener('click',toggleMenu);});
  new MutationObserver(syncMenu).observe(app,{attributes:true,attributeFilter:['class']});
  if(desktopQuery.addEventListener)desktopQuery.addEventListener('change',syncMenu);
  syncMenu();
  $('scrim').addEventListener('click',function(){app.classList.remove('open');});
  $('clear-history').addEventListener('click',function(){if(!conversations.length){setStatus('Nta biganiro bihari byo gusiba.');return;}if(!window.confirm('Urashaka gusiba ibiganiro byose?'))return;conversations=[];activeConversationId=null;saveConversations();beginNewChat();renderHistory();});
  document.querySelectorAll('[data-close]').forEach(function(b){b.addEventListener('click',function(){app.classList.remove('open');$('toggle-history').focus();});});
  document.addEventListener('keydown',function(e){if(e.key==='Escape'&&app.classList.contains('open')){app.classList.remove('open');$('toggle-history').focus();}});
  loadConversations();
}());
</script>
</body>
</html>
"""


LANDING = r"""
<!doctype html>
<html lang="rw"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mfasha – Umufasha wawe mu buhinzi n’ubworozi</title>
<meta name="description" content="Mfasha igufasha gushaka amakuru ku buhinzi n’ubworozi mu Kinyarwanda.">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{--g9:#0C3320;--g7:#1F6B35;--g5:#2E7D32;--lime:#A4C42B;--cream:#F6F4EC;--ink:#14201A;--mut:#56635B;--line:#E3DFD0;--e:cubic-bezier(.2,.7,.2,1);font-family:Inter,system-ui,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--cream);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2,h3{font-family:Fraunces,Georgia,serif;margin:0;letter-spacing:-.02em}a{color:inherit;text-decoration:none}
.nav{position:fixed;inset:0 0 auto;z-index:10;display:flex;align-items:center;gap:28px;padding:14px 5vw;transition:background .3s,box-shadow .3s}
.nav.solid{background:rgba(246,244,236,.94);box-shadow:0 1px 0 var(--line);color:var(--ink)}.nav{color:#fff}
.logo{display:flex;align-items:center;gap:9px;font:700 1.35rem Fraunces,serif}.logo i{width:30px;height:30px;border-radius:9px;background:var(--lime);display:grid;place-items:center;color:var(--g9);font:700 1rem Fraunces}
.nav nav{display:flex;gap:24px;margin-left:12px;font-weight:500;font-size:.95rem}.nav nav a{opacity:.85;transition:opacity .2s}.nav nav a:hover{opacity:1}
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 24px;border-radius:10px;font-weight:600;transition:transform .2s var(--e),box-shadow .2s var(--e),background .2s}
.btn:hover{transform:translateY(-2px)}.btn:active{transform:none}
.go{background:var(--lime);color:var(--g9)}.go:hover{box-shadow:0 8px 22px rgba(164,196,43,.45)}
.ghost{color:#fff;border:1.5px solid rgba(255,255,255,.55)}.ghost:hover{background:rgba(255,255,255,.12)}
.nav .btn{margin-left:auto;padding:9px 20px}
.hero{position:relative;color:#fff;padding:150px 5vw 170px;background:linear-gradient(125deg,var(--g9),var(--g7) 55%,#6E9A1E);overflow:hidden}
.hero:before{content:"";position:absolute;width:620px;height:620px;right:-140px;top:-180px;border-radius:50%;background:radial-gradient(circle,rgba(164,196,43,.35),transparent 68%);animation:drift 14s ease-in-out infinite alternate}
.wrap{position:relative;max-width:1180px;margin:auto;display:grid;grid-template-columns:1.05fr 1fr;gap:56px;align-items:center}
.hero h1{font-size:clamp(3rem,7vw,5.2rem);line-height:1}.hero h2{font-size:clamp(1.4rem,3vw,2rem);font-weight:600;margin-top:12px;color:#E3F0B8}
.hero p{max-width:480px;margin:20px 0 32px;font-size:1.1rem;opacity:.92}.row{display:flex;gap:12px;flex-wrap:wrap}
.wave{position:absolute;left:0;bottom:-1px;width:100%;height:90px;display:block}
.mock{position:relative;height:430px}.card{position:absolute;background:#fff;color:var(--ink);border-radius:16px;box-shadow:0 18px 50px rgba(5,30,15,.3)}
.m1{inset:30px 0 auto 40px;padding:20px;animation:float 7s ease-in-out infinite}.m1 b{font:700 .95rem Fraunces}
.q{margin:12px 0 0 auto;width:fit-content;max-width:85%;background:#E0EDE1;border-radius:14px 14px 3px 14px;padding:9px 14px;font-size:.92rem}
.a{margin-top:12px;border:1px solid var(--line);border-left:4px solid var(--g5);border-radius:3px 14px 14px 14px;padding:12px 14px;font-size:.88rem}
.bd{display:inline-block;background:#E8F5E9;color:var(--g5);font-weight:600;font-size:.74rem;border-radius:99px;padding:1px 10px;margin-bottom:6px}
.m2{left:0;bottom:60px;padding:12px 18px;display:flex;align-items:center;gap:10px;font-weight:600;font-size:.9rem;animation:float 6s 1s ease-in-out infinite}
.m2 i{width:36px;height:36px;border-radius:50%;background:var(--g5);display:grid;place-items:center;color:#fff;font-style:normal}
.m3{right:10px;bottom:20px;padding:10px 16px;font-weight:600;font-size:.85rem;background:var(--lime);color:var(--g9);animation:float 8s .5s ease-in-out infinite}
section{padding:96px 5vw}.in{max-width:1100px;margin:auto}.kick{color:var(--g5);font-weight:600;font-size:.85rem;letter-spacing:.06em;text-transform:uppercase}
.in>h2{font-size:clamp(2rem,4.5vw,3rem);margin:8px 0 14px}.in>p{max-width:560px;color:var(--mut)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px;margin-top:44px}
.f{background:#fff;border:1px solid var(--line);border-radius:16px;padding:26px;transition:transform .3s var(--e),box-shadow .3s var(--e),border-color .3s}
.f:hover{transform:translateY(-6px);box-shadow:0 16px 36px rgba(31,107,53,.14);border-color:#BFD7B3}
.f i{width:46px;height:46px;border-radius:12px;background:#E8F5E9;color:var(--g5);display:grid;place-items:center;font:700 1.2rem Fraunces;font-style:normal;transition:.3s}
.f:hover i{background:var(--g5);color:#fff;transform:rotate(-6deg) scale(1.08)}.f h3{font-size:1.2rem;margin:18px 0 6px}.f p{margin:0;color:var(--mut);font-size:.95rem}
.how{background:#fff;border-block:1px solid var(--line)}.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:30px;margin-top:48px;counter-reset:s}
.s{position:relative;padding-top:64px}.s:before{counter-increment:s;content:counter(s);position:absolute;top:0;left:0;width:48px;height:48px;border-radius:50%;background:var(--g5);color:#fff;display:grid;place-items:center;font:700 1.25rem Fraunces;transition:transform .3s var(--e),background .3s}
.s:hover:before{transform:scale(1.12);background:var(--lime);color:var(--g9)}.s:after{content:"";position:absolute;top:24px;left:60px;right:-14px;border-top:2px dashed #BFD7B3}.s:last-child:after{display:none}
.s h3{font-size:1.15rem;margin-bottom:4px}.s p{margin:0;color:var(--mut);font-size:.95rem}
.cta{text-align:center;color:#fff;background:linear-gradient(125deg,var(--g9),var(--g7));position:relative;overflow:hidden}.cta h2{font-size:clamp(2rem,4.5vw,3rem)}.cta p{opacity:.9;margin:12px 0 28px}
footer{padding:26px 5vw;text-align:center;color:var(--mut);font-size:.88rem}
.rv{opacity:0;transform:translateY(24px);transition:opacity .7s var(--e),transform .7s var(--e);transition-delay:var(--d,0s)}.rv.on{opacity:1;transform:none}
@keyframes float{50%{transform:translateY(-12px)}}@keyframes drift{to{transform:translate(-60px,40px) scale(1.15)}}
@media(max-width:860px){.wrap{grid-template-columns:1fr}.mock{height:380px}.nav nav{display:none}.s:after{display:none}.hero{padding-top:120px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.rv{opacity:1;transform:none}}
</style></head><body>
<header class="nav" id="nav"><a class="logo" href="/"><i>M</i>Mfasha</a><nav><a href="#ikora">Ibyo ikora</a><a href="#uko">Uko ikora</a></nav><a class="btn go" href="/chat">Tangira</a></header>
<div class="hero"><div class="wrap"><div>
<h1>Mfasha</h1><h2>Umufasha wawe mu buhinzi n’ubworozi</h2>
<p>Baza ikibazo mu Kinyarwanda, wandike cyangwa uvuge, maze ubone igisubizo gikomoka ku nyandiko z’ubuhinzi, gisomwe n’ijwi.</p>
<div class="row"><a class="btn go" href="/chat">Tangira →</a><a class="btn ghost" href="#uko">Reba uko ikora</a></div></div>
<div class="mock"><div class="card m1"><b>Ikiganiro</b><div class="q">Intama zororoka gute?</div><div class="a"><span class="bd">Icyizere: kinshi</span><br>Intama ihaka iminsi 149-152 (amezi 5). Yonsa amezi atatu, ishobora kubyara buri mezi 9.</div></div>
<div class="card m2"><i>●</i>Vuga ikibazo cyawe</div><div class="card m3">Soma igisubizo ▸</div></div></div>
<svg class="wave" viewBox="0 0 1440 90" preserveAspectRatio="none"><path d="M0 60C240 100 480 10 760 40s460 30 680-10v60H0z" fill="#F6F4EC"/></svg></div>
<section id="ikora"><div class="in"><span class="kick rv">Mfasha ikora iki?</span><h2 class="rv">Ibisubizo ku buhinzi n’ubworozi, mu rurimi rwawe</h2><p class="rv">Mfasha ishakira igisubizo mu nyandiko z’ubuhinzi, ikakigaragariza aho cyakomotse.</p>
<div class="grid">
<div class="f rv"><i>K</i><h3>Mu Kinyarwanda</h3><p>Baza ku bihingwa, amatungo, ifumbire n’ubutaka mu rurimi rwawe.</p></div>
<div class="f rv" style="--d:.08s"><i>V</i><h3>Andika cyangwa uvuge</h3><p>Koresha inyandiko cyangwa mikoro, Mfasha irakumva.</p></div>
<div class="f rv" style="--d:.16s"><i>I</i><h3>Ibisubizo byizewe</h3><p>Igisubizo gikomoka ku nyandiko, kandi iyo nta cyo ifite irabivuga.</p></div>
<div class="f rv" style="--d:.24s"><i>S</i><h3>Umva igisubizo</h3><p>Kanda “Soma igisubizo” wumve igisubizo gisomwa n’ijwi.</p></div></div></div></section>
<section class="how" id="uko"><div class="in"><span class="kick rv">Uko ikora</span><h2 class="rv">Intambwe enye gusa</h2>
<div class="steps"><div class="s rv"><h3>Baza</h3><p>Andika cyangwa uvuge ikibazo cyawe.</p></div>
<div class="s rv" style="--d:.1s"><h3>Mfasha irashakisha</h3><p>Ishakisha mu nyandiko z’ubuhinzi igice gikwiye.</p></div>
<div class="s rv" style="--d:.2s"><h3>Wakira igisubizo</h3><p>Ubona igisubizo, icyizere cyacyo n’andi makuru.</p></div>
<div class="s rv" style="--d:.3s"><h3>Umva</h3><p>Igisubizo gisomwa n’ijwi mu Kinyarwanda.</p></div></div></div></section>
<section class="cta"><div class="in"><h2 class="rv">Witeguye gutangira?</h2><p class="rv">Baza ikibazo cya mbere cyawe none.</p><a class="btn go rv" href="/chat">Tangira none →</a></div></section>
<footer>Mfasha · Umufasha wawe mu buhinzi n’ubworozi</footer>
<script>var n=document.getElementById('nav');function t(){n.classList.toggle('solid',scrollY>40)}t();addEventListener('scroll',t,{passive:true});
var io=new IntersectionObserver(function(e){e.forEach(function(x){if(x.isIntersecting){x.target.classList.add('on');io.unobserve(x.target)}})},{threshold:.15});document.querySelectorAll('.rv').forEach(function(x){io.observe(x)});</script>
</body></html>
"""


if __name__ == "__main__":      
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "7860")))