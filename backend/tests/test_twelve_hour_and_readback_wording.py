"""12-hour clock for everything a person reads or hears; the read-back says nothing about "simulated" (it is read
aloud: the routing box under it says so); no "not mentioned: immediate action" note (it cannot be added from the screen)."""
import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.schemas import SegmentSource
from backend.app.services import spoken, workorder
from backend.app.services.timefmt import clock12
from backend.app.services.view import draft_rows
from backend.tests.helpers import review, settle
from backend.tests.test_api import make, new_session, post_text, settle_urgency
from backend.app.services.pipeline import Pipeline
from backend.app.storage.store import Store, make_engine

CATALOGUE = load_catalogue()


def pipe(language="en"):
    store = Store(make_engine())
    return Pipeline(store, CATALOGUE, language), store, store.create_session(language)


@pytest.mark.parametrize("value,shown", [
    ("14:00", "2:00 PM"), ("00:30", "12:30 AM"), ("12:00", "12:00 PM"), ("12:15", "12:15 PM"), ("09:05", "9:05 AM"),
    ("10:30", "10:30 AM"), ("23:59", "11:59 PM"), ("00:00", "12:00 AM"), ("13:00", "1:00 PM"),
])
def test_the_12_hour_clock(value, shown):
    assert clock12(value) == shown


@pytest.mark.parametrize("junk", [None, "", "x", "25:00", "12:60", "7", "ten thirty"])
def test_anything_that_is_not_a_time_is_left_alone(junk):
    assert clock12(junk) == ("" if junk is None else junk)


@pytest.mark.parametrize("language,text,expected", [
    ("en", "B-02 stopped at two o'clock in the afternoon, smoke", "Time: 2:00 PM."),
    ("en", "B-02 stopped at ten thirty AM, smoke", "Time: 10:30 AM."),
    ("mr", "B-02 बंद पडला, सकाळी साडेदहा वाजता", "वेळ: 10:30 AM."),
    ("hi", "B-02 बंद हो गया, दोपहर दो बजे", "समय: 2:00 PM।"),
])
def test_the_readback_shows_a_12_hour_time_in_every_language(language, text, expected):
    p, store, sid = pipe(language)
    p.submit_turn(sid, text, SegmentSource.FIXTURE)
    settle(p, sid)
    assert expected in p.review(sid).readback
    assert "14:00" not in p.review(sid).readback


def test_a_corrected_time_shows_both_times_in_12_hour_form():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped at ten thirty AM, no, ten forty AM", SegmentSource.FIXTURE)
    assert "Time: 10:40 AM (corrected from 10:30 AM)." in review(p, sid).readback


def test_the_stored_value_stays_24_hour_so_nothing_downstream_changes():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped at ten thirty PM, smoke", SegmentSource.FIXTURE)
    assert review(p, sid).payload["reported_incident_time"]["value"] == "22:30"


def test_the_checklist_row_and_the_heard_line_use_the_12_hour_form():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped at ten thirty PM, smoke", SegmentSource.FIXTURE)
    row = next(r for r in draft_rows(store.draft(sid), CATALOGUE, store.segments(sid)) if r.label == "Reported time")
    assert row.value == "10:30 PM" and (row.heard, row.understood_as) == ("ten thirty PM", "10:30 PM")


@pytest.mark.parametrize("language,fragments", [
    ("en", ["two o'clock P M"]),
    ("mr", ["दोन वाजता पी एम"]),
    ("hi", ["दो बजे पी एम"]),
])
def test_the_voice_says_the_time_with_am_or_pm_not_as_a_24_hour_number(language, fragments):
    said = spoken.to_spoken("Time: 2:00 PM.", language)
    for f in fragments:
        assert f in said, said
    assert "fourteen" not in said and "चौदा" not in said and "चौदह" not in said
    assert "ए एम" in spoken.to_spoken("9:05 AM", "mr") or "A M" in spoken.to_spoken("9:05 AM", "en")


def test_a_time_without_am_pm_is_still_spoken_as_before():
    assert spoken.to_spoken("10:30", "en") == "ten thirty"  # nothing else in the voice changed


# ---------------------------------------------------------------- the read-back is read aloud: no "simulated" in it

@pytest.mark.parametrize("language", ["en", "mr", "hi"])
def test_the_readback_does_not_say_simulated_but_still_says_who_would_be_told(language):
    p, store, sid = pipe(language)
    p.submit_turn(sid, "B-02 conveyor belt stopped, smoke is coming", SegmentSource.FIXTURE)
    settle(p, sid, "stop_work")
    text = p.review(sid).readback
    for word in ("simulated", "नमुना", "नमूना", "nothing is sent", "काहीही पाठवलं", "कुछ भेजा"):
        assert word not in text, (language, text)
    assert {"en": "Would notify: Maintenance head, Production supervisor.", "mr": "कळवलं जाईल: देखभाल प्रमुख, उत्पादन सुपरवायझर.",
            "hi": "सूचित किया जाएगा: रखरखाव प्रमुख, उत्पादन सुपरवाइज़र।"}[language] in text


def test_the_screen_still_says_it_is_simulated_in_the_routing_data(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "en")
    s = settle_urgency(client, sid, post_text(client, sid, "B-02 stopped, smoke").json()["state"], "today")
    assert s["review"]["routing"]["simulated"] is True  # the box under the read-back, the card rows and the rules table say it
    assert "simulated" not in s["review"]["readback"].lower()
    assert s["review"]["payload"]["routing"]["simulated"] is True


# ---------------------------------------------------------------- no note about immediate action

def test_there_is_no_not_mentioned_note_for_immediate_action_but_time_and_cause_remain(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "en")
    s = settle_urgency(client, sid, post_text(client, sid, "B-02 stopped, smoke").json()["state"])
    noted = {f for n in s["notes"] if n["type"] == "optional_detail" for f in n["fields"]}
    assert noted == {"time", "cause"}  # these can be added from the screen; immediate action cannot


def test_immediate_action_is_still_recorded_when_it_is_said():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped, smoke, I turned it off", SegmentSource.FIXTURE)
    assert review(p, sid).payload["immediate_action"] == "turned_off"
