"""Gnani Timbre text-to-speech adapter (synchronous binary audio)."""
from backend.app.adapters import gnani_common
from backend.app.config import Settings, get_settings


def synthesize(
    text: str,
    language: str,
    *,
    voice: str | None = None,
    speed: float = 1.0,
    sample_rate: int = 24000,
    settings: Settings | None = None,
) -> bytes:
    """Return WAV bytes for `text`. Write numbers/dates as spoken words in `text`.

    language: "mr-IN" | "hi-IN" | "en-IN" | "hi-en" (Hinglish) | "auto".
    """
    s = settings or get_settings()
    if not text.strip():
        raise gnani_common.GnaniError("bad_request", "empty text")
    resp = gnani_common.post(
        s.gnani_tts_url,
        s.gnani_api_key_id,
        fallback_key=s.gnani_api_key_id_2,
        json={
            "text": text,
            "model": s.gnani_tts_model,
            "voice": voice or s.gnani_tts_voice,
            "language": language,
            "speed": speed,
            "audio_config": {
                "sample_rate": sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
    )
    if not resp.content:
        raise gnani_common.GnaniError("provider_error", "empty audio returned", resp.status_code)
    return resp.content
