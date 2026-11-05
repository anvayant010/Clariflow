"""A second Gnani key (a teammate's own registration) is used only when the first runs out of credit (HTTP 402)."""
import dataclasses

import httpx
import pytest

from backend.app.adapters import gnani_common, gnani_stt, gnani_tts
from backend.app.config import Settings, get_settings

KEY1, KEY2 = "KEY-ONE-SECRET-111", "KEY-TWO-SECRET-222"


def reply(status, body=None, content=b""):
    return httpx.Response(status, json=body, content=None if body is not None else content,
                          request=httpx.Request("POST", "https://x.test"))


class Fake:
    """Stands in for httpx.post: answers per key, remembers which key each call used."""

    def __init__(self, **by_key):
        self.by_key, self.used = by_key, []

    def __call__(self, url, headers=None, **kw):
        key = headers["X-API-Key-ID"]
        self.used.append(key)
        ans = self.by_key[key]
        return ans.pop(0) if isinstance(ans, list) else ans


@pytest.fixture(autouse=True)
def clean_state():
    gnani_common._OUT_OF_CREDIT.clear()
    yield
    gnani_common._OUT_OF_CREDIT.clear()


def install(monkeypatch, fake):
    monkeypatch.setattr(gnani_common.httpx, "post", fake)
    monkeypatch.setattr(gnani_common.time, "sleep", lambda s: None)


def post(**kw):
    return gnani_common.post("https://x.test", KEY1, fallback_key=KEY2, **kw)


def test_the_first_key_is_used_while_it_has_credit(monkeypatch):
    fake = Fake(**{KEY1: reply(200, {"ok": 1}), KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    assert post().json() == {"ok": 1}
    assert fake.used == [KEY1]


def test_out_of_credit_repeats_the_call_once_with_the_second_key(monkeypatch):
    fake = Fake(**{KEY1: reply(402, {"detail": {"error_code": "insufficient_credit", "message": "no credit"}}), KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    assert post().json() == {"ok": 2}
    assert fake.used == [KEY1, KEY2]


def test_after_the_switch_the_empty_key_is_not_tried_again(monkeypatch):
    fake = Fake(**{KEY1: reply(402, {"message": "no credit"}), KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    post()
    post()
    post()
    assert fake.used == [KEY1, KEY2, KEY2, KEY2]  # one wasted call on the empty key, then straight to the second


def test_the_first_key_is_tried_again_after_an_hour_in_case_credit_was_added(monkeypatch):
    fake = Fake(**{KEY1: [reply(402, {"message": "no credit"}), reply(200, {"ok": 1})], KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    clock = [1000.0]
    monkeypatch.setattr(gnani_common.time, "monotonic", lambda: clock[0])
    assert post().json() == {"ok": 2}
    clock[0] += gnani_common.RETRY_AFTER_S - 1
    assert post().json() == {"ok": 2}  # still inside the hour: second key
    clock[0] += 2
    assert post().json() == {"ok": 1}  # an hour later: the first key again


def test_both_keys_out_of_credit_raises_a_safe_error(monkeypatch):
    fake = Fake(**{KEY1: reply(402, {"message": "no credit"}), KEY2: reply(402, {"message": "no credit"})})
    install(monkeypatch, fake)
    with pytest.raises(gnani_common.GnaniError) as e:
        post()
    assert e.value.kind == "insufficient_credit" and e.value.status == 402
    assert KEY1 not in str(e.value) and KEY2 not in str(e.value)


@pytest.mark.parametrize("status,kind", [(401, "auth"), (403, "scope_not_allowed"), (400, "bad_request"), (503, "unavailable")])
def test_other_errors_never_switch_keys(monkeypatch, status, kind):
    fake = Fake(**{KEY1: reply(status, {"message": "x"}), KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    with pytest.raises(gnani_common.GnaniError) as e:
        post()
    assert e.value.kind == kind
    assert fake.used == [KEY1]  # the second key was never used: this is not a credit problem
    assert not gnani_common._OUT_OF_CREDIT


def test_a_rate_limit_is_waited_out_on_the_same_key(monkeypatch):
    fake = Fake(**{KEY1: [reply(429, {"message": "slow down"}), reply(200, {"ok": 1})], KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    assert post().json() == {"ok": 1}
    assert fake.used == [KEY1, KEY1]


def test_with_only_one_key_a_402_is_raised_and_nothing_is_remembered(monkeypatch):
    fake = Fake(**{KEY1: reply(402, {"message": "no credit"})})
    install(monkeypatch, fake)
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_common.post("https://x.test", KEY1)
    assert e.value.kind == "insufficient_credit"
    assert not gnani_common._OUT_OF_CREDIT


def test_only_the_second_key_set_still_works(monkeypatch):
    fake = Fake(**{KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    assert gnani_common.post("https://x.test", "", fallback_key=KEY2).json() == {"ok": 2}


def test_no_key_at_all_is_an_auth_error(monkeypatch):
    install(monkeypatch, Fake())
    with pytest.raises(gnani_common.GnaniError) as e:
        gnani_common.post("https://x.test", "", fallback_key="")
    assert e.value.kind == "auth"


def test_the_keys_are_never_written_to_the_log(monkeypatch, caplog):
    fake = Fake(**{KEY1: reply(402, {"message": "no credit"}), KEY2: reply(200, {"ok": 2})})
    install(monkeypatch, fake)
    with caplog.at_level("DEBUG", logger="clariflow"):
        post()
    assert caplog.records and all(KEY1 not in r.getMessage() and KEY2 not in r.getMessage() for r in caplog.records)
    assert any("#1" in r.getMessage() for r in caplog.records)  # says which key by position only


def s(**over) -> Settings:
    return dataclasses.replace(get_settings(), gnani_api_key_id=KEY1, gnani_api_key_id_2=KEY2, **over)


def test_text_to_speech_and_speech_recognition_both_use_the_fallback(monkeypatch):
    fake = Fake(**{KEY1: reply(402, {"message": "no credit"}), KEY2: [reply(200, content=b"RIFFaudio"), reply(200, {"transcript": "hi", "request_id": "r"})]})
    install(monkeypatch, fake)
    assert gnani_tts.synthesize("hello", "en-IN", settings=s()) == b"RIFFaudio"
    assert gnani_stt.transcribe(b"x", "a.wav", "en-IN", settings=s()).transcript == "hi"


def test_the_settings_print_never_shows_a_key(monkeypatch):
    text = repr(s())
    assert KEY1 not in text and KEY2 not in text and "second_key_set=True" in text


def test_the_second_key_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY_ID_2", "from-env-key")
    assert get_settings().gnani_api_key_id_2 == "from-env-key"
    monkeypatch.delenv("GNANI_API_KEY_ID_2")
    assert get_settings().gnani_api_key_id_2 == ""
