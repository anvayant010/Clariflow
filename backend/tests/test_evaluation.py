"""The evaluation harness itself must be right: scoring rules, naive baseline, Break mode, report."""
import copy
import xml.dom.minidom

import pytest

from backend.app.adapters import gnani_common
from backend.app.domain.assets import load_catalogue
from backend.app.services import evaluation as ev
from backend.app.services.evalreport import build, chart_svg, markdown

CAT = load_catalogue()
M = lambda kind, value, unit=None, cf=None, flagged=False: ev.Measurement(kind=kind, value=value, unit=unit,
                                                                           corrected_from=cf, flagged=flagged)


# ---------------------------------------------------------------- scoring rules

def test_perfect_record_scores_all_correct():
    truth = {"asset": "P-12", "time": "10:30", "symptoms": {"stopped": "present"},
             "measurements": [{"kind": "pressure", "value": 50, "unit": "PSI", "corrected_from": 15}], "flags": []}
    rec = ev.Record(system="x", asset="P-12", time="10:30", symptoms={"stopped": "present"},
                    measurements=[M("pressure", 50, "PSI", 15)])
    s = ev.score(truth, rec)
    assert (s.slots, s.correct, s.risky, s.corrections_kept) == (4, 4, 0, 1)


def test_wrong_values_are_counted():
    truth = {"asset": "P-12", "symptoms": {"stopped": "present"},
             "measurements": [{"kind": "pressure", "value": 50, "unit": "PSI", "corrected_from": None}], "flags": []}
    rec = ev.Record(system="x", asset="P-21", symptoms={"stopped": "absent"}, measurements=[M("pressure", 15, "PSI")])
    s = ev.score(truth, rec)
    assert (s.wrong, s.correct, s.risky) == (3, 0, 3)


def test_each_ambiguity_saved_without_a_question_is_risky():
    for flag, rec in {
        "ambiguous_asset": ev.Record(system="x", asset="P-12"),
        "ambiguous_time": ev.Record(system="x", time="10:30"),
        "ambiguous_unit": ev.Record(system="x", measurements=[M("temperature", 60, "°C")]),
        "missing_unit": ev.Record(system="x", measurements=[M("pressure", 40, None)]),
        "conflicting_observation": ev.Record(system="x", symptoms={"leakage": "absent", "water": "present"}),
    }.items():
        truth = {"flags": [flag], "measurements": [{"kind": "pressure", "value": 40, "unit": None}] if flag == "missing_unit" else []}
        s = ev.score(truth, rec)
        assert s.risky == 1 and s.handled == 0, flag


def test_raising_the_ambiguity_is_handled_not_risky():
    s = ev.score({"flags": ["missing_unit"], "measurements": [{"kind": "pressure", "value": 40, "unit": None}]},
                 ev.Record(system="x", measurements=[M("pressure", 40, None, flagged=True)], flags=["missing_unit"]))
    assert (s.handled, s.risky, s.unnecessary_questions) == (1, 0, 0)


def test_extra_question_is_counted_but_not_risky():
    s = ev.score({"asset": "F-03", "symptoms": {"stopped": "present"}, "flags": []},
                 ev.Record(system="x", symptoms={"stopped": "present"}, flags=["unknown_asset"]))
    assert s.flagged_safe == 1 and s.unnecessary_questions == 1 and s.risky == 0


def test_missing_fact_is_not_counted_as_risky_but_is_reported():
    s = ev.score({"asset": "P-12", "flags": []}, ev.Record(system="x"))
    assert (s.missing, s.risky) == (1, 0) and "not saved" in s.notes[0]


def test_correction_trace_is_scored_separately():
    truth = {"measurements": [{"kind": "pressure", "value": 50, "unit": "PSI", "corrected_from": 15}], "flags": []}
    kept = ev.score(truth, ev.Record(system="x", measurements=[M("pressure", 50, "PSI", 15)]))
    lost = ev.score(truth, ev.Record(system="x", measurements=[M("pressure", 50, "PSI", None)]))
    assert (kept.corrections_kept, lost.corrections_kept, lost.risky) == (1, 0, 0)


# ---------------------------------------------------------------- naive baseline

def test_naive_assumes_instead_of_asking():
    r = ev.naive_record("Pump twelve is hot, temperature sixty degree, stopped at ten thirty.", CAT)
    assert r.asset == "P-12"  # first of two candidates
    assert r.measurements[0].unit == "°C"  # assumed
    assert r.time == "10:30"  # spoken hour kept as-is
    assert r.flags == []


def test_naive_keeps_both_sides_of_a_contradiction_and_last_value_of_a_correction():
    r = ev.naive_record("M-07 leakage नाही. पण पाणी दिसतंय. pressure fifteen, no, fifty PSI.", CAT)
    assert r.symptoms["leakage"] == "absent" and r.symptoms["water"] == "present"
    assert [(m.value, m.corrected_from) for m in r.measurements] == [(50, None)]


def test_naive_silently_drops_an_unreadable_number():
    assert ev.naive_record("temperature फलाणा degree", CAT).measurements == []


def test_clariflow_record_flags_the_same_inputs():
    r = ev.clariflow_record("Pump twelve is hot, temperature sixty degree, stopped at ten thirty.", CAT)
    assert r.asset is None and r.time is None
    assert {"ambiguous_asset", "ambiguous_unit", "ambiguous_time"} <= set(r.flags)


# ---------------------------------------------------------------- Break mode

@pytest.fixture(scope="module")
def break_results():
    return {b["id"]: b for b in ev.run_all_break(CAT)}


def test_six_break_scenarios_all_pass(break_results):
    assert len(break_results) == 6
    failing = {k: [c for c in v["checks"] if not c["passed"]] for k, v in break_results.items() if not v["passed"]}
    assert not failing, failing


def test_break_mode_proves_the_gate_each_time(break_results):
    for b in break_results.values():
        names = [c["name"] for c in b["checks"]]
        assert "nothing saved before confirmation" in names
        if b["id"] != "break-6-unknown-cause":
            assert "save while the question is open" in names


def test_break_mode_fails_when_an_expectation_is_wrong():
    s = copy.deepcopy(ev.load_break()[0])
    s["first_question"] = "ambiguous_asset"
    assert ev.run_break(s, CAT)["passed"] is False
    s = copy.deepcopy(ev.load_break()[0])
    s["final"]["measurements"][0]["value"] = 15
    assert ev.run_break(s, CAT)["passed"] is False


def test_break_mode_fails_when_an_answer_is_not_understood():
    s = copy.deepcopy(ev.load_break()[0])
    s["turns"][1]["text"] = "hmm what"
    assert ev.run_break(s, CAT)["passed"] is False


def test_naive_flaws_are_listed_per_scenario(break_results):
    assert any("missing unit" in f for f in break_results["break-1-correction"]["naive"]["flaws"])
    assert any("conflicting" in f for f in break_results["break-2-contradiction"]["naive"]["flaws"])
    assert any("without asking" in f for f in break_results["break-4-ambiguous-asset"]["naive"]["flaws"])
    assert any("AM/PM" in f or "time without" in f for f in break_results["break-5-ambiguous-ampm"]["naive"]["flaws"])


# ---------------------------------------------------------------- report

def test_report_is_deterministic_and_makes_no_provider_calls(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("evaluation must not call Gnani")
    monkeypatch.setattr(gnani_common, "post", boom)
    a, b = build(CAT), build(CAT)
    assert a == b
    assert a["datasets"]["clips"]["n_cases"] == 9 and a["datasets"]["phrasings"]["n_cases"] >= 57
    assert len(a["break"]) == 6


def test_report_states_limits_and_chart_is_valid_svg():
    r = build(CAT)
    md = markdown(r)
    assert "A baseline we wrote, not a real product" in md and "Truth records were written by Claude" in md
    assert "Risky total" in md
    doc = xml.dom.minidom.parseString(chart_svg(r))
    text = "".join(n.firstChild.data for n in doc.getElementsByTagName("text") if n.firstChild)
    assert "Naive baseline" in text and "Clariflow" in text and "checked items" in text
    for banned in ("foolproof", "zero hallucinations", "production-ready", "first ever"):
        assert banned not in md.lower() and banned not in text.lower()
