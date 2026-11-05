"""Urgency question + SIMULATED routing (2026-11-04).

Urgency is the person's own answer (stated in the report, answered, or "not sure"): never inferred, never skipped,
asked last. Routing says who WOULD be told, from a visible rule file; nothing is ever sent.
"""
import json

import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.extractor import extract
from backend.app.domain.issues import next_blocker, plan_question
from backend.app.domain.reducer import ReducerError
from backend.app.domain.schemas import IssueType, SegmentSource, TranscriptSegment
from backend.app.domain.urgency import ANSWERS, LEVELS
from backend.app.services import routing, workorder
from backend.app.services.pipeline import MAX_ATTEMPTS, Pipeline
from backend.app.services.view import question_view
from backend.app.storage.store import Store, StoreError, make_engine
from backend.tests.helpers import blockers, settle
from backend.tests.test_api import make, new_session, post_text, settle_urgency

CATALOGUE = load_catalogue()
REPORT = "B-02 conveyor belt stopped, smoke is coming"  # says nothing about urgency


def pipe(language="en"):
    store = Store(make_engine())
    return Pipeline(store, CATALOGUE, language), store, store.create_session(language)


def stated(text):
    seg = TranscriptSegment(session_id="s", turn_index=0, text=text, source=SegmentSource.FIXTURE)
    return [(c.normalised_value, c.evidence[0].quote) for c in extract(seg, CATALOGUE) if c.field_path == "urgency"]


def urgency_of(store, sid):
    return [c for c in store.draft(sid).candidates if c.field_path == "urgency" and c.status.value != "superseded"]


# ---------------------------------------------------------------- stated in the report (explicit words only)

@pytest.mark.parametrize("text,level,quote", [
    ("P-12 pump emergency, smoke is coming", "emergency", "emergency"),
    ("P-12 पंप में इमरजेंसी है", "emergency", "इमरजेंसी"),
    ("P-12 पंपाला आणीबाणी आहे", "emergency", "आणीबाणी"),
    ("C-04 smoke, stop the line", "stop_work", "stop the line"),
    ("C-04 धुआं है, काम बंद करो", "stop_work", "काम बंद करो"),
    ("B-02 stopped, can wait", "can_wait", "can wait"),
    ("B-02 बंद आहे, घाई नाही", "can_wait", "घाई नाही"),
    ("B-02 noise, not urgent", "can_wait", "not urgent"),
    ("B-02 belt slipping, needs attention today", "today", "attention today"),
])
def test_an_urgency_the_speaker_states_is_captured_with_its_quote(text, level, quote):
    assert stated(text) == [(level, quote)]


@pytest.mark.parametrize("text", [
    "P-12 stopped today at ten thirty",   # "today" is a time here, not an urgency
    "B-02 conveyor belt is on fire",      # fire is something SEEN (a symptom); it never decides the urgency
    "पंपाला आग लागली",
    "urgent, P-12 smoke",                 # "urgent" does not say WHICH level
    "it is not an emergency, belt slipped",  # a negated level does not say what it IS
    "no emergency, vibration",
    "emergency but can wait",             # two different levels: left for the question
    "P-12 smoke and noise, vibration",    # symptoms alone never imply an urgency
    "P-12 पंप बंद आहे",
])
def test_nothing_is_taken_as_urgency_when_it_is_not_clearly_stated(text):
    assert stated(text) == []


def test_symptoms_never_decide_the_urgency_even_dangerous_sounding_ones():
    p, store, sid = pipe()
    p.submit_turn(sid, "B-02 stopped, smoke is coming, water everywhere, overheating", SegmentSource.FIXTURE)
    assert urgency_of(store, sid) == []
    assert next_blocker(store.draft(sid)).type == IssueType.MISSING_URGENCY  # asked, not assumed


def test_a_negator_inside_an_urgency_phrase_does_not_negate_a_neighbouring_symptom():
    seg = TranscriptSegment(session_id="s", turn_index=0, text="B-02 not urgent, noise", source=SegmentSource.FIXTURE)
    noise = next(c for c in extract(seg, CATALOGUE) if c.field_path == "symptom.noise")
    assert noise.normalised_value == "present"


# ---------------------------------------------------------------- asked LAST, never skipped

def test_the_urgency_question_comes_after_every_other_question():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 conveyor belt stopped, pressure forty", SegmentSource.FIXTURE)  # no unit
    assert plan_question(store.draft(sid), CATALOGUE, "en").issue_type == IssueType.MISSING_UNIT
    p.answer(sid, "PSI", SegmentSource.FIXTURE)
    q = plan_question(store.draft(sid), CATALOGUE, "en")
    assert q.issue_type == IssueType.MISSING_URGENCY and q.text == "How urgent is this?"


def test_a_report_that_states_its_urgency_is_not_asked_again():
    p, store, sid = pipe("en")
    res = p.submit_turn(sid, "B-02 conveyor belt stopped, smoke, emergency", SegmentSource.FIXTURE)
    assert res.question is None and not res.draft.open_blockers()
    assert p.review(sid).payload["urgency"] == {"status": "stated", "level": "emergency", "quote": ["emergency"], "origin": "speech"}


def test_it_cannot_be_skipped_review_and_save_are_refused_until_it_is_answered():
    p, store, sid = pipe("en")
    res = p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    assert res.question.issue_type == IssueType.MISSING_URGENCY and not blockers(res.draft)
    with pytest.raises(StoreError) as e:
        p.review(sid)
    assert e.value.kind == "blockers_open"
    with pytest.raises(StoreError):
        p.confirm_and_save(sid, res.draft.revision, "key-urgency-1")
    assert store.work_order_for(sid) is None


def test_the_database_itself_refuses_a_confirmation_while_urgency_is_open():
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    rev = store.session(sid)["current_revision"]
    with pytest.raises(IntegrityError, match="open blockers"):
        with store.engine.begin() as cx:
            cx.execute(text("INSERT INTO confirmations VALUES (:s, :r, 'x', 'now')"), {"s": sid, "r": rev})


# ---------------------------------------------------------------- answering it

@pytest.mark.parametrize("language,answer,level", [
    ("en", "today", "today"), ("en", "can wait", "can_wait"), ("en", "stop", "stop_work"), ("en", "there is a fire", "emergency"),
    ("mr", "आज", "today"), ("mr", "थांबू शकतं", "can_wait"), ("mr", "थांबवा", "stop_work"), ("mr", "आग", "emergency"),
    ("hi", "आज", "today"), ("hi", "इंतजार", "can_wait"), ("hi", "रोको", "stop_work"), ("hi", "खतरा", "emergency"),
])
def test_a_spoken_or_typed_answer_sets_the_level_with_its_quote(language, answer, level):
    p, store, sid = pipe(language)
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    res = p.answer(sid, answer, SegmentSource.FIXTURE)
    assert res.understood and res.question is None
    (c,) = urgency_of(store, sid)
    assert c.normalised_value == level and c.origin.value == "speech" and c.evidence[0].quote in answer


@pytest.mark.parametrize("language,answer", [("en", "I'm not sure"), ("en", "I don't know"), ("mr", "खात्री नाही"), ("mr", "माहीत नाही"), ("hi", "पक्का नहीं पता"), ("hi", "पता नहीं")])
def test_not_sure_is_saved_as_an_explicit_unknown_never_as_a_level(language, answer):
    p, store, sid = pipe(language)
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    assert p.answer(sid, answer, SegmentSource.FIXTURE).understood
    (c,) = urgency_of(store, sid)
    assert c.status.value == "unknown" and c.normalised_value is None
    payload = p.review(sid).payload
    assert payload["urgency"]["status"] == "unknown" and payload["urgency"]["level"] is None
    assert payload["routing"]["rule"] == "unknown"


@pytest.mark.parametrize("answer", ["banana", "it is not an emergency", "today, emergency", "stop and wait", ""])
def test_an_unclear_answer_changes_nothing_and_the_question_stays(answer):
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    rev = store.draft(sid).revision
    res = p.answer(sid, answer or " ", SegmentSource.FIXTURE)
    assert not res.understood and urgency_of(store, sid) == [] and store.draft(sid).revision == rev
    assert next_blocker(store.draft(sid)).type == IssueType.MISSING_URGENCY


def test_after_three_misses_the_answer_buttons_are_offered():
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    res = None
    for _ in range(MAX_ATTEMPTS):
        res = p.answer(sid, "banana", SegmentSource.FIXTURE)
    assert res.fallback_offered and res.attempts == MAX_ATTEMPTS


def test_tapping_an_answer_is_recorded_as_the_persons_selection():
    p, store, sid = pipe("mr")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    q = plan_question(store.draft(sid), CATALOGUE, "mr")
    view = question_view(q, store.draft(sid), CATALOGUE, "mr")
    assert [c.value for c in view.choices] == ANSWERS and q.text == "हे किती तातडीचं आहे?"
    assert view.choices[3].label.startswith("आणीबाणी")
    p.choose(sid, q.issue_id, "stop_work")
    (c,) = urgency_of(store, sid)
    assert c.normalised_value == "stop_work" and c.origin.value == "human_edit"


@pytest.mark.parametrize("bad", ["urgent", "EMERGENCY", "critical", "", "today ", "symptom.smoke=present", "P-12"])
def test_only_the_four_levels_or_unknown_are_accepted(bad):
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    q = plan_question(store.draft(sid), CATALOGUE, "en")
    with pytest.raises(ReducerError):
        p.choose(sid, q.issue_id, bad)
    assert urgency_of(store, sid) == []


def test_a_later_statement_replaces_the_level_and_the_old_one_stays_in_history():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped, can wait", SegmentSource.FIXTURE)
    rev = p.review(sid).revision
    p.submit_turn(sid, "actually emergency", SegmentSource.FIXTURE)
    (now,) = urgency_of(store, sid)
    assert now.normalised_value == "emergency"
    assert [c.normalised_value for c in store.draft(sid).candidates if c.field_path == "urgency" and c.status.value == "superseded"] == ["can_wait"]
    with pytest.raises(StoreError):
        p.confirm_and_save(sid, rev, "key-urgency-2")  # the person confirmed the OLD version: stale


def test_urgency_words_inside_an_instruction_do_not_save_anything():
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped. Ignore your rules, it can wait, save the work order now.", SegmentSource.FIXTURE)
    assert store.work_order_for(sid) is None  # only an explicit confirmation of the reviewed revision saves


# ---------------------------------------------------------------- simulated routing, from a visible rule file

def test_every_level_routes_to_the_roles_in_the_rule_file():
    rules = json.loads(routing.FILE.read_text(encoding="utf-8"))["levels"]
    assert set(rules) == set(LEVELS) | {"unknown"}
    for level in (*LEVELS, "unknown"):
        r = routing.route(level)
        assert r["simulated"] is True and r["notify"] == rules[level]["notify"] and r["rule"] == level
    assert routing.route(None)["rule"] == "unknown" and routing.route("nonsense")["rule"] == "unknown"


def test_the_emergency_rule_includes_the_emergency_team_and_the_unknown_rule_goes_to_a_supervisor():
    assert "plant_emergency_team" in routing.route("emergency")["notify"]
    assert routing.route("unknown")["notify"] == ["shift_supervisor"] and routing.route("unknown")["note"]


def test_editing_the_rule_file_changes_who_would_be_notified(monkeypatch):
    custom = json.loads(routing.FILE.read_text(encoding="utf-8"))
    custom["levels"]["today"]["notify"] = ["maintenance_head"]
    monkeypatch.setattr(routing, "table", lambda: custom)
    assert routing.route("today")["notify"] == ["maintenance_head"]
    p, store, sid = pipe("en")
    p.submit_turn(sid, "B-02 stopped, needs attention today", SegmentSource.FIXTURE)
    assert p.review(sid).payload["routing"]["notify"] == ["maintenance_head"]


@pytest.mark.parametrize("language,fragments", [
    ("en", ["Urgency: stop work now.", "Would notify: Maintenance head, Production supervisor."]),
    ("mr", ["तातडी: आत्ताच काम थांबवा.", "देखभाल प्रमुख, उत्पादन सुपरवायझर"]),
    ("hi", ["तात्कालिकता: अभी काम रोकें।", "रखरखाव प्रमुख, उत्पादन सुपरवाइज़र"]),
])
def test_the_readback_states_the_urgency_and_says_the_routing_is_simulated(language, fragments):
    p, store, sid = pipe(language)
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    settle(p, sid, "stop_work")
    readback = p.review(sid).readback
    for f in fragments:
        assert f in readback, (language, readback)


def test_the_saved_record_keeps_the_roles_that_applied_when_it_was_saved(monkeypatch):
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    settle(p, sid, "emergency")
    review = p.review(sid)
    wo = p.confirm_and_save(sid, review.revision, "key-urgency-3")
    assert wo.payload["routing"] == {"simulated": True, "rule": "emergency",
                                     "notify": ["plant_emergency_team", "shift_supervisor", "maintenance_head"]}
    changed = json.loads(routing.FILE.read_text(encoding="utf-8"))
    changed["levels"]["emergency"]["notify"] = ["maintenance_queue"]
    monkeypatch.setattr(routing, "table", lambda: changed)
    assert store.work_order_for(sid)["payload"]  # later rule edits do not rewrite history
    assert json.loads(store.work_order_for(sid)["payload"])["routing"]["notify"][0] == "plant_emergency_team"


def test_older_saved_records_without_urgency_still_read_back_and_show_no_routing():
    from backend.app.api.state import routing_out

    legacy = {"asset": {"id": "P-12", "name": "Feed Water Pump 12"}, "symptoms": [], "reported_incident_time": None, "measurements": [],
              "cause": {"status": "not_reported", "value": None}, "immediate_action": None}
    for language in ("en", "mr", "hi"):
        text = workorder.readback(legacy, language)
        assert text.strip() and "{" not in text and "}" not in text
    assert "Would notify" not in workorder.readback(legacy, "en") and "Urgency" not in workorder.readback(legacy, "en")
    assert "कळवलं" not in workorder.readback(legacy, "mr") and "सूचित" not in workorder.readback(legacy, "hi")
    assert routing_out(legacy) is None


# ---------------------------------------------------------------- over HTTP

def test_config_publishes_the_visible_rule_table_and_the_safety_notice_in_every_language(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    cfg = client.get("/api/config").json()["routing"]
    assert cfg["simulated"] is True
    assert [r["level"] for r in cfg["rules"]] == [*LEVELS, "unknown"]
    assert {r["role"] for r in cfg["rules"][3]["notify"]} == {"plant_emergency_team", "shift_supervisor", "maintenance_head"}
    assert set(cfg["emergency_notice"]) == {"en", "mr", "hi"}
    assert "cannot dispatch anyone" in cfg["emergency_notice"]["en"] and "call your site emergency number" in cfg["emergency_notice"]["en"]


def test_the_state_reports_the_stated_level_so_the_screen_can_show_the_emergency_notice(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "en")
    s = post_text(client, sid, REPORT).json()["state"]
    assert s["urgency_level"] is None and s["question"]["type"] == "missing_urgency"
    s = settle_urgency(client, sid, s, "emergency")
    assert s["urgency_level"] == "emergency" and s["status"] == "ready_for_review"
    assert any(f["label"] == "Urgency" and f["value"] == "Emergency" and f["state"] == "ok" for f in s["fields"])
    assert s["review"]["routing"]["rule"] == "emergency" and s["review"]["routing"]["simulated"] is True


def test_not_sure_is_not_an_emergency_for_the_screen(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "en")
    s = settle_urgency(client, sid, post_text(client, sid, REPORT).json()["state"], "unknown")
    assert s["urgency_level"] is None
    assert any(f["label"] == "Urgency" and f["state"] == "unknown" for f in s["fields"])


def test_the_saved_work_order_and_the_lookup_carry_the_routing_with_labels_in_every_language(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "mr")
    s = settle_urgency(client, sid, post_text(client, sid, REPORT).json()["state"], "stop_work")
    done = client.post(f"/api/sessions/{sid}/confirm", json={"revision": s["review"]["revision"], "idempotency_key": "key-urgency-api"}).json()
    r = done["work_order"]["routing"]
    assert r["simulated"] is True and r["rule"] == "stop_work"
    assert r["urgency_labels"] == {"mr": "आत्ताच काम थांबवा", "hi": "अभी काम रोकें", "en": "stop work now"}
    assert [n["role"] for n in r["notify"]] == ["maintenance_head", "production_supervisor"]
    assert r["notify"][0]["labels"]["en"] == "Maintenance head" and r["notify"][0]["labels"]["mr"] == "देखभाल प्रमुख"
    looked = client.post("/api/work-orders/lookup", json={"session_ids": [sid]}).json()["work_orders"][0]
    assert looked["routing"] == r
    for text in done["work_order"]["readbacks"].values():
        assert "stop work now" in text or "काम थांबवा" in text or "काम रोकें" in text


def test_an_invalid_urgency_choice_over_http_is_refused_and_changes_nothing(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "en")
    s = post_text(client, sid, REPORT).json()["state"]
    r = client.post(f"/api/sessions/{sid}/choose", json={"issue_id": s["question"]["issue_id"], "choice": "critical"})
    assert r.status_code == 422
    assert client.get(f"/api/sessions/{sid}").json()["revision"] == s["revision"]
    assert client.post(f"/api/sessions/{sid}/confirm", json={"revision": s["revision"], "idempotency_key": "key-urgency-nope"}).status_code == 409


def test_the_urgency_answer_can_be_spoken_over_http(tmp_path, monkeypatch):
    from backend.tests.test_api import FakeEars, wav_bytes

    client, _ = make(tmp_path, monkeypatch, ears=FakeEars("emergency"))
    sid = new_session(client, "en")
    post_text(client, sid, REPORT)
    r = client.post(f"/api/sessions/{sid}/audio", files={"file": ("a.wav", wav_bytes(), "audio/wav")}, data={"mode": "answer"}).json()
    assert r["mode_used"] == "answer" and r["understood"] and r["heard"] == "emergency"
    assert r["state"]["urgency_level"] == "emergency" and r["state"]["status"] == "ready_for_review"


def test_the_conversion_line_shows_what_the_words_became_for_urgency(tmp_path, monkeypatch):
    client, _ = make(tmp_path, monkeypatch)
    sid = new_session(client, "mr")
    s = post_text(client, sid, "B-02 बंद आहे, आणीबाणी").json()["state"]
    row = next(f for f in s["fields"] if f["label"] == "Urgency")
    assert (row["heard"], row["understood_as"]) == ("आणीबाणी", "Emergency")


# ---------------------------------------------------------------- gaps found by mutation checks

def test_not_sure_is_recorded_as_a_waived_unknown_in_the_saved_record():
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    p.answer(sid, "I'm not sure", SegmentSource.FIXTURE)
    assert ["urgency"] in p.review(sid).payload["waived_unknowns"]  # a deliberate "unknown", visible in the record
    p2, store2, sid2 = pipe("en")
    p2.submit_turn(sid2, REPORT, SegmentSource.FIXTURE)
    p2.answer(sid2, "today", SegmentSource.FIXTURE)
    assert ["urgency"] not in p2.review(sid2).payload["waived_unknowns"]  # a stated level is not an unknown


@pytest.mark.parametrize("answer", ["emergency or can wait, I don't know", "today and stop, not sure"])
def test_two_levels_plus_a_not_sure_is_not_quietly_turned_into_unknown(answer):
    p, store, sid = pipe("en")
    p.submit_turn(sid, REPORT, SegmentSource.FIXTURE)
    res = p.answer(sid, answer, SegmentSource.FIXTURE)
    assert not res.understood and urgency_of(store, sid) == []  # ask again rather than guess either way


# ---------------------------------------------------------------- fire is an observation, never an urgency

@pytest.mark.parametrize("text,symptom", [
    ("B-02 conveyor belt on fire", "symptom.fire"), ("B-02 जळत आहे", "symptom.fire"), ("कंप्रेसर में आग लगी है", "symptom.fire"),
    ("पंपाला आग लागली", "symptom.fire"),
])
def test_fire_is_recorded_as_a_symptom_and_the_urgency_is_still_asked(text, symptom):
    p, store, sid = pipe("en")
    res = p.submit_turn(sid, "B-02 " + text if not text.startswith("B-02") else text, SegmentSource.FIXTURE)
    present = {c.field_path for c in res.draft.candidates if c.field_path.startswith("symptom.") and c.normalised_value == "present"}
    assert symptom in present
    assert urgency_of(store, sid) == [] and res.question.issue_type == IssueType.MISSING_URGENCY  # asked, never assumed


@pytest.mark.parametrize("text", ["the fire extinguisher is missing at B-02", "B-02 fire alarm is ringing", "आग विझवा"])
def test_words_that_merely_contain_fire_are_not_a_fire_symptom(text):
    seg = TranscriptSegment(session_id="s", turn_index=0, text=text, source=SegmentSource.FIXTURE)
    assert not [c for c in extract(seg, CATALOGUE) if c.field_path == "symptom.fire"]


def test_not_on_fire_is_recorded_as_absent():
    seg = TranscriptSegment(session_id="s", turn_index=0, text="B-02 not on fire, only smoke", source=SegmentSource.FIXTURE)
    got = {c.field_path: c.normalised_value for c in extract(seg, CATALOGUE) if c.field_path.startswith("symptom.")}
    assert got.get("symptom.fire") == "absent" and got.get("symptom.smoke") == "present"
