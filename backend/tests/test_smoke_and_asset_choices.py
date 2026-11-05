"""Found in the first real browser try (2026-11-04): "smoke is coming out" produced no symptom, and the
"which equipment?" question gave nothing to tap."""
import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.schemas import SegmentSource
from backend.app.services.pipeline import Pipeline
from backend.app.services.view import question_view
from backend.app.domain.issues import plan_question
from backend.app.storage.store import Store, make_engine
from backend.tests.helpers import asking, blockers, review, settle  # noqa: F401

CATALOGUE = load_catalogue()


def pipe(language="en"):
    store = Store(make_engine())
    return Pipeline(store, CATALOGUE, language), store


def symptoms(store, sid):
    return {c.field_path: c.normalised_value for c in store.draft(sid).candidates if c.field_path.startswith("symptom.")}


@pytest.mark.parametrize("language,text", [
    ("en", "P-12 pump is making smoke"),
    ("mr", "P-12 पंप मधून धूर येत आहे."),
    ("hi", "P-12 पंप से धुआं निकल रहा है"),
    ("mr", "P-12 पंप मधून स्मोक येत आहे"),
])
def test_smoke_is_recorded_as_a_symptom_with_evidence(language, text):
    p, store = pipe(language)
    sid = store.create_session(language)
    p.submit_turn(sid, text, SegmentSource.FIXTURE)
    assert symptoms(store, sid).get("symptom.smoke") == "present"
    smoke = next(c for c in store.draft(sid).candidates if c.field_path == "symptom.smoke")
    assert smoke.evidence and smoke.evidence[0].quote  # tied to a quote, not invented


def test_negated_smoke_is_not_recorded_as_present():
    p, store = pipe("en")
    sid = store.create_session("en")
    p.submit_turn(sid, "P-12 pump has vibration but no smoke", SegmentSource.FIXTURE)
    assert symptoms(store, sid).get("symptom.smoke") != "present"


def test_unknown_equipment_question_offers_the_whole_plant_list_and_a_tap_answers_it():
    p, store = pipe("mr")
    sid = store.create_session("mr")
    p.submit_turn(sid, "त्यातून धूर येत आहे.", SegmentSource.FIXTURE)  # the exact transcript from the browser try
    draft = store.draft(sid)
    q = plan_question(draft, CATALOGUE, "mr")
    assert q.issue_type.value == "unknown_asset"
    view = question_view(q, draft, CATALOGUE, "mr")
    assert [c.value for c in view.choices] == [a.id for a in CATALOGUE]
    assert all(c.label.startswith(c.value) for c in view.choices)

    p.choose(sid, q.issue_id, "P-21")
    asset = next(c for c in store.draft(sid).candidates if c.field_path == "asset" and c.origin.value == "human_edit")
    assert asset.normalised_value == "P-21"
    assert not blockers(store.draft(sid))  # nothing else blocks; smoke is kept
    assert symptoms(store, sid).get("symptom.smoke") == "present"


def test_readback_names_smoke_in_each_language():
    for language, word in (("en", "smoke"), ("mr", "धूर"), ("hi", "धुआं")):
        p, store = pipe(language)
        sid = store.create_session(language)
        p.submit_turn(sid, {"en": "P-12 smoke", "mr": "P-12 धूर", "hi": "P-12 धुआं"}[language], SegmentSource.FIXTURE)
        assert word in review(p, sid).readback


# ---------------------------------------------------------------- read-back in every language, for every kind of draft

def test_readback_renders_in_all_languages_for_every_phrasing_case():
    """The saved record can be shown in any language, so no draft may break a template (KeyError, empty text,
    leftover '{placeholder}'), including drafts with blockers, unknowns, corrections and missing units."""
    import json
    from pathlib import Path

    from backend.app.services import workorder

    cases = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "cases" / "phrasings.json").read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 50
    for case in cases:
        p, store = pipe("en")
        sid = store.create_session("en")
        p.submit_turn(sid, case["text"], SegmentSource.FIXTURE)
        payload = workorder.build_payload(store.draft(sid), CATALOGUE)
        for language in ("mr", "hi", "en"):
            text = workorder.readback(payload, language)
            assert text.strip(), (case["id"], language)
            assert "{" not in text and "}" not in text, (case["id"], language, text)


# ---------------------------------------------------------------- found in the second browser try

from backend.app.domain.extractor import extract  # noqa: E402
from backend.app.domain.schemas import TranscriptSegment  # noqa: E402


def symptom_values(text):
    seg = TranscriptSegment(session_id="s", turn_index=0, text=text, source=SegmentSource.FIXTURE)
    return {c.field_path: c.normalised_value for c in extract(seg, CATALOGUE) if c.field_path.startswith("symptom.")}


@pytest.mark.parametrize("text,expected", [
    # the exact sentence from the browser: the "not" of "not working" must not negate the smoke
    ("C-04 Air Compressor not working, smoke is coming", {"symptom.stopped": "present", "symptom.smoke": "present"}),
    ("compressor not working and smoke is coming", {"symptom.stopped": "present", "symptom.smoke": "present"}),
    ("कंप्रेसर काम करत नाही, धूर येत आहे", {"symptom.stopped": "present", "symptom.smoke": "present"}),
    ("कंप्रेसर चालत नाही आणि धूर येतोय", {"symptom.stopped": "present", "symptom.smoke": "present"}),
    ("पंप काम नहीं कर रहा है, धुआं निकल रहा है", {"symptom.stopped": "present", "symptom.smoke": "present"}),
    # real negations still work
    ("no smoke", {"symptom.smoke": "absent"}),
    ("P-12 vibration, no smoke", {"symptom.vibration": "present", "symptom.smoke": "absent"}),
    ("smoke नाही", {"symptom.smoke": "absent"}),
    ("no leakage but water underneath", {"symptom.leakage": "absent", "symptom.water": "present"}),
])
def test_a_negator_stays_inside_its_own_clause(text, expected):
    assert symptom_values(text) == expected


def open_symptom_question(language="en"):
    p, store = pipe(language)
    sid = store.create_session(language)
    p.submit_turn(sid, "C-04 compressor", SegmentSource.FIXTURE)
    q = plan_question(store.draft(sid), CATALOGUE, language)
    assert q.issue_type.value == "missing_symptom"
    return p, store, sid, q


@pytest.mark.parametrize("language,answer", [("en", "smoke is coming out"), ("mr", "धूर येत आहे"), ("hi", "धुआं निकल रहा है")])
def test_what_did_you_see_can_be_answered_by_describing_it(language, answer):
    p, store, sid, _ = open_symptom_question(language)
    res = p.answer(sid, answer, SegmentSource.FIXTURE)
    assert res.understood and symptoms(store, sid).get("symptom.smoke") == "present"
    assert not blockers(store.draft(sid))


def test_an_answer_with_no_symptom_is_not_understood_and_changes_no_symptom():
    p, store, sid, q = open_symptom_question()
    res = p.answer(sid, "I don't know", SegmentSource.FIXTURE)
    assert not res.understood and res.attempts == 1
    assert plan_question(store.draft(sid), CATALOGUE, "en").issue_type.value == "missing_symptom"
    assert not [c for c in store.draft(sid).candidates if c.field_path.startswith("symptom.") and c.normalised_value == "present"]


def test_what_did_you_see_offers_symptoms_to_tap_and_a_tap_answers_it():
    p, store, sid, q = open_symptom_question("mr")
    view = question_view(q, store.draft(sid), CATALOGUE, "mr")
    values = [c.value for c in view.choices]
    assert "symptom.smoke=present" in values and "symptom.running=present" not in values
    assert all("=" not in c.label for c in view.choices)  # plain words, not codes
    p.choose(sid, q.issue_id, "symptom.smoke=present")
    smoke = next(c for c in store.draft(sid).candidates if c.field_path == "symptom.smoke" and c.origin.value == "human_edit")
    assert smoke.normalised_value == "present"
    assert not blockers(store.draft(sid))


def test_tapping_a_symptom_replaces_an_earlier_no_smoke_and_rejects_anything_else():
    from backend.app.domain.reducer import ReducerError

    p, store, sid, _ = open_symptom_question()
    p.submit_turn(sid, "no smoke", SegmentSource.FIXTURE)  # still no PRESENT symptom: the question stays open
    q = plan_question(store.draft(sid), CATALOGUE, "en")
    for bad in ("symptom.smoke=absent", "symptom.teleport=present", "asset=P-12", "symptom.running=present", "smoke"):
        with pytest.raises(ReducerError):
            p.choose(sid, q.issue_id, bad)
    p.choose(sid, q.issue_id, "symptom.smoke=present")
    smoke = [c for c in store.draft(sid).candidates if c.field_path == "symptom.smoke" and c.status.value != "superseded"]
    assert [c.normalised_value for c in smoke] == ["present"]
