"""Deployment support: the visitor's address behind a host's proxy, the data folder, and the shipped question audio."""
import dataclasses

import pytest

from backend.app.config import get_settings
from backend.app.services import speech
from backend.tests.test_api import make


def visitor(client, **headers):
    r = client.get("/api/visitor", headers=headers)
    assert r.status_code == 200
    return r.json()["visitor"]


# ---- the visitor's address ------------------------------------------------------------------------------------

def test_without_a_proxy_the_forwarded_header_is_ignored(tmp_path, monkeypatch):
    """TRUSTED_PROXY_HOPS=0 (the local default): anyone can send X-Forwarded-For, so it must not matter."""
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=0)
    assert visitor(client) == visitor(client, **{"X-Forwarded-For": "9.9.9.9"}) == visitor(client, **{"X-Forwarded-For": "8.8.8.8"})


def test_one_proxy_uses_the_rightmost_address(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=1)
    a = visitor(client, **{"X-Forwarded-For": "203.0.113.7"})
    b = visitor(client, **{"X-Forwarded-For": "203.0.113.8"})
    assert a != b  # two visitors are two buckets, not one shared bucket
    assert a == visitor(client, **{"X-Forwarded-For": "203.0.113.7"})


def test_an_address_typed_by_the_visitor_cannot_dodge_the_limits(tmp_path, monkeypatch):
    """The visitor sends 'X-Forwarded-For: 1.1.1.1'; our proxy appends the real address on the right."""
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=1)
    real = visitor(client, **{"X-Forwarded-For": "203.0.113.7"})
    spoofed_a = visitor(client, **{"X-Forwarded-For": "1.1.1.1, 203.0.113.7"})
    spoofed_b = visitor(client, **{"X-Forwarded-For": "2.2.2.2, 203.0.113.7"})
    assert real == spoofed_a == spoofed_b


def test_two_proxies_skip_the_inner_one(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=2)
    a = visitor(client, **{"X-Forwarded-For": "203.0.113.7, 10.0.0.5"})
    b = visitor(client, **{"X-Forwarded-For": "203.0.113.8, 10.0.0.5"})
    assert a != b


def test_a_missing_short_or_malformed_header_falls_back_to_the_connection_address(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=2)
    direct = visitor(client)
    assert visitor(client, **{"X-Forwarded-For": "203.0.113.7"}) == direct  # fewer entries than proxies
    assert visitor(client, **{"X-Forwarded-For": "not-an-ip, also-not"}) == direct
    assert visitor(client, **{"X-Forwarded-For": ", ,"}) == direct


def test_the_visitor_value_is_a_short_hash_not_an_address(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=1)
    v = visitor(client, **{"X-Forwarded-For": "203.0.113.7"})
    assert len(v) == 16 and "203" not in v and "." not in v


def test_the_per_visitor_limit_is_per_address_behind_a_proxy(tmp_path, monkeypatch):
    """One visitor using up their reports must not block a different visitor (the bug this setting exists to prevent)."""
    client, _ = make(tmp_path, monkeypatch, trusted_proxy_hops=1, ip_sessions_per_day=2)
    one = {"X-Forwarded-For": "203.0.113.7"}
    other = {"X-Forwarded-For": "203.0.113.99"}
    for _ in range(2):
        assert client.post("/api/sessions", json={"language": "en"}, headers=one).status_code == 201
    assert client.post("/api/sessions", json={"language": "en"}, headers=one).status_code == 429
    assert client.post("/api/sessions", json={"language": "en"}, headers=other).status_code == 201


def test_the_setting_is_read_from_the_environment_and_never_negative(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    assert get_settings().trusted_proxy_hops == 1
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "-3")
    assert get_settings().trusted_proxy_hops == 0
    monkeypatch.delenv("TRUSTED_PROXY_HOPS")
    assert get_settings().trusted_proxy_hops == 0


# ---- shipped question audio ------------------------------------------------------------------------------------

def test_a_shipped_question_clip_is_used_without_calling_timbre(tmp_path, monkeypatch):
    s = dataclasses.replace(get_settings(), gnani_api_key_id="test-key-not-real")
    monkeypatch.setattr(speech, "DATA_DIR", tmp_path / "data")
    seed = tmp_path / "seed"
    seed.mkdir()
    monkeypatch.setattr(speech, "SEED_TTS_DIR", seed)
    _, path = speech._cache_path("Which pump?", "en", s)
    (seed / path.name).write_bytes(b"RIFFseeded")
    monkeypatch.setattr(speech.gnani_tts, "synthesize", lambda *a, **k: pytest.fail("a credit was spent on a shipped clip"))
    assert speech.is_cached("Which pump?", "en", s)
    assert speech.speak("Which pump?", "en", s) == b"RIFFseeded"


def test_without_a_shipped_clip_timbre_is_called_once_and_then_the_disk_serves_it(tmp_path, monkeypatch):
    s = dataclasses.replace(get_settings(), gnani_api_key_id="test-key-not-real")
    monkeypatch.setattr(speech, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(speech, "SEED_TTS_DIR", tmp_path / "nothing")
    calls = []
    monkeypatch.setattr(speech.gnani_tts, "synthesize", lambda text, lang, settings=None: calls.append(text) or b"RIFFnew")
    assert not speech.is_cached("Which pump?", "en", s)
    assert speech.speak("Which pump?", "en", s) == b"RIFFnew"
    assert speech.speak("Which pump?", "en", s) == b"RIFFnew"
    assert calls == ["Which pump?"] and speech.is_cached("Which pump?", "en", s)


def test_the_data_folder_can_be_set_from_the_environment():
    """Checked in a fresh process: reloading the module inside the test run would redefine its classes for every other test."""
    import os
    import subprocess
    import sys
    code = "from backend.app.services import speech; print(speech.DATA_DIR.as_posix())"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**os.environ, "DATA_DIR": "/srv/clariflow-data"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("/srv/clariflow-data")
    unset = {k: v for k, v in os.environ.items() if k != "DATA_DIR"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=unset)
    assert out.stdout.strip().endswith("/data")
