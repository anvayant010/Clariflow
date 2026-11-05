"""Naive baseline, scoring, and Break mode.

The "naive baseline" is a baseline WE wrote, not a competing product. It is the same transcript
parsing as Clariflow (so number/asset reading is not what is being compared) followed by
"save as heard" with no checking:
  - ambiguous asset      -> takes the first candidate
  - "degree"             -> assumes Celsius
  - time without AM/PM   -> keeps the spoken hour as if it were 24-hour
  - missing unit         -> saves the number with no unit and no flag
  - contradiction        -> saves both statements as fact
  - correction           -> last value wins, no trace of the earlier one
  - unreadable number    -> silently drops the measurement
  - saves immediately, nothing asked
On audio it also uses plain `verbatim` STT without keyterms (the config we started from).

Scoring counts CHECKED ITEMS against a truth record. A genuine ambiguity in what was said is a
"flag" in the truth: a careful system must ask about it, so saving a value there is an assumption.
Wrong, assumed and unresolved items are all "risky saves". Clariflow's numbers describe its draft
BEFORE any human answers; it cannot save until they are resolved and confirmed.
"""
import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.domain.assets import load_catalogue
from backend.app.domain.extractor import extract
from backend.app.domain.issues import active
from backend.app.domain.schemas import Asset, CandidateStatus, IssueType, SegmentSource, TranscriptSegment
from backend.app.services.pipeline import Pipeline
from backend.app.storage.store import Store, StoreError, make_engine

CASES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "cases"
CONFLICT_CONCEPTS = {"leakage", "water", "running", "stopped"}
NAIVE_DEFINITION = ("A baseline we wrote, not a real product: the same transcript parsing as Clariflow, then 'save as heard' "
                    "with no checks (first asset candidate, Celsius assumed, spoken hour kept as-is, missing unit left blank, "
                    "contradictions saved as fact, last value wins, nothing asked). On audio it uses plain verbatim STT.")


# ---------------------------------------------------------------- records


class Measurement(BaseModel):
    kind: str
    value: float | int
    unit: str | None = None
    corrected_from: float | int | None = None
    flagged: bool = False


class Record(BaseModel):
    """What a system holds about the report at the moment it would save."""

    system: str
    asset: str | None = None
    time: str | None = None
    measurements: list[Measurement] = Field(default_factory=list)
    symptoms: dict[str, str] = Field(default_factory=dict)
    cause: str | None = None
    flags: list[str] = Field(default_factory=list)  # blocking questions raised (Clariflow only)


def _segment(text: str) -> TranscriptSegment:
    return TranscriptSegment(session_id="eval", turn_index=0, text=text, source=SegmentSource.FIXTURE)


def naive_record(text: str, catalogue: list[Asset]) -> Record:
    rec = Record(system="naive")
    for c in extract(_segment(text), catalogue):
        if c.status == CandidateStatus.SUPERSEDED:
            continue
        head = c.field_path.split(".")[0]
        if head == "asset":
            options = sorted(c.meta.get("options", []))
            rec.asset = (options[0] if options else None) if c.status == CandidateStatus.NEEDS_CLARIFICATION else c.normalised_value
        elif head == "time":
            rec.time = c.normalised_value or f"{c.meta['hour_spoken']:02d}:{c.meta['minute']:02d}"
        elif head == "measurement":
            if c.meta.get("value_missing") or c.normalised_value is None:
                continue  # the naive path cannot read it and says nothing
            unit = "°C" if c.meta.get("unit_ambiguous") else c.unit
            rec.measurements.append(Measurement(kind=c.meta["kind"], value=c.normalised_value, unit=unit))
        elif head == "symptom":
            rec.symptoms[c.field_path.split(".", 1)[1]] = str(c.normalised_value)
        elif head == "cause":
            rec.cause = "unknown"
    return rec


def clariflow_record(text: str, catalogue: list[Asset]) -> Record:
    """Run one report turn through the production pipeline and read the draft (no answers given)."""
    pipe = Pipeline(Store(make_engine()), catalogue, "en")
    sid = pipe.start()
    draft = pipe.submit_turn(sid, text, SegmentSource.FIXTURE).draft
    by_id = {c.id: c for c in draft.candidates}
    # the final urgency question is asked of every report: it is not an ambiguity in what was said, so it is not counted here
    rec = Record(system="clariflow", flags=sorted({i.type.value for i in draft.open_blockers() if i.type != IssueType.MISSING_URGENCY}))
    for c in active(draft):
        head = c.field_path.split(".")[0]
        if head == "asset":
            rec.asset = None if c.status == CandidateStatus.NEEDS_CLARIFICATION else c.normalised_value
        elif head == "time":
            rec.time = c.normalised_value if c.status in (CandidateStatus.PROPOSED, CandidateStatus.CONFIRMED) else None
        elif head == "measurement":
            if c.normalised_value is None:
                continue
            old = by_id.get(c.meta.get("corrected_from_id"))
            flagged = bool(c.meta.get("unit_ambiguous") or (c.unit is None and c.meta.get("unit_status") != "unknown"))
            rec.measurements.append(Measurement(kind=c.meta["kind"], value=c.normalised_value, unit=c.unit,
                                                corrected_from=old.normalised_value if old else None, flagged=flagged))
        elif head == "symptom":
            rec.symptoms[c.field_path.split(".", 1)[1]] = str(c.normalised_value)
        elif head == "cause":
            rec.cause = "unknown"
    return rec


# ---------------------------------------------------------------- scoring


class Score(BaseModel):
    slots: int = 0  # checked items
    correct: int = 0
    wrong: int = 0  # a saved value that contradicts the truth
    assumed: int = 0  # a value saved where the truth is a genuine ambiguity
    unresolved: int = 0  # a genuine ambiguity saved with no flag and no assumed value
    missing: int = 0  # a definite fact that was not saved and not flagged
    flagged_safe: int = 0  # a definite fact the system asked about instead of saving (safe but costs a question)
    handled: int = 0  # a genuine ambiguity the system raised
    unnecessary_questions: int = 0
    corrections_total: int = 0
    corrections_kept: int = 0
    notes: list[str] = Field(default_factory=list)

    @property
    def risky(self) -> int:
        return self.wrong + self.assumed + self.unresolved


def score(truth: dict, rec: Record) -> Score:
    s, flags, tflags = Score(), set(rec.flags), set(truth.get("flags", []))

    def note(msg: str) -> None:
        s.notes.append(msg)

    t_asset = truth.get("asset")
    if t_asset:
        s.slots += 1
        if rec.asset == t_asset:
            s.correct += 1
        elif rec.asset is None and flags & {"ambiguous_asset", "unknown_asset"}:
            s.flagged_safe += 1
        elif rec.asset is None:
            s.missing += 1
            note(f"asset {t_asset} not saved, nothing asked")
        else:
            s.wrong += 1
            note(f"asset saved as {rec.asset}, truth {t_asset}")

    t_time = truth.get("time")
    if t_time:
        s.slots += 1
        if rec.time == t_time:
            s.correct += 1
        elif rec.time is None and "ambiguous_time" in flags:
            s.flagged_safe += 1
        elif rec.time is None:
            s.missing += 1
            note(f"time {t_time} not saved, nothing asked")
        else:
            s.wrong += 1
            note(f"time saved as {rec.time}, truth {t_time}")

    for tm in truth.get("measurements", []):
        s.slots += 1
        same_kind = [m for m in rec.measurements if m.kind == tm["kind"]]
        got = next((m for m in same_kind if m.value == tm["value"]), same_kind[0] if same_kind else None)
        if got is None:
            if "missing_value" in flags:
                s.flagged_safe += 1
            else:
                s.missing += 1
                note(f"{tm['kind']} {tm['value']} not saved, nothing asked")
        elif got.value != tm["value"]:
            s.wrong += 1
            note(f"{tm['kind']} saved as {got.value}, truth {tm['value']}")
        elif tm["unit"] is None or got.unit == tm["unit"]:
            s.correct += 1
        elif got.unit is None:
            if got.flagged:
                s.flagged_safe += 1
            else:
                s.missing += 1
                note(f"{tm['kind']} unit {tm['unit']} lost, nothing asked")
        else:
            s.wrong += 1
            note(f"{tm['kind']} unit saved as {got.unit}, truth {tm['unit']}")
        if tm.get("corrected_from") is not None:
            s.corrections_total += 1
            s.corrections_kept += int(got is not None and got.corrected_from == tm["corrected_from"])

    for concept, state in truth.get("symptoms", {}).items():
        s.slots += 1
        have = rec.symptoms.get(concept)
        if have == state:
            s.correct += 1
        elif "conflicting_observation" in flags and concept in CONFLICT_CONCEPTS:
            s.flagged_safe += 1
        elif have is None:
            s.missing += 1
            note(f"symptom {concept} not saved")
        else:
            s.wrong += 1
            note(f"symptom {concept} saved as {have}, truth {state}")

    if truth.get("cause") == "unknown":
        s.slots += 1
        if rec.cause == "unknown":
            s.correct += 1
        else:
            s.missing += 1
            note("explicit 'cause unknown' not saved")

    # genuine ambiguities: the careful behaviour is to raise them
    for flag in sorted(tflags):
        s.slots += 1
        if flag in flags:
            s.handled += 1
        elif flag == "ambiguous_asset" and rec.asset:
            s.assumed += 1
            note(f"ambiguous asset: saved {rec.asset} without asking")
        elif flag == "ambiguous_time" and rec.time:
            s.assumed += 1
            note(f"time without AM/PM saved as {rec.time}")
        elif flag == "ambiguous_unit" and any(m.unit in ("°C", "°F") for m in rec.measurements):
            s.assumed += 1
            note("'degree' saved as Celsius without asking")
        elif flag == "missing_unit" and any(m.unit is not None and m.kind in
                                           {x["kind"] for x in truth.get("measurements", [])} for m in rec.measurements):
            s.assumed += 1
            note("a unit nobody said was saved")
        else:
            s.unresolved += 1
            note(f"{flag.replace('_', ' ')} saved with no question")

    if truth.get("flags_specified", True):
        tolerated = {"missing_symptom"} if not truth.get("symptoms") else set()
        extra = sorted(flags - tflags - tolerated)
        s.unnecessary_questions += len(extra)
        for f in extra:
            note(f"asked beyond the inherent ambiguities: {f}")
    return s


# ---------------------------------------------------------------- datasets


def load_clips() -> list[dict]:
    return json.loads((CASES_DIR / "eval_clips.json").read_text(encoding="utf-8"))["clips"]


def truth_from_expect(expect: dict) -> dict:
    corrected = {kind: frm for kind, frm in expect.get("corrected", [])}
    return {
        "asset": expect.get("asset"), "time": expect.get("time"), "symptoms": expect.get("symptoms", {}),
        "cause": expect.get("cause"),
        "measurements": [{"kind": k, "value": v, "unit": u, "corrected_from": corrected.get(k)}
                         for k, v, u in expect.get("measurements", [])],
        "flags": [expect["question"]] if expect.get("question") else [],
        "flags_specified": "question" in expect,
    }


def load_phrasings() -> list[dict]:
    cases = json.loads((CASES_DIR / "phrasings.json").read_text(encoding="utf-8"))["cases"]
    return [{"id": c["id"], "naive_text": c["text"], "text": c["text"], "truth": truth_from_expect(c["expect"])}
            for c in cases if not c.get("known_gap")]


def clip_cases() -> list[dict]:
    return [{"id": c["id"], "naive_text": c["transcripts"]["plain_verbatim"],
             "text": c["transcripts"]["codemix_keyterms"], "truth": c["truth"]} for c in load_clips()]


TOTAL_FIELDS = ["slots", "correct", "wrong", "assumed", "unresolved", "missing", "flagged_safe", "handled",
                "unnecessary_questions", "corrections_total", "corrections_kept"]


def run_cases(cases: list[dict], catalogue: list[Asset]) -> dict:
    rows, totals = [], {sys: dict.fromkeys(TOTAL_FIELDS + ["risky", "cases_with_risky"], 0) for sys in ("naive", "clariflow")}
    for case in cases:
        row = {"id": case["id"], "truth": case["truth"]}
        for system, text, build in (("naive", case["naive_text"], naive_record), ("clariflow", case["text"], clariflow_record)):
            rec = build(text, catalogue)
            sc = score(case["truth"], rec)
            row[system] = {"transcript": text, "record": rec.model_dump(), "score": sc.model_dump() | {"risky": sc.risky}}
            for f in TOTAL_FIELDS:
                totals[system][f] += getattr(sc, f)
            totals[system]["risky"] += sc.risky
            totals[system]["cases_with_risky"] += int(sc.risky > 0)
        rows.append(row)
    return {"n_cases": len(cases), "totals": totals, "rows": rows}


# ---------------------------------------------------------------- Break mode


def payload_checks(payload: dict, final: dict) -> list[dict]:
    out = []

    def check(name, expected, actual):
        out.append({"name": name, "expected": expected, "actual": actual, "passed": expected == actual})

    if "asset" in final:
        check("asset", final["asset"], payload["asset"] and payload["asset"]["id"])
    if "time" in final:
        check("time", final["time"], payload["reported_incident_time"] and payload["reported_incident_time"]["value"])
    for concept, state in final.get("symptoms", {}).items():
        check(f"symptom {concept}", state, next((s["state"] for s in payload["symptoms"] if s["concept"] == concept), None))
    for fm in final.get("measurements", []):
        m = next((m for m in payload["measurements"] if m["kind"] == fm["kind"]), None)
        got = m and {"value": m["value"], "unit": m["unit"], "corrected_from": (m.get("corrected_from") or {}).get("value")}
        check(f"{fm['kind']}", {k: fm[k] for k in ("value", "unit", "corrected_from")}, got)
    if "cause" in final:
        check("cause", final["cause"], "unknown" if payload["cause"]["status"] == "unknown" else None)
    if "urgency" in final:  # the person's own answer (never inferred), with SIMULATED routing recorded beside it
        check("urgency", final["urgency"], payload["urgency"]["level"] or "unknown")
        check("routing is simulated", True, payload["routing"]["simulated"])
    return out


def load_break() -> list[dict]:
    return json.loads((CASES_DIR / "break_scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def run_break(scenario: dict, catalogue: list[Asset] | None = None) -> dict:
    catalogue = catalogue or load_catalogue()
    clips = {c["id"]: c for c in load_clips()}
    checks: list[dict] = []

    def check(name, expected, actual):
        checks.append({"name": name, "expected": expected, "actual": actual, "passed": expected == actual})

    store = Store(make_engine())
    pipe = Pipeline(store, catalogue, "en")
    sid = pipe.start()
    res, first_question, transcript = None, "(not run)", ""
    try:
        for n, turn in enumerate(scenario["turns"]):
            text = clips[turn["from_clip"]]["transcripts"]["codemix_keyterms"] if "from_clip" in turn else turn["text"]
            if n == 0:
                transcript = text
            if turn.get("answers"):  # e.g. urgency: it must be the question that is open, and it comes after everything else
                open_q = res.question.issue_type.value if res is not None and res.question else None
                check(f"{turn['answers']} is asked, after the other questions", turn["answers"], open_q)
            res = (pipe.submit_turn(sid, text, SegmentSource.FIXTURE) if turn["as"] == "report"
                   else pipe.answer(sid, text, SegmentSource.FIXTURE))
            if n == 0:
                first_question = res.question.issue_type.value if res.question else None
                check("first question asked", scenario["first_question"], first_question)
                check("nothing saved before confirmation", None, store.work_order_for(sid))
                if res.question:
                    for what, call in (("review", lambda: pipe.review(sid)),
                                       ("save", lambda: pipe.confirm_and_save(sid, res.draft.revision, "break-gate"))):
                        try:
                            call()
                            outcome = "allowed (BUG)"
                        except StoreError:
                            outcome = "refused"
                        check(f"{what} while the question is open", "refused", outcome)
            elif not res.understood:
                check("answer understood", True, False)
        check("all questions resolved", None, res.question.issue_type.value if res.question else None)
        review = pipe.review(sid)
        checks.extend(payload_checks(review.payload, scenario["final"]))
        wo = pipe.confirm_and_save(sid, review.revision, f"break-{scenario['id']}")
        check("saved only after explicit confirmation of the reviewed revision", review.revision, wo.confirmed_revision)
    except Exception as e:  # noqa: BLE001 - a crash is a failed scenario, reported as such
        checks.append({"name": "run completed", "expected": "no error", "actual": f"{type(e).__name__}: {e}", "passed": False})

    clip = clips.get(scenario.get("clip") or "")
    truth = clip["truth"] if clip else scenario["truth"]
    naive_text = clip["transcripts"]["plain_verbatim"] if clip else transcript
    naive_rec = naive_record(naive_text, catalogue)
    naive_score = score(truth, naive_rec)
    return {
        "id": scenario["id"], "title": scenario["title"], "what_it_tests": scenario["what_it_tests"],
        "provenance": scenario.get("provenance") or "real Prisma v3.0 transcript of Anvay's recording, 2026-11-04",
        "transcript": transcript, "checks": checks, "passed": all(c["passed"] for c in checks),
        "naive": {"transcript": naive_text, "record": naive_rec.model_dump(), "risky": naive_score.risky,
                  "flaws": naive_score.notes},
    }


def run_all_break(catalogue: list[Asset] | None = None) -> list[dict]:
    catalogue = catalogue or load_catalogue()
    return [run_break(s, catalogue) for s in load_break()]
