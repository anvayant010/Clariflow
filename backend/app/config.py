"""Settings from environment (.env is git-ignored). Secrets stay backend-only."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gnani_api_key_id: str
    gnani_stt_url: str
    gnani_tts_url: str
    gnani_stt_model: str
    gnani_tts_model: str
    gnani_tts_voice: str
    extractor_provider: str
    extractor_api_key: str
    database_url: str
    # ---- public-demo protection (credits are limited: 5,000 programme credits in total)
    allow_fixture: bool = False  # accept pasted FIXTURE transcripts (development only)
    daily_stt_cap: int = 300  # Prisma calls per UTC day, all visitors
    daily_tts_cap: int = 400  # Timbre calls per UTC day (cache misses only)
    session_audio_cap: int = 15  # recordings per report session
    session_tts_cap: int = 30  # question/read-back audio generations per session
    ip_sessions_per_day: int = 30
    ip_stt_per_day: int = 60  # Prisma calls per visitor per UTC day
    ip_tts_per_day: int = 100  # Timbre generations per visitor per UTC day
    ip_requests_per_minute: int = 120
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    trusted_proxy_hops: int = 0  # proxies in front of this server (0 = none: use the connection address)
    gnani_api_key_id_2: str = ""  # optional second key (a teammate's own registration), used only when the first runs out of credit

    def __repr__(self) -> str:  # never leak keys into logs
        return (
            f"Settings(stt_model={self.gnani_stt_model!r}, "
            f"extractor={self.extractor_provider!r}, key_set={bool(self.gnani_api_key_id)}, second_key_set={bool(self.gnani_api_key_id_2)})"
        )


def get_settings() -> Settings:
    return Settings(
        gnani_api_key_id=os.getenv("GNANI_API_KEY_ID", ""),
        gnani_stt_url=os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3"),
        gnani_tts_url=os.getenv("GNANI_TTS_URL", "https://api.vachana.ai/api/v1/tts/inference"),
        gnani_stt_model=os.getenv("GNANI_STT_MODEL", "prisma-v3.0"),
        gnani_tts_model=os.getenv("GNANI_TTS_MODEL", "timbre-v3.0"),
        gnani_tts_voice=os.getenv("GNANI_TTS_VOICE", "Shivani"),
        extractor_provider=os.getenv("EXTRACTOR_PROVIDER", "deterministic"),
        extractor_api_key=os.getenv("EXTRACTOR_API_KEY", ""),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./clariflow.db"),
        allow_fixture=os.getenv("ALLOW_FIXTURE", "").lower() in ("1", "true", "yes"),
        daily_stt_cap=int(os.getenv("DAILY_STT_CAP", "300")),
        daily_tts_cap=int(os.getenv("DAILY_TTS_CAP", "400")),
        session_audio_cap=int(os.getenv("SESSION_AUDIO_CAP", "15")),
        session_tts_cap=int(os.getenv("SESSION_TTS_CAP", "30")),
        ip_sessions_per_day=int(os.getenv("IP_SESSIONS_PER_DAY", "30")),
        ip_stt_per_day=int(os.getenv("IP_STT_PER_DAY", "60")),
        ip_tts_per_day=int(os.getenv("IP_TTS_PER_DAY", "100")),
        ip_requests_per_minute=int(os.getenv("IP_REQUESTS_PER_MINUTE", "120")),
        cors_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
        trusted_proxy_hops=max(0, int(os.getenv("TRUSTED_PROXY_HOPS", "0"))),
        gnani_api_key_id_2=os.getenv("GNANI_API_KEY_ID_2", ""),
    )
