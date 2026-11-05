import httpx
import pytest

from backend.app.adapters import gnani_common, gnani_stt, gnani_tts
from backend.app.config import Settings


def make_settings(key="SECRET-KEY-123") -> Settings:
    return Settings(
        gnani_api_key_id=key,
        gnani_stt_url="https://stt.test/stt/v3",
        gnani_tts_url="https://tts.test/inference",
        gnani_stt_model="prisma-v3.0",
        gnani_tts_model="timbre-v3.0",
        gnani_tts_voice="Shivani",
        extractor_provider="deterministic",
        extractor_api_key="",
        database_url="sqlite://",
    )


def resp(status, json=None, content=b""):
    return httpx.Response(status, json=json, content=None if json is not None else content,
                          request=httpx.Request("POST", "https://x.test"))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gnani_common.time, "sleep", lambda s: None)


def test_stt_success_sends_expected_fields(monkeypatch):
    seen = {}

    def fake_post(url, headers, timeout, files, data):
        seen.update(url=url, headers=headers, files=files, data=data)
        return resp(200, {"success": True, "request_id": "r1", "transcript": "पन्नास PSI",
                          "model": "prisma-v3.0", "detected_language_code": "mr-IN"})

    monkeypatch.setattr(gnani_common.httpx, "post", fake_post)
    r = gnani_stt.transcribe(b"RIFF", "a.wav", "mr-IN", settings=make_settings())
    assert r.transcript == "पन्नास PSI" and r.detected_language_code == "mr-IN"
    assert seen["headers"]["X-API-Key-ID"] == "SECRET-KEY-123"
    assert seen["data"] == {"model": "prisma-v3.0", "language_code": "mr-IN", "format": "verbatim"}
    assert "audio_file" in seen["files"]


def test_stt_empty_transcript_is_not_an_error(monkeypatch):
    monkeypatch.setattr(gnani_common.httpx, "post",
                        lambda *a, **k: resp(200, {"success": True, "transcript": "", "request_id": "r"}))
    assert gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings()).transcript == ""


def test_429_is_retried_then_succeeds(monkeypatch):
    calls = iter([resp(429, {"detail": {"error_code": "RATE_LIMITED", "message": "slow"}}),
                  resp(200, {"transcript": "ok", "request_id": "r"})])
    monkeypatch.setattr(gnani_common.httpx, "post", lambda *a, **k: next(calls))
    assert gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings()).transcript == "ok"


def test_persistent_429_raises_rate_limited(monkeypatch):
    monkeypatch.setattr(gnani_common.httpx, "post",
                        lambda *a, **k: resp(429, {"detail": {"error_code": "RATE_LIMITED", "message": "m"}}))
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings())
    assert e.value.kind == "rate_limited"


def test_timeout_maps_to_safe_error(monkeypatch):
    def boom(*a, **k):
        raise httpx.ReadTimeout("t")

    monkeypatch.setattr(gnani_common.httpx, "post", boom)
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings())
    assert e.value.kind == "timeout"


def test_error_never_contains_api_key(monkeypatch):
    monkeypatch.setattr(gnani_common.httpx, "post",
                        lambda *a, **k: resp(401, {"detail": {"error_code": "INVALID_API_KEY", "message": "bad"}}))
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings())
    assert "SECRET-KEY-123" not in str(e.value) and e.value.kind == "auth"


def test_missing_key_fails_before_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network must not be called")

    monkeypatch.setattr(gnani_common.httpx, "post", boom)
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_stt.transcribe(b"x", "a.wav", "hi-IN", settings=make_settings(key=""))
    assert e.value.kind == "auth"


def test_tts_returns_audio_bytes_and_sends_voice_model(monkeypatch):
    seen = {}

    def fake_post(url, headers, timeout, json):
        seen.update(json)
        return resp(200, content=b"RIFFwav")

    monkeypatch.setattr(gnani_common.httpx, "post", fake_post)
    assert gnani_tts.synthesize("नमस्कार", "mr-IN", settings=make_settings()) == b"RIFFwav"
    assert seen["model"] == "timbre-v3.0" and seen["voice"] == "Shivani" and seen["language"] == "mr-IN"


def test_tts_rejects_empty_text():
    with pytest.raises(gnani_common.GnaniError):
        gnani_tts.synthesize("  ", "mr-IN", settings=make_settings())
