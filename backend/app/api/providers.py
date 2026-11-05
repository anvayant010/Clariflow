"""The two outbound seams (speech recognition, voice). Tests replace them; production uses Gnani."""
from typing import Protocol

from backend.app.adapters.gnani_stt import SttResult
from backend.app.config import Settings
from backend.app.domain.schemas import Asset
from backend.app.services import speech


class Ears(Protocol):
    def transcribe(self, wav: bytes, plain: bool = False) -> SttResult: ...


class Voice(Protocol):
    def cached(self, text: str, language: str) -> bool: ...
    def speak(self, text: str, language: str) -> bytes: ...


class GnaniEars:
    """Prisma v3.0. plain=True is the naive baseline's STT (verbatim, no keyterms)."""

    def __init__(self, catalogue: list[Asset], settings: Settings | None = None):
        self._main = speech.make_transcriber(catalogue, settings)
        self._plain = speech.make_transcriber(catalogue, settings, plain=True)

    def transcribe(self, wav: bytes, plain: bool = False) -> SttResult:
        return (self._plain if plain else self._main)(wav, "clip.wav")


class GnaniVoice:
    """Timbre v3.0 with the on-disk cache."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def cached(self, text: str, language: str) -> bool:
        return speech.is_cached(text, language, self.settings)

    def speak(self, text: str, language: str) -> bytes:
        return speech.speak(text, language, self.settings)
