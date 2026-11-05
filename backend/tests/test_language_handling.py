"""'पंधरा → 15': next to each field, the words as heard and what they were turned into, shown only when the
language handling actually converted something."""
import pytest

from backend.tests.test_api import ME1, make, new_session, post_text


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch)[0]


def conversions(state, key="fields"):
    return {f["label"]: (f["heard"], f["understood_as"]) for f in state[key] if f["heard"]}


def run(client, text, language="mr"):
    sid = new_session(client, language)
    return sid, post_text(client, sid, text).json()["state"]


def test_the_two_examples_from_the_brief_number_words_and_clock_words(client):
    _, s = run(client, ME1)
    c = conversions(s)
    assert c["Reported time"] == ("साडेदहा वाजता", "10:30 AM")
    assert c["Pressure"] == ("पन्नास", "50")
    # the corrected-away value keeps its own conversion in the history list
    assert conversions(s, "history")["Pressure"] == ("पंधरा", "15")


def test_nothing_is_shown_when_nothing_was_converted(client):
    _, s = run(client, ME1)
    labels = {f["label"]: f for f in s["fields"]}
    assert labels["Asset"]["heard"] is None  # "P-12" -> "P-12" is not a conversion
    assert labels["Vibration"]["heard"] is None  # "vibration" -> "Vibration"
    assert "Asset" not in conversions(s)


@pytest.mark.parametrize("text,label,heard,understood", [
    ("पी ट्वेल्व stopped at ten thirty AM", "Asset", "पी ट्वेल्व", "P-12"),
    ("पी ट्वेल्व stopped at ten thirty AM", "Reported time", "ten thirty AM", "10:30 AM"),
    ("P-12 stopped at ten thirty PM", "Reported time", "ten thirty PM", "10:30 PM"),
    ("P-12 pressure two point five bar", "Pressure", "two point five bar", "2.5 bar"),
    ("सकाळी साडे अकरा वाजता P-12 बंद, pressure एकशे वीस bar", "Pressure", "एकशे वीस bar", "120 bar"),
    ("सकाळी साडे अकरा वाजता P-12 बंद, pressure एकशे वीस bar", "Reported time", "साडे अकरा वाजता", "11:30 AM"),
    ("P-12 पंप से धुआं निकल रहा है", "Smoke", "धुआं", "Smoke"),
    ("P-12 बंद पडला आहे", "Stopped", "बंद पडला", "Stopped"),
    ("P-12 smoke नाही", "Smoke", "smoke नाही", "Smoke: not present"),
])
def test_each_kind_of_field_shows_what_the_words_became(client, text, label, heard, understood):
    _, s = run(client, text)
    row = next(f for f in s["fields"] + s["history"] if f["label"] == label)
    assert (row["heard"], row["understood_as"]) == (heard, understood)


@pytest.mark.parametrize("text,label", [
    ("P-12 stopped at ten thirty PM", "Asset"),  # "P-12" -> "P-12"
    ("P-12 stopped at ten thirty PM", "Stopped"),  # "stopped" -> "Stopped" (same word)
    ("P-12 vibration", "Vibration"),
    ("C-04 compressor trip हो गया", "Asset"),  # the ID was spoken next to its alias: still nothing converted
])
def test_an_identical_word_is_not_shown_as_a_conversion(client, text, label):
    _, s = run(client, text, "en")
    row = next(f for f in s["fields"] if f["label"] == label)
    assert row["heard"] is None and row["understood_as"] is None


def test_a_tapped_value_has_no_spoken_words_so_no_conversion(client):
    sid, s = run(client, "त्यातून धूर येत आहे.")
    q = s["question"]
    s = client.post(f"/api/sessions/{sid}/choose", json={"issue_id": q["issue_id"], "choice": "P-21"}).json()
    asset = next(f for f in s["fields"] if f["label"] == "Asset")
    assert asset["origin"] != "speech" and asset["heard"] is None and asset["understood_as"] is None


def test_a_stated_cause_is_never_converted_it_is_kept_as_said(client):
    _, s = run(client, "P-12 stopped, cause belt slipped, pressure two point five bar", "en")
    cause = next(f for f in s["fields"] if f["label"] == "Cause")
    assert cause["heard"] is None and cause["value"] == "belt slipped (as reported)"  # and the pressure stayed out of it


def test_the_conversion_never_shows_a_value_that_differs_from_the_displayed_one(client):
    """The line next to a field must agree with the value shown on that field."""
    _, s = run(client, ME1)
    for f in s["fields"]:
        if f["heard"] and f["label"] in ("Reported time", "Pressure"):
            assert f["understood_as"].split()[0] in f["value"], f
