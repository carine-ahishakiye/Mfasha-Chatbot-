"""Application factory: builds the FastAPI app, loads the models at start-up, and wires the routes."""
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .. import config
from ..interfaces import SpeechSynthesizer
from ..pipeline import Mfasha
from .routes import build_router
from .services import Services

STATIC = Path(__file__).parent / "static"


def _quantize_asr(bot) -> None:
    """Optional int8 speech recognition, faster on CPU (MFASHA_FAST_ASR=1)."""
    try:
        import torch
        asr = getattr(bot, "transcriber", None)
        if asr is not None and getattr(asr, "device", "cpu") == "cpu":
            asr.model = torch.quantization.quantize_dynamic(asr.model, {torch.nn.Linear}, dtype=torch.qint8)
            print("ASR: int8 speed mode on")
    except Exception as e:
        print("ASR speed mode skipped:", e)


def _warm_up(sv: Services) -> None:
    """The first call of each model is slow, so do one of each before the first visitor."""
    try:
        t0 = time.time()
        sv.voice.speaker.speak("Muraho.")
        asr = getattr(sv.bot, "transcriber", None)
        if asr:
            asr.transcribe(np.zeros(config.ASR_SR, dtype=np.float32))
        print(f"warm-up done in {time.time() - t0:.0f}s")
    except Exception as e:
        print("warm-up skipped:", e)


def create_app(bot: Optional[Mfasha] = None, speaker: Optional[SpeechSynthesizer] = None,
               feedback_file: Optional[Path] = None) -> FastAPI:
    """Pass a bot and a speaker to run without loading any model (tests); leave them out for the real app."""
    sv = Services(bot=bot, feedback_file=feedback_file or config.FEEDBACK_FILE)
    if speaker is not None:
        sv.attach_speaker(speaker)

    @asynccontextmanager
    async def lifespan(_app):
        if sv.bot is None:
            print("loading models, this takes a few minutes the first time ...")
            sv.bot = Mfasha.load()
        if sv.voice.speaker is None:
            from ..tts import Speaker
            sv.attach_speaker(Speaker())
        if os.getenv("MFASHA_FAST_ASR") == "1":
            _quantize_asr(sv.bot)
        _warm_up(sv)
        print("ready")
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(build_router(sv))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
