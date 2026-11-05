"""Public-demo protection: the programme gives 5,000 credits in total, so a shared link must not be able
to drain them. Quotas live in the database (they survive restarts); the per-minute window is in memory.

Raw IP addresses are never stored: a short hash is used as the key.
"""
import hashlib
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from backend.app.api.errors import ApiError
from backend.app.config import Settings
from backend.app.storage.store import Store


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Limits:
    def __init__(self, store: Store, settings: Settings, clock=time.monotonic):
        self.store, self.s, self.clock = store, settings, clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def ip_key(ip: str) -> str:
        return hashlib.sha256(f"clariflow-ip|{ip}".encode()).hexdigest()[:16]

    def check_rate(self, ip: str) -> None:
        now, window = self.clock(), 60.0
        with self._lock:
            q = self._hits[self.ip_key(ip)]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= self.s.ip_requests_per_minute:
                raise ApiError(429, "rate_limited", "Too many requests. Please wait a moment and try again.")
            q.append(now)

    def take_session(self, ip: str) -> None:
        if not self.store.take(f"ip:{self.ip_key(ip)}:{_today()}", "sessions", self.s.ip_sessions_per_day):
            raise ApiError(429, "session_limit", "Daily limit of new reports reached for this connection. Please try again tomorrow.")

    def take_stt(self, session_id: str | None, ip: str, n: int = 1) -> None:
        for _ in range(n):
            if not self.store.take(f"ip:{self.ip_key(ip)}:{_today()}", "stt", self.s.ip_stt_per_day):
                raise ApiError(429, "visitor_limit", "You have reached today's speech limit for this demo. Typed answers still work.")
            if session_id and not self.store.take(f"session:{session_id}", "stt", self.s.session_audio_cap):
                raise ApiError(429, "session_audio_limit", "This report has reached its recording limit. Start a new report.")
            if not self.store.take(f"day:{_today()}", "stt", self.s.daily_stt_cap):
                raise ApiError(429, "daily_limit", "The demo has reached today's speech-recognition limit. Typed answers still work.")

    def take_tts(self, session_id: str | None, ip: str) -> None:
        if not self.store.take(f"ip:{self.ip_key(ip)}:{_today()}", "tts", self.s.ip_tts_per_day):
            raise ApiError(429, "visitor_voice_limit", "You have reached today's voice limit for this demo. Questions are still shown as text.")
        if session_id and not self.store.take(f"session:{session_id}", "tts", self.s.session_tts_cap):
            raise ApiError(429, "session_voice_limit", "This report has reached its voice limit. Questions are still shown as text.")
        if not self.store.take(f"day:{_today()}", "tts", self.s.daily_tts_cap):
            raise ApiError(429, "daily_voice_limit", "The demo has reached today's voice limit. Questions are still shown as text.")

    def remaining(self, session_id: str) -> dict:
        return {"recordings": max(0, self.s.session_audio_cap - self.store.used(f"session:{session_id}", "stt")),
                "voice_prompts": max(0, self.s.session_tts_cap - self.store.used(f"session:{session_id}", "tts"))}
