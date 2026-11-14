"""FastAPI application factory. Routes live in `routes.py`; this file only wires things together."""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match, Mount

from mfasha import __version__
from mfasha.auth import LoginThrottle
from mfasha.api.routes import router
from mfasha.config import ROOT, Settings
from mfasha.domain.errors import InvalidAudioError, KnowledgeBaseError, MfashaError, ServiceUnavailableError
from mfasha.factory import build_pipeline
from mfasha.knowledge.base import KnowledgeBase
from mfasha.pipeline import MfashaPipeline
from mfasha.storage import InteractionRepository, create_session_factory

logging.basicConfig(
    filename="mfasha.log", encoding="utf-8", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mfasha")


class FreshStaticFiles(StaticFiles):
    """Serves the web pages with `no-cache`, so a browser always re-checks and never keeps an old design.

    The pages are mounted at "/", which would swallow a request such as GET /api/ask/text (a POST-only route)
    and answer 404. For paths under /api/ we first check whether an API route matches the path with a
    different method, and if so answer 405 with an Allow header, as HTTP requires."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            allowed = _allowed_methods(scope)
            if allowed and scope["method"] not in allowed:
                response = JSONResponse({"detail": "Method Not Allowed"}, status_code=405,
                                        headers={"Allow": ", ".join(sorted(allowed))})
                await response(scope, receive, send)
                return
        await super().__call__(scope, receive, send)

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _allowed_methods(scope) -> set[str]:
    """HTTP methods that an API route accepts on this exact path (empty when the path does not exist)."""
    allowed: set[str] = set()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        probe = {**scope, "method": method}
        for route in scope["app"].router.routes:
            if not isinstance(route, Mount) and route.matches(probe)[0] == Match.FULL:
                allowed.add(method)
                break
    return allowed


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

    # Error tracking: every rejected request is written to mfasha.log with its status code and reason.
    # The question text, phone number and PIN are never logged.
    @app.exception_handler(StarletteHTTPException)
    async def log_http_error(request: Request, exc: StarletteHTTPException):
        logger.warning("%s %s -> %s %s", request.method, request.url.path, exc.status_code, exc.detail)
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        logger.warning("%s %s -> 422 invalid input (%s)", request.method, request.url.path, first.get("msg", ""))
        return await request_validation_exception_handler(request, exc)