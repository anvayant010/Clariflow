"""One error shape for the whole API: {"error": {"code": ..., "message": ...}}.

Messages are written for the person using the app. Provider details, keys, file names and stack
traces never reach the client; the request id (X-Request-ID) is what to quote when reporting a problem.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.adapters.gnani_common import GnaniError
from backend.app.services.audioconv import AudioError
from backend.app.storage.store import StoreError

log = logging.getLogger("clariflow")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


STORE_MESSAGES = {
    "not_found": (404, "That report was not found."),
    "stale_revision": (409, "The report changed after you reviewed it. Please review it again."),
    "blockers_open": (409, "There is still an open question to answer first."),
    "not_confirmed": (409, "That version has not been confirmed."),
    "idempotency_conflict": (409, "That confirmation was already used for a different report."),
    "already_saved": (409, "This report is already saved."),
}
GNANI_UNAVAILABLE = (503, "speech_unavailable", "The speech service is unavailable right now. Please try again, or type your answer.")
GNANI_BUSY = (503, "speech_busy", "The speech service is busy. Please try again in a moment.")


def body(code: str, message: str, request: Request | None = None) -> dict:
    out = {"error": {"code": code, "message": message}}
    rid = getattr(request.state, "request_id", None) if request else None
    if rid:
        out["error"]["request_id"] = rid
    return out


def register(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(request: Request, e: ApiError):
        return JSONResponse(body(e.code, e.message, request), status_code=e.status)

    @app.exception_handler(StoreError)
    async def _store(request: Request, e: StoreError):
        status, message = STORE_MESSAGES.get(e.kind, (409, "That could not be done."))
        return JSONResponse(body(e.kind, message, request), status_code=status)

    @app.exception_handler(AudioError)
    async def _audio(request: Request, e: AudioError):
        return JSONResponse(body(f"audio_{e.code}", str(e), request), status_code=422)

    @app.exception_handler(GnaniError)
    async def _gnani(request: Request, e: GnaniError):
        log.warning("provider error kind=%s", e.kind)  # kind only: never the message body
        status, code, message = GNANI_BUSY if e.kind in ("rate_limited", "timeout", "upstream_timeout", "unavailable") else GNANI_UNAVAILABLE
        return JSONResponse(body(code, message, request), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, e: RequestValidationError):
        fields = sorted({str(err["loc"][-1]) for err in e.errors() if err.get("loc")})
        return JSONResponse(body("invalid_request", "Invalid request: check " + ", ".join(fields or ["the input"]), request),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, e: StarletteHTTPException):
        return JSONResponse(body("http_%d" % e.status_code, "Not found." if e.status_code == 404 else "Request failed.", request),
                            status_code=e.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, e: Exception):
        log.exception("unhandled error id=%s", getattr(request.state, "request_id", "-"))
        return JSONResponse(body("internal_error", "Something went wrong on our side.", request), status_code=500)
