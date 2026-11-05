"""Rules engine: derive the issues a draft currently has, and plan ONE question.

Issues are a pure function of the active candidates, so resolving a problem means changing a
candidate (new unit, chosen asset, ...) and the issue disappears on the next recompute. Nothing
here guesses; anything unresolved stays an open issue until a human answers or explicitly marks
it unknown.
"""
import json
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.domain.schemas import (
    Asset, CandidateStatus, Draft, EvidenceRef, FieldCandidate, Issue, IssueStatus, IssueType,
)

QUESTIONS_FILE = Path(__file__).resolve().parents[1] / "lexicon" / "questions.json"

# deterministic question order: asset -> conflict -> unit -> time -> symptom
PRIORITY = [
    IssueType.AMBIGUOUS_ASSET, IssueType.UNKNOWN_ASSET, IssueType.CONFLICTING_OBSERVATION,
    IssueType.MISSING_VALUE, IssueType.MISSING_UNIT, IssueType.AMBIGUOUS_UNIT, IssueType.AMBIGUOUS_TIME,
    IssueType.MISSING_SYMPTOM, IssueType.MISSING_URGENCY,
]
# (path, value) pairs that cannot both hold at the same moment
CONFLICT_PAIRS = [
    (("symptom.leakage", "absent"), ("symptom.water", "present")),
    (("symptom.running", "present"), ("symptom.stopped", "present")),
]
LEAK_OPTIONS = ["leakage_confirmed", "source_unknown"]


def active(draft: Draft, prefix: str | None = None) -> list[FieldCandidate]:
    return [c for c in draft.candidates if c.status != CandidateStatus.SUPERSEDED
            and (prefix is None or c.field_path == prefix or c.field_path.startswith(prefix + "."))]


def conflict_options(a: FieldCandidate, b: FieldCandidate) -> list[str]:
    paths = {a.field_path, b.field_path}
    if paths == {"symptom.leakage", "symptom.water"}:
        return LEAK_OPTIONS
    return [f"{a.field_path}={a.normalised_value}", f"{b.field_path}={b.normalised_value}"]


def derive(draft: Draft) -> list[Issue]:
    """Issues implied by the active candidates (not yet merged with history)."""
    out: list[Issue] = []

    assets = active(draft, "asset")
    if not assets:
        out.append(Issue(type=IssueType.UNKNOWN_ASSET, key="unknown_asset", field_paths=["asset"]))
    elif assets[0].status == CandidateStatus.NEEDS_CLARIFICATION:
        c = assets[0]
        out.append(Issue(type=IssueType.AMBIGUOUS_ASSET, key=f"ambiguous_asset|{c.id}", field_paths=["asset"],
                         evidence=c.evidence, options=list(c.meta.get("options", []))))

    symptoms = active(draft, "symptom")
    if not any(c.normalised_value == "present" for c in symptoms):
        out.append(Issue(type=IssueType.MISSING_SYMPTOM, key="missing_symptom", field_paths=["symptom"]))

    if not active(draft, "urgency"):  # stated in the report, answered, or explicitly "not sure": otherwise ask
        out.append(Issue(type=IssueType.MISSING_URGENCY, key="missing_urgency", field_paths=["urgency"]))

    seen = set()
    for i, a in enumerate(symptoms):
        for b in symptoms[i + 1:]:
            same_concept = a.field_path == b.field_path and a.normalised_value != b.normalised_value
            pair = any({(a.field_path, a.normalised_value), (b.field_path, b.normalised_value)} == set(p)
                       for p in CONFLICT_PAIRS)
            if not (same_concept or pair) or a.meta.get("temporal") or b.meta.get("temporal"):
                continue  # a temporal change ("पहले… अब…") is not a contradiction
            key = f"conflict|{a.id}|{b.id}"
            if key not in seen:
                seen.add(key)
                out.append(Issue(type=IssueType.CONFLICTING_OBSERVATION, key=key,
                                 field_paths=[a.field_path, b.field_path], evidence=a.evidence + b.evidence,
                                 options=conflict_options(a, b)))

    for c in active(draft, "measurement"):
        if c.meta.get("value_missing"):
            out.append(Issue(type=IssueType.MISSING_VALUE, key=f"missing_value|{c.id}", field_paths=[c.field_path],
                             evidence=c.evidence, options=["unknown"]))
            continue
        if c.status == CandidateStatus.UNKNOWN:
            continue  # the user said the value is unknown
        if c.meta.get("old_value_missing"):
            out.append(Issue(type=IssueType.POSSIBLE_DROPPED_VALUE, key=f"dropped|{c.id}", blocking=False,
                             field_paths=[c.field_path], evidence=c.evidence))
        if c.meta.get("unit_ambiguous"):
            opts = ["°C", "°F", "unknown"] if c.meta.get("kind") == "temperature" else ["unknown"]
            out.append(Issue(type=IssueType.AMBIGUOUS_UNIT, key=f"ambiguous_unit|{c.id}", field_paths=[c.field_path],
                             evidence=c.evidence, options=opts))
        elif c.unit is None and c.meta.get("unit_status") != "unknown":
            out.append(Issue(type=IssueType.MISSING_UNIT, key=f"missing_unit|{c.id}", field_paths=[c.field_path],
                             evidence=c.evidence, options=["unknown"]))
        if c.meta.get("corrected_from_id") and c.status == CandidateStatus.PROPOSED:
            old = next((o for o in draft.candidates if o.id == c.meta["corrected_from_id"]), None)
            out.append(Issue(type=IssueType.UNCONFIRMED_CORRECTION, key=f"correction|{c.id}", blocking=False,
                             field_paths=[c.field_path], evidence=(old.evidence if old else []) + c.evidence))

    times = active(draft, "time")
    if times and times[0].meta.get("corrected_from_id") and times[0].status != CandidateStatus.UNKNOWN:
        old = next((o for o in draft.candidates if o.id == times[0].meta["corrected_from_id"]), None)
        out.append(Issue(type=IssueType.UNCONFIRMED_CORRECTION, key=f"correction|{times[0].id}", blocking=False,
                         field_paths=["time"], evidence=(old.evidence if old else []) + times[0].evidence))
    if times and times[0].status == CandidateStatus.NEEDS_CLARIFICATION:
        out.append(Issue(type=IssueType.AMBIGUOUS_TIME, key=f"ambiguous_time|{times[0].id}", field_paths=["time"],
                         evidence=times[0].evidence, options=["am", "pm", "unknown"]))
    for path in ("time", "cause"):  # optional details a person can add; immediate action is recorded only if said
        if not active(draft, path):
            out.append(Issue(type=IssueType.OPTIONAL_DETAIL, key=f"optional|{path}", blocking=False,
                             field_paths=[path]))
    return out


def sync_issues(existing: list[Issue], derived: list[Issue], revision: int,
                resolution_evidence: list[EvidenceRef] | None = None, waived: bool = False) -> list[Issue]:
    """Keep ids stable for issues that persist, close ones that went away, add new ones."""
    by_key = {i.key: i for i in existing if i.status == IssueStatus.OPEN}
    derived_keys = {i.key for i in derived}
    out = [i for i in existing if i.status != IssueStatus.OPEN]
    for old in by_key.values():
        if old.key in derived_keys:
            out.append(old)
        else:
            out.append(old.model_copy(update={
                "status": IssueStatus.WAIVED_UNKNOWN if waived else IssueStatus.RESOLVED,
                "resolved_revision": revision, "resolution_evidence": resolution_evidence or []}))
    for new in derived:
        if new.key not in by_key:
            out.append(new.model_copy(update={"created_revision": revision}))
    return out


# ---------------------------------------------------------------- questions


class Question(BaseModel):
    issue_id: str
    issue_type: IssueType
    language: str
    text: str
    options: list[str] = Field(default_factory=list)


def _templates() -> dict:
    return json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))


def next_blocker(draft: Draft) -> Issue | None:
    blockers = draft.open_blockers()
    for t in PRIORITY:
        for issue in blockers:
            if issue.type == t:
                return issue
    return blockers[0] if blockers else None


def plan_question(draft: Draft, catalogue: list[Asset], language: str = "mr") -> Question | None:
    """ONE question for the highest-priority blocking issue, or None when nothing blocks."""
    issue = next_blocker(draft)
    if issue is None:
        return None
    tpl = _templates()
    names = {a.id: f"{a.id} ({a.display_name})" for a in catalogue}
    quotes = [e.quote for e in issue.evidence]
    ctx = {"mention": quotes[0] if quotes else "", "options": " / ".join(names.get(o, o) for o in issue.options),
           "a": quotes[0] if quotes else "", "b": quotes[-1] if quotes else "", "kind": "", "value": "", "raw_unit": "",
           "time": quotes[0] if quotes else ""}
    key = issue.type.value
    if issue.type in (IssueType.MISSING_UNIT, IssueType.AMBIGUOUS_UNIT, IssueType.MISSING_VALUE):
        c = next(c for c in active(draft, issue.field_paths[0]) if issue.key.endswith(c.id))
        kind = c.meta.get("kind", "")
        ctx.update(kind=tpl["kind_names"].get(kind, {}).get(language, kind), value=c.normalised_value,
                   raw_unit=c.meta.get("raw_unit") or "")
        if issue.type == IssueType.AMBIGUOUS_UNIT and kind == "temperature":
            key = "ambiguous_unit_temperature"
        if issue.type == IssueType.MISSING_UNIT and c.meta.get("unit_mismatch"):
            key = "unit_mismatch"
    if issue.type == IssueType.CONFLICTING_OBSERVATION and issue.options == LEAK_OPTIONS:
        key = "conflicting_observation_leak"
    text = tpl["questions"][key][language].format(**ctx)
    return Question(issue_id=issue.id, issue_type=issue.type, language=language, text=text, options=issue.options)
