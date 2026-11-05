"""Gnani Prisma speech-to-text adapter (REST, <= 30 s per clip)."""
import uuid

from pydantic import BaseModel

from backend.app.adapters import gnani_common
from backend.app.config import Settings, get_settings

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}


class SttResult(BaseModel):
    transcript: str  # empty string means no speech; that is not an error
    request_id: str
    model: str
    detected_language_code: str | None = None
    truncated: bool = False
    end_to_end_latency: float | None = None
    language_code_sent: str
    format_sent: str


def transcribe(
    audio: bytes,
    filename: str,
    language_code: str,
    *,
    content_type: str = "audio/wav",
    fmt: str = "verbatim",
    context: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> SttResult:
    """Send one clip to Prisma.

    language_code: "mr-IN" | "hi-IN" | "en-IN" | "indic-auto" | "hi-IN,en-IN" (v3.0 hints).
    fmt: "verbatim" (raw spoken form) | "transcribe" (inverse text normalisation) | "codemix".
    context: optional v3.0 fields, e.g. {"keyterms": '["P-12"]', "topic": "..."}.
    """
    s = settings or get_settings()
    request_id = str(uuid.uuid4())
    resp = gnani_common.post(
        s.gnani_stt_url,
        s.gnani_api_key_id,
        fallback_key=s.gnani_api_key_id_2,
        headers={"X-API-Request-ID": request_id},
        files={"audio_file": (filename, audio, content_type)},
        data={"model": s.gnani_stt_model, "language_code": language_code, "format": fmt, **(context or {})},
    )
    body = resp.json()
    return SttResult(
        transcript=body.get("transcript") or "",
        request_id=body.get("request_id") or request_id,
        model=body.get("model") or s.gnani_stt_model,
        detected_language_code=body.get("detected_language_code"),
        truncated=bool(body.get("truncated", False)),
        end_to_end_latency=body.get("end_to_end_latency"),
        language_code_sent=language_code,
        format_sent=fmt,
    )
