"""Glue between the UI and the Gnani adapters: STT configuration (decision D12), clip validation,
audio storage for evidence playback, and cached question audio (Timbre).

Nothing here touches the draft. Failures raise GnaniError / ClipError and the caller decides.
"""
import hashlib
import io
import json
import mimetypes
import os
import uuid
import wave
from collections.abc import Callable
from pathlib import Path

from backend.app.adapters import gnani_stt, gnani_tts
from backend.app.config import Settings, get_settings
from backend.app.domain.schemas import Asset
from backend.app.services.spoken import to_spoken

_ROOT = Path(__file__).resolve().parents[3]
# Where recordings and cached voice live. On a host this is the mounted disk (DATA_DIR=/data); locally it is ./data.
DATA_DIR = Path(os.getenv("DATA_DIR") or (_ROOT / "data"))
# Read-only question audio that ships with the app (synthetic Timbre output), so a host whose disk starts empty
# does not spend credits or make the first visitor wait to hear common questions.
SEED_TTS_DIR = _ROOT / "deploy" / "tts_seed"
STT_LANGUAGES = "mr-IN,hi-IN,en-IN"  # hint list; the language setting barely mattered in the gate test
STT_FORMAT = "codemix"
MAX_CLIP_SECONDS = 30
MAX_CLIP_BYTES = 8_000_000
TTS_LANGUAGE = {"mr": "mr-IN", "hi": "hi-IN", "en": "en-IN"}
DOMAIN_WORDS = ["pump", "compressor", "motor", "fan", "pressure", "PSI", "temperature", "vibration", "leakage"]
TOPIC = "Industrial maintenance incident report: pumps, compressors, motors and fans, pressure in PSI, temperature"


class ClipError(ValueError):
    """The clip was rejected before any provider call (type, size or length)."""


def stt_context(catalogue: list[Asset]) -> dict[str, str]:
    """Prisma v3.0 context: our own asset IDs as keyterms + a short topic (disclosed in the write-up)."""
    return {"keyterms": json.dumps([a.id for a in catalogue] + DOMAIN_WORDS, ensure_ascii=False), "topic": TOPIC}


def validate_clip(audio: bytes, filename: str) -> str:
    """Return the content type, or raise ClipError. Never relabels one container as another."""
    ext = Path(filename).suffix.lower()
    if ext not in gnani_stt.SUPPORTED_EXTENSIONS:
        raise ClipError(f"unsupported file type {ext or '(none)'}; use wav, m4a, mp3, ogg, flac or aac")
    if not audio:
        raise ClipError("the clip is empty")
    if len(audio) > MAX_CLIP_BYTES:
        raise ClipError("the clip is too large")
    if ext == ".wav":
        try:
            with wave.open(io.BytesIO(audio)) as w:
                seconds = w.getnframes() / float(w.getframerate())
        except (wave.Error, EOFError, ZeroDivisionError):
            raise ClipError("the file is not a valid WAV") from None
        if seconds > MAX_CLIP_SECONDS:
            raise ClipError(f"the clip is {seconds:.0f} s; the limit is {MAX_CLIP_SECONDS} s")
    return mimetypes.guess_type(filename)[0] or "audio/wav"


def make_transcriber(catalogue: list[Asset], settings: Settings | None = None,
                     plain: bool = False) -> Callable[[bytes, str], object]:
    """A `transcriber(audio, filename) -> SttResult` using the chosen STT config. Validates first.
    plain=True is the naive baseline's STT: format verbatim, no keyterms, no topic."""
    context = None if plain else stt_context(catalogue)
    fmt = "verbatim" if plain else STT_FORMAT

    def transcriber(audio: bytes, filename: str):
        content_type = validate_clip(audio, filename)
        return gnani_stt.transcribe(audio, filename, STT_LANGUAGES, content_type=content_type,
                                    fmt=fmt, context=context, settings=settings)

    return transcriber


def save_audio(session_id: str, audio: bytes, filename: str) -> str:
    """Keep the clip so an evidence receipt can play it back. Returns a path relative to the data dir."""
    ext = Path(filename).suffix.lower() or ".wav"
    rel = Path("audio") / session_id / f"{uuid.uuid4().hex}{ext}"
    target = DATA_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(audio)
    return rel.as_posix()


def load_audio(audio_ref: str | None) -> bytes | None:
    if not audio_ref:
        return None
    path = (DATA_DIR / audio_ref).resolve()
    if DATA_DIR.resolve() not in path.parents or not path.is_file():
        return None
    return path.read_bytes()


def _cache_path(text: str, language: str, s: Settings) -> tuple[str, Path]:
    lang = TTS_LANGUAGE[language]
    spoken = to_spoken(text, language)  # numbers, asset IDs, times and units as words
    digest = hashlib.sha256(f"{s.gnani_tts_model}|{s.gnani_tts_voice}|{lang}|{spoken}".encode("utf-8")).hexdigest()[:32]
    return spoken, DATA_DIR / "tts_cache" / f"{digest}.wav"


def is_cached(text: str, language: str, settings: Settings | None = None) -> bool:
    """True when speak() would be served from disk (no credits used)."""
    path = _cache_path(text, language, settings or get_settings())[1]
    return path.is_file() or (SEED_TTS_DIR / path.name).is_file()


def speak(text: str, language: str, settings: Settings | None = None) -> bytes:
    """Timbre audio for `text` in 'mr' | 'hi' | 'en'. Cached on disk so repeats cost no credits."""
    s = settings or get_settings()
    lang = TTS_LANGUAGE[language]
    text, path = _cache_path(text, language, s)
    if path.is_file():
        return path.read_bytes()
    seeded = SEED_TTS_DIR / path.name
    if seeded.is_file():
        return seeded.read_bytes()
    audio = gnani_tts.synthesize(text, lang, settings=s)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return audio
