"""Gaps closed on 2026-11-04: spoken decimals, time corrections, unreadable numbers, dropped
corrected values, and the repeated-question cap."""
import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.normaliser import Analyser, analyse, default_lexicon
from backend.app.domain.schemas import IssueType
from backend.app.services.pipeline import MAX_ATTEMPTS, Pipeline
from backend.app.storage.store import Store, make_engine
from backend.tests.helpers import asking, blockers, review, settle  # noqa: F401


@pytest.fixture
def env():
    store = Store(make_engine())
    return Pipeline(store, load_catalogue(), "en"), store


# ---------------------------------------------------------------- decimals

@pytest.mark.parametrize("text,value", [
    ("pressure two point five bar", 2.5), ("pressure zero point seven five bar", 0.75),
    ("pressure three and a half bar", 3.5), ("pressure साडे तीन bar", 3.5), ("pressure सव्वा दोन bar", 2.25),
    ("pressure पावणे चार bar", 3.75), ("pressure डेढ़ bar", 1.5), ("pressure अडीच bar", 2.5),
    ("pressure 2.5 bar", 2.5),
])
def test_spoken_decimals(text, value):
    q = analyse(text).quantities
    assert [x.number.value for x in q] == [value] and q[0].unit.canonical == "bar"


def test_decimal_words_do_not_steal_clock_times():
    a = analyse("सकाळी साडे दहा वाजता P-12 बंद झाला")
    assert [t.hhmm for t in a.times] == ["10:30"] and a.quantities == []


# ---------------------------------------------------------------- time corrections

def test_time_correction_with_explicit_ampm_is_detected():
    a = analyse("stopped at ten thirty AM, no, ten forty AM")
    assert [t.hhmm for t in a.times] == ["10:30", "10:40"]
    assert (a.time_corrections[0].old.hhmm, a.time_corrections[0].new.hhmm) == ("10:30", "10:40")


def test_marker_before_non_time_is_not_a_time_correction():
    assert analyse("stopped at ten thirty AM, no vibration").time_corrections == []


def test_time_correction_in_pipeline_keeps_history_and_reads_back(env):
    p, store = env
    sid = p.start()
    r = p.submit_turn(sid, "P-12 stopped at ten thirty AM, no, ten forty AM.")
    times = [c for c in r.draft.candidates if c.field_path == "time"]
    assert [(c.normalised_value, c.status.value) for c in times] == [("10:30", "superseded"), ("10:40", "proposed")]
    assert asking(r) is None
    assert "Time: 10:40 AM (corrected from 10:30 AM)" in review(p, sid).readback


def test_corrected_time_without_ampm_asks_instead_of_inheriting(env):
    p, _ = env
    sid = p.start()
    r = p.submit_turn(sid, "P-12 stopped at ten thirty AM, no, ten forty.")
    assert r.question.issue_type == IssueType.AMBIGUOUS_TIME


# ---------------------------------------------------------------- unreadable number

def test_unit_after_unreadable_word_asks_for_the_value(env):
    p, store = env
    sid = p.start()
    r = p.submit_turn(sid, "M-07 is hot, temperature फलाणा degree.")
    assert r.question.issue_type == IssueType.MISSING_VALUE
    assert not [c for c in r.draft.candidates if c.field_path == "measurement.temperature" and c.normalised_value]
    r = p.answer(sid, "eighty five")
    assert r.understood and r.question.issue_type == IssueType.AMBIGUOUS_UNIT
    r = p.answer(sid, "celsius")
    assert asking(r) is None
    assert "Temperature 85 °C." in review(p, sid).readback


def test_unreadable_number_can_be_marked_unknown_and_saved(env):
    p, _ = env
    sid = p.start()
    p.submit_turn(sid, "M-07 is hot, temperature फलाणा degree.")
    r = p.answer(sid, "I don't know")
    assert r.understood and asking(r) is None
    rev = review(p, sid)
    assert "Temperature value unknown." in rev.readback
    wo = p.confirm_and_save(sid, rev.revision, "k1")
    assert wo.payload["measurements"][0]["value"] is None
    assert wo.payload["measurements"][0]["value_status"] == "unknown"


@pytest.mark.parametrize("text", [
    "pressure in PSI is high", "the reading in bar", "temperature in degrees celsius is normal",
    "pressure PSI", "it is at 50 PSI", "temperature 80 degree celsius",
])
def test_no_false_missing_value(text):
    a = Analyser(text, default_lexicon())
    a.run()
    assert a.orphan_units() == []


# ---------------------------------------------------------------- dropped corrected value

def test_correction_whose_old_value_was_not_heard_is_flagged_not_hidden(env):
    p, _ = env
    sid = p.start()
    r = p.submit_turn(sid, "P-12 बंद आहे. pressure नाही, पन्नास PSI होतं.")
    assert asking(r) is None  # non-blocking
    assert any(i.type == IssueType.POSSIBLE_DROPPED_VALUE and not i.blocking for i in r.draft.issues)
    rev = review(p, sid)
    assert "earlier value was not transcribed" in rev.readback
    assert rev.payload["measurements"][0]["earlier_value_not_heard"] is True


def test_normal_correction_is_not_flagged_as_dropped():
    a = analyse("pressure fifteen, no, fifty PSI")
    assert a.lone_corrections == [] and len(a.corrections) == 1


# ---------------------------------------------------------------- repeated-question cap

def test_attempt_counter_offers_fallback_after_three_misunderstood_answers(env):
    p, store = env
    sid = p.start()
    r = p.submit_turn(sid, "P-12 stopped, pressure 40.")
    assert r.question.issue_type == IssueType.MISSING_UNIT
    for n in range(1, MAX_ATTEMPTS + 1):
        r = p.answer(sid, "hmm what")
        assert not r.understood and r.attempts == n and r.fallback_offered == (n >= MAX_ATTEMPTS)
    r = p.choose(sid, r.question.issue_id, "unknown")  # the selectable fallback still works
    assert asking(r) is None


def test_attempts_do_not_change_the_draft(env):
    p, store = env
    sid = p.start()
    p.submit_turn(sid, "P-12 stopped, pressure 40.")
    before = store.draft(sid)
    p.answer(sid, "hmm what")
    assert store.draft(sid) == before


# ---------------------------------------------------------------- hundreds / unread number parts

@pytest.mark.parametrize("text,value", [
    ("pressure एकशे वीस PSI", 120), ("pressure दोनशे PSI", 200), ("pressure दीडशे PSI", 150),
    ("pressure डेढ़ सौ bar", 150), ("pressure साढ़े तीन सौ bar", 350), ("pressure ढाई हज़ार PSI", 2500),
    ("pressure एक सौ बीस bar", 120),
])
def test_hundreds_are_not_read_too_small(text, value):
    q = analyse(text).quantities
    assert [x.number.value for x in q] == [value]


def test_unknown_hundreds_word_is_never_silently_dropped(env):
    p, _ = env
    sid = p.start()
    r = p.submit_turn(sid, "P-12 बंद आहे, pressure फलाणाशे वीस PSI.")  # फलाणाशे is not in the lexicon
    assert r.question.issue_type == IssueType.MISSING_VALUE
    assert not [c for c in r.draft.candidates if c.normalised_value == 20]
