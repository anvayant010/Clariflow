"""Coverage probe: varied synthetic phrasings through the real extract -> reduce -> question path.

The transcripts are Claude-written (fixtures/cases/phrasings.json), not Prisma output. They show
where the deterministic extractor is and is not robust; failures are fixed or listed as limits.
"""
import json
from pathlib import Path

import pytest

from backend.app.domain.assets import load_catalogue
from backend.app.domain.issues import active
from backend.app.domain.schemas import CandidateStatus
from backend.app.services.pipeline import Pipeline
from backend.app.storage.store import Store, make_engine

CASES = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "cases" / "phrasings.json")
                   .read_text(encoding="utf-8"))["cases"]


def observe(text: str) -> dict:
    store = Store(make_engine())
    pipe = Pipeline(store, load_catalogue(), "en")
    sid = pipe.start()
    res = pipe.submit_turn(sid, text)
    d = res.draft
    by_id = {c.id: c for c in d.candidates}
    asset = next(iter(active(d, "asset")), None)
    time_c = next(iter(active(d, "time")), None)
    meas = active(d, "measurement")
    return {
        "asset": (None if asset is None else asset.normalised_value if asset.status != CandidateStatus.NEEDS_CLARIFICATION
                  else "ambiguous"),
        "symptoms": {c.field_path.split(".")[1]: c.normalised_value for c in active(d, "symptom")},
        "measurements": [[c.meta["kind"], c.normalised_value, c.unit] for c in meas],
        "corrected": [[c.meta["kind"], by_id[c.meta["corrected_from_id"]].normalised_value]
                      for c in meas if c.meta.get("corrected_from_id") in by_id],
        "time_corrected_from": (by_id[time_c.meta["corrected_from_id"]].normalised_value
                                if time_c is not None and time_c.meta.get("corrected_from_id") in by_id else None),
        "dropped_old": any(c.meta.get("old_value_missing") for c in meas),
        "time": None if time_c is None else (time_c.normalised_value if time_c.status != CandidateStatus.UNKNOWN else "unknown"),
        "cause": "unknown" if active(d, "cause") else None,
        "action": next((c.normalised_value for c in active(d, "immediate_action")), None),
        "question": (res.question.issue_type.value if res.question and res.question.issue_type.value != "missing_urgency" else None),
    }


def check(got: dict, expect: dict) -> list[str]:
    bad = []
    for key, want in expect.items():
        have = got[key]
        if key == "symptoms":
            for concept, state in want.items():
                if have.get(concept) != state:
                    bad.append(f"symptom {concept}: want {state}, got {have.get(concept)}")
        elif key in ("measurements", "corrected"):
            if sorted(map(repr, have)) != sorted(map(repr, want)):
                bad.append(f"{key}: want {want}, got {have}")
        elif have != want:
            bad.append(f"{key}: want {want!r}, got {have!r}")
    return bad


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_phrasing(case):
    if case.get("known_gap"):
        pytest.xfail(case["known_gap"])
    problems = check(observe(case["text"]), case["expect"])
    assert not problems, "; ".join(problems)
