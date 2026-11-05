"""Localised read-back and the spoken (TTS-ready) form of text."""
import json
import re

import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.services import speech
from backend.app.services.pipeline import Pipeline
from backend.app.services.spoken import number_words, to_spoken
from backend.app.services.workorder import readback
from backend.app.storage.store import Store, make_engine
from backend.tests.helpers import review as settled_review

ME1 = "P-12 pump बंद पडला आहे. सकाळी साडेदहा वाजता vibration खूप होतं. pressure पंधरा नाही, पन्नास PSI होतं."
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def review(lang: str):
    p = Pipeline(Store(make_engine()), load_catalogue(), lang)
    sid = p.start()
    p.submit_turn(sid, ME1)
    return settled_review(p, sid)


@pytest.mark.parametrize("lang", ["en", "mr", "hi"])
def test_readback_in_every_language_states_the_same_facts(lang):
    rb = review(lang).readback
    for fact in ("P-12", "10:30", "50", "15"):
        assert fact in rb, (lang, rb)
    assert bool(DEVANAGARI.search(rb)) == (lang != "en")
    assert "{" not in rb  # no unfilled template slot


def test_readback_languages_differ_but_payload_is_identical():
    en, mr, hi = review("en"), review("mr"), review("hi")
    assert en.payload == mr.payload == hi.payload
    assert len({en.readback, mr.readback, hi.readback}) == 3


def test_every_template_key_exists_in_every_language():
    t = json.loads(open("backend/app/lexicon/readback.json", encoding="utf-8").read())["templates"]
    assert set(t["en"]) == set(t["mr"]) == set(t["hi"])


@pytest.mark.parametrize("n,lang,words", [
    (12, "mr", "बारा"), (85, "mr", "पंच्याऐंशी"), (120, "mr", "एकशे वीस"), (200, "mr", "दोनशे"),
    (50, "hi", "पचास"), (120, "hi", "एक सौ बीस"), (1500, "hi", "एक हजार पांच सौ"),
    (45, "en", "forty five"), (120, "en", "one hundred twenty"), (7, "en", "seven"),
])
def test_number_words(n, lang, words):
    assert number_words(n, lang) == words


def test_to_spoken_spells_ids_numbers_times_and_units():
    assert to_spoken("P-12", "mr") == "पी बारा"
    assert to_spoken("C-04", "mr") == "सी शून्य चार"
    assert to_spoken("P-12", "en") == "P twelve"
    assert to_spoken("Pressure 50 PSI.", "en") == "Pressure fifty P S I."
    assert to_spoken("तापमान 85 °C", "mr") == "तापमान पंच्याऐंशी डिग्री सेल्सिअस"
    assert to_spoken("pressure 2.5 bar", "en") == "pressure two point five bar"
    assert to_spoken("Time: 10:30.", "en") == "Time: ten thirty."
    assert to_spoken("वेळ: 23:00", "mr") == "वेळ: तेवीस वाजता"
    assert to_spoken("Time: 09:05", "en") == "Time: nine oh five"


def test_to_spoken_leaves_text_without_digits_alone():
    assert to_spoken("Which asset do you mean?", "en") == "Which asset do you mean?"
    assert to_spoken("हा रिपोर्ट कोणत्या असेटबद्दल आहे?", "mr") == "हा रिपोर्ट कोणत्या असेटबद्दल आहे?"
    assert to_spoken("number 123456", "en") == "number 123456"  # out of range: digits kept, never invented


def test_speak_sends_the_spoken_form_to_timbre(tmp_path, monkeypatch):
    monkeypatch.setattr(speech, "DATA_DIR", tmp_path)
    seen = []
    monkeypatch.setattr(speech.gnani_tts, "synthesize", lambda text, lang, settings=None: seen.append((text, lang)) or b"W")
    speech.speak("तुम्ही प्रेशर 50 म्हणालात.", "mr")
    assert seen == [("तुम्ही प्रेशर पन्नास म्हणालात.", "mr-IN")]


def test_readback_function_rejects_unknown_language():
    with pytest.raises(KeyError):
        readback({}, "xx")
