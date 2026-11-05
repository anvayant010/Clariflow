"""FastAPI application.   Run:  .venv\\Scripts\\uvicorn backend.app.main:create_app --factory --port 8000

create_app() takes the outbound seams (speech recognition, voice) and the store as arguments so
tests run the real routes without any network call.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import errors
from backend.app.api.limits import Limits
from backend.app.api.providers import Ears, GnaniEars, GnaniVoice, Voice
from backend.app.api.routes import build_router
from backend.app.config import Settings, get_settings
from backend.app.domain.assets import load_catalogue
from backend.app.domain.schemas import Asset
from backend.app.storage.store import Store, make_engine

log = logging.getLogger("clariflow")
ROOT = Path(__file__).resolve().parents[2]
MAX_BODY_BYTES = 10_000_000


@dataclass
class AppContext:
    settings: Settings
    store: Store
    catalogue: list[Asset]
    ears: Ears
    voice: Voice
    limits: Limits
    speech_configured: bool
    cache: dict = field(default_factory=dict)


def create_app(settings: Settings | None = None, store: Store | None = None, ears: Ears | None = None,
               voice: Voice | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = store or Store(make_engine(settings.database_url))
    catalogue = load_catalogue()
    app = FastAPI(title="Clariflow", docs_url=None, redoc_url=None, openapi_url=None)  # no public schema page
    app.state.ctx = AppContext(
        settings=settings, store=store, catalogue=catalogue, ears=ears or GnaniEars(catalogue, settings),
        voice=voice or GnaniVoice(settings), limits=Limits(store, settings),
        speech_configured=bool(settings.gnani_api_key_id or settings.gnani_api_key_id_2) or ears is not None)

    errors.register(app)
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], allow_credentials=False)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            response = JSONResponse(errors.body("too_large", "That upload is too large.", request), status_code=413)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api"):
            # path and timing only: never bodies, audio, file names or query strings
            log.info("%s %s -> %s in %.0f ms id=%s", request.method, request.url.path, response.status_code,
                     (time.perf_counter() - started) * 1000, request.state.request_id)
        return response

    app.include_router(build_router())
    dist = ROOT / "frontend" / "dist"
    if dist.is_dir():  # one origin in production: the built React app is served by the same server
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app

