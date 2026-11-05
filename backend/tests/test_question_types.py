"""Every question type, in Marathi / Hindi / English, answered by typed or spoken text (both go through
`Pipeline.answer`) and by tapping a choice. The cases are in question_cases.py.

What this pins down: the right question is asked, a natural answer resolves it to the right value, and an answer that
does not fit (wrong kind of unit, "the big one", "maybe") is NOT accepted: the same question is asked again.
"""
import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.issues import active, next_blocker
from backend.app.domain.schemas import CandidateStatus, SegmentSource
from backend.app.services.pipeline import Pipeline
from backend.app.services.view import question_view
from backend.app.storage.store import Store, make_engine
from backend.tests.question_cases import CASES

CATALOGUE = load_catalogue()


def session(lang, report):
    p = Pipeline(Store(make_engine()), CATALOGUE, lang)
    sid = p.start()
    p.submit_turn(sid, report, SegmentSource.FIXTURE)
    return p, sid


def qtype(p, sid):
    issue = next_blocker(p.store.draft(sid))
    return issue.type.value if issue else None


def state(p, sid):
    out = {}
    for c in active(p.store.draft(sid)):
        if c.status == CandidateStatus.UNKNOWN:
            out[c.field_path] = "unknown"
        elif c.status == CandidateStatus.NEEDS_CLARIFICATION:
            out[c.field_path] = "?"
        else:
            unit = f" {c.unit}" if c.unit else (" unit-unknown" if c.meta.get("unit_status") == "unknown" else "")
            out[c.field_path] = f"{c.normalised_value}{unit}"
    return out


def _id(case):
    return f"{case[0]}-{case[1]}"


@pytest.mark.parametrize("case", CASES, ids=[_id(c) for c in CASES])
def test_the_right_question_is_asked(case):
    name, lang, report, expect_q, _ = case
    p, sid = session(lang, report)
    assert qtype(p, sid) == expect_q


ANSWERS = [(c, a) for c in CASES for a in c[4]]


@pytest.mark.parametrize("case,answer", ANSWERS, ids=[f"{_id(c)}-{a[0]}" for c, a in ANSWERS])
def test_an_answer_is_understood_or_the_question_is_repeated(case, answer):
    name, lang, report, expect_q, _ = case
    text, want = answer
    p, sid = session(lang, report)
    result = p.answer(sid, text, SegmentSource.FIXTURE)
    if want is None:  # does not fit: nothing may be guessed, the same question comes back
        assert not result.understood and qtype(p, sid) == expect_q
    else:
        field, value = want
        assert state(p, sid).get(field) == value and qtype(p, sid) != expect_q


@pytest.mark.parametrize("case", [c for c in CASES if c[3] not in ("missing_value", "missing_urgency")], ids=lambda c: _id(c))
def test_every_tap_choice_resolves_the_question(case):
    """The typed/tapped fallback: each choice the screen offers must move the report forward (never a dead end)."""
    name, lang, report, expect_q, _ = case
    p, sid = session(lang, report)
    q = p.store.draft(sid)
    from backend.app.domain.issues import plan_question
    view = question_view(plan_question(q, CATALOGUE, lang), q, CATALOGUE, lang)
    assert view.choices, "a question with nothing to tap is a dead end"
    for choice in view.choices:
        p2, sid2 = session(lang, report)
        issue = next_blocker(p2.store.draft(sid2))
        p2.choose(sid2, issue.id, choice.value)
        assert next_blocker(p2.store.draft(sid2)) != issue, (choice.value, "did not resolve the question")
