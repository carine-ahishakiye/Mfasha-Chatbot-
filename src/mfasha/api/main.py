"""FastAPI application factory. Routes live in `routes.py`; this file only wires things together."""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from mfasha import __version__
from mfasha.auth import LoginThrottle
from mfasha.api.routes import router
from mfasha.config import ROOT, Settings
from mfasha.domain.errors import InvalidAudioError, KnowledgeBaseError, MfashaError, ServiceUnavailableError
from mfasha.factory import build_pipeline
from mfasha.knowledge.base import KnowledgeBase
from mfasha.pipeline import MfashaPipeline
from mfasha.storage import InteractionRepository, create_session_factory


class FreshStaticFiles(StaticFiles):
    """Serves the web pages with `no-cache`, so a browser always re-checks and never keeps an old design."""
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(settings: Optional[Settings] = None, pipeline: Optional[MfashaPipeline] = None,
               knowledge_base: Optional[KnowledgeBase] = None,
               repository: Optional[InteractionRepository] = None) -> FastAPI:
    """Every collaborator can be injected, which is how the tests run the API with fakes."""
    settings = settings or Settings.from_env()
    if pipeline is None:
        pipeline, knowledge_base = build_pipeline(settings, knowledge_base)
    if repository is None:
        repository = InteractionRepository(create_session_factory(settings.database_url))

    app = FastAPI(title="MFASHA API", version=__version__,
                  description="Kinyarwanda agriculture chatbot with text and voice support")
    app.state.settings, app.state.pipeline = settings, pipeline
    app.state.kb, app.state.repository = knowledge_base, repository
    app.state.secret = settings.secret_key or secrets.token_hex(32)   # random: tokens end at restart
    app.state.throttle = LoginThrottle()

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    _register_error_handlers(app)
    app.include_router(router, prefix="/api")

    frontend = ROOT / "frontend"
    if frontend.exists():                       # the farmer web app is served from the same origin
        app.mount("/", FreshStaticFiles(directory=frontend, html=True), name="frontend")
    return app


def _register_error_handlers(app: FastAPI) -> None:
    def respond(status: int, code: str):
        async def handler(_: Request, exc: MfashaError):
            return JSONResponse(status_code=status, content={"error": code, "detail": str(exc)})
        return handler

    app.add_exception_handler(InvalidAudioError, respond(422, "invalid_audio"))
    app.add_exception_handler(ServiceUnavailableError, respond(503, "service_unavailable"))
    app.add_exception_handler(KnowledgeBaseError, respond(500, "knowledge_base_error"))