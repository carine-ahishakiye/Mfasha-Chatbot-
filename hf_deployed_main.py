
"""FastAPI application factory. Routes live in routes.py; this file wires things together."""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from mfasha import __version__
from mfasha.auth import LoginThrottle
from mfasha.api.routes import router
from mfasha.config import ROOT, Settings
from mfasha.domain.errors import (
    InvalidAudioError,
    KnowledgeBaseError,
    MfashaError,
    ServiceUnavailableError,
)
from mfasha.factory import build_pipeline
from mfasha.knowledge.base import KnowledgeBase
from mfasha.pipeline import MfashaPipeline
from mfasha.storage import InteractionRepository, create_session_factory

logging.basicConfig(
    filename="mfasha.log",
    encoding="utf-8",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("mfasha")


class FreshStaticFiles(StaticFiles):
    """Serves frontend files without caching."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    settings: Optional[Settings] = None,
    pipeline: Optional[MfashaPipeline] = None,
    knowledge_base: Optional[KnowledgeBase] = None,
    repository: Optional[InteractionRepository] = None,
) -> FastAPI:
    """Every collaborator can be injected, which is how the tests run the API with fakes."""

    settings = settings or Settings.from_env()

    if pipeline is None:
        pipeline, knowledge_base = build_pipeline(settings, knowledge_base)

    if repository is None:
        repository = InteractionRepository(
            create_session_factory(settings.database_url)
        )

    app = FastAPI(
        title="MFASHA API",
        version=__version__,
        description="Kinyarwanda agriculture chatbot with text and voice support",
    )

    app.state.settings = settings
    app.state.pipeline = pipeline
    app.state.kb = knowledge_base
    app.state.repository = repository
    app.state.secret = settings.secret_key or secrets.token_hex(32)
    app.state.throttle = LoginThrottle()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    _register_error_handlers(app)

    # Register API routes before the frontend mount.
    app.include_router(router, prefix="/api")

    # Return 405 when an existing API path receives an unsupported method.
    # Unknown API paths continue to return 404.
    # Store allowed HTTP methods for each registered API path.
    api_methods_by_path = {
        "/api" + route.path: set(route.methods or [])
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    # Return 405 when an existing API path receives an unsupported method.
    @app.middleware("http")
    async def check_api_http_method(request: Request, call_next):
        path = request.scope.get("path", "")

        # Remove the Hugging Face mount prefix when present.
        if path.startswith("/mfasha/"):
            path = path[len("/mfasha"):]

        if path.startswith("/api/"):
            allowed_methods = api_methods_by_path.get(path)

            if allowed_methods and request.method not in allowed_methods:
                return JSONResponse(
                    status_code=405,
                    content={"detail": "Method Not Allowed"},
                    headers={
                        "Allow": ", ".join(sorted(allowed_methods))
                    },
                )

        return await call_next(request)

    frontend = ROOT / "frontend"

    if frontend.exists():
        app.mount(
            "/",
            FreshStaticFiles(
                directory=frontend,
                html=True,
            ),
            name="frontend",
        )

    return app


def _register_error_handlers(app: FastAPI) -> None:
    def respond(status: int, code: str):
        async def handler(_: Request, exc: MfashaError):
            return JSONResponse(
                status_code=status,
                content={"error": code, "detail": str(exc)},
            )

        return handler

    app.add_exception_handler(
        InvalidAudioError,
        respond(422, "invalid_audio"),
    )

    app.add_exception_handler(
        ServiceUnavailableError,
        respond(503, "service_unavailable"),
    )

    app.add_exception_handler(
        KnowledgeBaseError,
        respond(500, "knowledge_base_error"),
    )

    # Log rejected requests without recording questions, phone numbers or PINs.
    @app.exception_handler(StarletteHTTPException)
    async def log_http_error(
        request: Request,
        exc: StarletteHTTPException,
    ):
        logger.warning(
            "%s %s -> %s %s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )

        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def log_validation_error(
        request: Request,
        exc: RequestValidationError,
    ):
        first = exc.errors()[0]

        logger.warning(
            "%s %s -> 422 invalid input (%s)",
            request.method,
            request.url.path,
            first.get("msg", ""),
        )

        return await request_validation_exception_handler(request, exc)
