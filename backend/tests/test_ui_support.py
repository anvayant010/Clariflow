"""Tests for the code the UI relies on (speech glue and draft presentation); no network calls."""
import io
import json
import wave

import pytest

from backend.app.adapters.gnani_stt import SttResult
from backend.app.domain.assets import load_catalogue
from backend.app.services import speech
from backend.app.services.pipeline import Pipeline
from backend.app.services.view import draft_rows, history_rows, mark
from backend.app.storage.store import Store, make_engine

ME1 = "P-12 pump बंद पडला आहे. सकाळी साडेदहा वाजता vibration खूप होतं. pressure पंधरा नाही, पन्नास होतं."


def wav_bytes(seconds: float, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def test_stt_context_uses_catalogue_ids_and_is_json():
    ctx = speech.stt_context(load_catalogue())
    terms = json.loads(ctx["keyterms"])
    assert "P-12" in terms and "PSI" in terms and len(terms) <= 200
    assert "topic" in ctx and len(ctx["topic"]) <= 1600


def test_validate_clip_accepts_short_wav_and_rejects_bad_input():
    assert speech.validate_clip(wav_bytes(2), "a.wav") in ("audio/wav", "audio/x-wav", "audio/vnd.wave")
    for bad, name in [(wav_bytes(31), "long.wav"), (b"", "e.wav"), (b"not a wav", "x.wav"), (b"123", "x.txt"),
                      (b"1" * (speech.MAX_CLIP_BYTES + 1), "big.m4a")]:
        with pytest.raises(speech.ClipError):
            speech.validate_clip(bad, name)


def test_transcriber_validates_before_any_provider_call():
    called = []
    t = speech.make_transcriber(load_catalogue())
    import backend.app.services.speech as sp
    orig = sp.gnani_stt.transcribe
    sp.gnani_stt.transcribe = lambda *a, **k: called.append(1)
    try:
        with pytest.raises(speech.ClipError):
            t(wav_bytes(40), "long.wav")
    finally:
        sp.gnani_stt.transcribe = orig
    assert called == []


def test_audio_roundtrip_and_path_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "DATA_DIR", tmp_path)
    ref = speech.save_audio("sess", b"abc", "clip.wav")
    assert speech.load_audio(ref) == b"abc"
    assert speech.load_audio("../../etc/passwd") is None
    assert speech.load_audio(None) is None


def test_tts_is_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "DATA_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(speech.gnani_tts, "synthesize", lambda text, lang, settings=None: calls.append(text) or b"WAV")
    assert speech.speak("which asset?", "en") == b"WAV"
    assert speech.speak("which asset?", "en") == b"WAV"
    assert len(calls) == 1


def test_mark_escapes_html():
    assert mark("a <b> c", 2, 5) == "a <mark>&lt;b&gt;</mark> c"
    assert mark("x<y", None, None) == "x&lt;y"


@pytest.fixture
def env():
    store = Store(make_engine())
    cat = load_catalogue()
    return Pipeline(store, cat, "mr"), store, cat


def test_draft_rows_show_correction_and_evidence_with_audio(env):
    p, store, cat = env
    sid = p.start()
    p.submit_turn(sid, ME1, audio_ref="audio/x/clip.wav")
    d, segs = store.draft(sid), store.segments(sid)
    rows = {r.label: r for r in draft_rows(d, cat, segs)}
    assert rows["Asset"].value.startswith("P-12")
    assert "corrected from 15" in rows["Pressure"].value and rows["Pressure"].state == "needs_answer"
    rec = rows["Pressure"].receipts[0]
    assert rec.audio_ref == "audio/x/clip.wav" and "<mark>" in rec.marked_html
    assert any(h.label == "Pressure" and h.value.startswith("15") for h in history_rows(d, cat, segs))


def test_typed_answer_is_labelled_not_speech(env):
    p, store, cat = env
    sid = p.start()
    r = p.submit_turn(sid, ME1)
    p.choose(sid, r.question.issue_id, "PSI")
    rows = {r.label: r for r in draft_rows(store.draft(sid), cat, store.segments(sid))}
    assert rows["Pressure"].value.startswith("50 PSI")


def test_answer_audio_uses_transcriber_and_stores_audio_ref(env):
    p, store, cat = env
    sid = p.start()
    p.submit_turn(sid, ME1)
    stt = lambda audio, name: SttResult(transcript="PSI", request_id="r", model="prisma-v3.0",
                                        language_code_sent="x", format_sent="codemix")
    r = p.answer_audio(sid, b"a", "a.wav", stt, audio_ref="audio/s/a.wav")
    assert r.understood and r.question is None or r.question.issue_type.value != "missing_unit"
    assert list(store.segments(sid).values())[-1].audio_ref == "audio/s/a.wav"


def test_answer_audio_stt_failure_leaves_draft_unchanged(env):
    p, store, cat = env
    sid = p.start()
    p.submit_turn(sid, ME1)
    before = store.draft(sid)
    empty = lambda audio, name: SttResult(transcript=" ", request_id="r", model="m",
                                          language_code_sent="x", format_sent="f")
    r = p.answer_audio(sid, b"a", "a.wav", empty)
    assert r.error == "no speech recognised" and store.draft(sid) == before
