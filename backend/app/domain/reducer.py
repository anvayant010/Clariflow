"""Reducer: the only code that builds a new draft revision.

Each call returns a NEW Draft (revision + 1); the input is never mutated and old values are kept
as SUPERSEDED candidates, so history survives. Candidates whose evidence does not point at real
transcript text are rejected before they can touch the draft.
"""
import math

from backend.app.domain.issues import LEAK_OPTIONS, active, derive, sync_issues
from backend.app.domain.normaliser import default_lexicon
from backend.app.domain.urgency import ANSWERS
from backend.app.domain.schemas import (
    CandidateOrigin, CandidateStatus, Draft, EvidenceRef, FieldCandidate, Issue, IssueStatus, IssueType,
    TranscriptSegment, new_id,
)

MULTI_VALUED = "symptom"  # every other path holds one current value


class ReducerError(ValueError):
    pass


def symptom_choices() -> list[str]:
    """Symptoms a person can tap when asked what they saw (the lexicon's symptom concepts; 'running' is not a fault)."""
    return [c.split(":", 1)[1] for c in default_lexicon().concepts if c.startswith("symptom:") and c != "symptom:running"]


def units_for_kind(kind: str | None) -> set[str]:
    """Canonical, unambiguous units that make sense for a measurement kind."""
    return {u["canonical"] for u in default_lexicon().units.values() if u["kind"] == kind and not u["ambiguous"]}


def evidence_valid(ev: EvidenceRef, segments: dict[str, TranscriptSegment]) -> bool:
    seg = segments.get(ev.segment_id)
    if seg is None or not ev.quote or ev.quote not in seg.text:
        return False
    if ev.start_char is not None and ev.end_char is not None:
        return seg.text[ev.start_char:ev.end_char] == ev.quote
    return True


def candidate_valid(c: FieldCandidate, segments: dict[str, TranscriptSegment]) -> bool:
    if c.origin == CandidateOrigin.HUMAN_EDIT and not c.evidence:
        return True  # typed/selected by the user; stays labelled as such
    return bool(c.evidence) and all(evidence_valid(e, segments) for e in c.evidence)


def _is_multi(path: str) -> bool:
    return path.split(".")[0] == MULTI_VALUED


def _finish(draft: Draft, candidates: list[FieldCandidate], issues_from: list[Issue],
            resolution_evidence=None, waived=False) -> Draft:
    new = Draft(session_id=draft.session_id, revision=draft.revision + 1, candidates=candidates, issues=[])
    new.issues = sync_issues(issues_from, derive(new), new.revision, resolution_evidence, waived)
    return new


def apply_candidates(draft: Draft, proposals: list[FieldCandidate], segments: dict[str, TranscriptSegment]
                     ) -> tuple[Draft, list[FieldCandidate]]:
    """Merge extractor proposals into a new revision. Returns (new draft, rejected proposals)."""
    rev = draft.revision + 1
    cands = [c.model_copy(deep=True) for c in draft.candidates]
    rejected: list[FieldCandidate] = []
    batch_ids = {p.id for p in proposals}

    for p in proposals:
        if not candidate_valid(p, segments):
            rejected.append(p)
            continue
        p = p.model_copy(deep=True, update={"revision": rev})
        if p.status == CandidateStatus.SUPERSEDED:  # old side of an in-turn correction
            cands.append(p)
            continue
        if _is_multi(p.field_path):
            if any(c.status != CandidateStatus.SUPERSEDED and c.field_path == p.field_path
                   and c.normalised_value == p.normalised_value for c in cands):
                continue  # already recorded
            cands.append(p)
            continue
        previous = [c for c in cands if c.field_path == p.field_path and c.status != CandidateStatus.SUPERSEDED
                    and c.id != p.replaces_candidate_id and c.id not in batch_ids]
        for old in previous:
            if (p.field_path == "asset" and old.normalised_value and p.normalised_value
                    and old.normalised_value != p.normalised_value):
                # a different asset in a later turn is never swapped silently: ask
                p.status, p.meta["options"] = CandidateStatus.NEEDS_CLARIFICATION, sorted(
                    {old.normalised_value, p.normalised_value})
                p.raw_value, p.normalised_value = p.raw_value, None
            old.status = CandidateStatus.SUPERSEDED
            p.replaces_candidate_id = p.replaces_candidate_id or old.id
        cands.append(p)
    return _finish(draft, cands, draft.issues), rejected


# ---------------------------------------------------------------- answers / choices


def _replace(cands: list[FieldCandidate], old: FieldCandidate, new: FieldCandidate, rev: int) -> None:
    for c in cands:
        if c.id == old.id:
            c.status = CandidateStatus.SUPERSEDED
    new.replaces_candidate_id, new.revision = old.id, rev
    cands.append(new)


def resolve_issue(draft: Draft, issue_id: str, choice: str, evidence: list[EvidenceRef] | None = None,
                  segments: dict[str, TranscriptSegment] | None = None,
                  valid_assets: set[str] | None = None) -> Draft:
    """Apply a human answer. `evidence` = quote from the answer turn; None means a typed/selected
    fallback, recorded as HUMAN_EDIT so it stays distinguishable from speech-derived values."""
    issue = next((i for i in draft.issues if i.id == issue_id and i.status == IssueStatus.OPEN), None)
    if issue is None:
        raise ReducerError("unknown or already resolved issue")
    if evidence and not all(evidence_valid(e, segments or {}) for e in evidence):
        raise ReducerError("answer evidence does not match the transcript")
    origin = CandidateOrigin.SPEECH if evidence else CandidateOrigin.HUMAN_EDIT
    ev = evidence or []
    rev = draft.revision + 1
    cands = [c.model_copy(deep=True) for c in draft.candidates]
    by_id = {c.id: c for c in cands}
    waived = False
    t = issue.type

    def make(path, value, **kw):
        return FieldCandidate(field_path=path, raw_value=str(value), normalised_value=value, origin=origin,
                              evidence=ev, status=kw.pop("status", CandidateStatus.PROPOSED), **kw)

    if t in (IssueType.AMBIGUOUS_ASSET, IssueType.UNKNOWN_ASSET):
        allowed = set(issue.options) if t == IssueType.AMBIGUOUS_ASSET else (valid_assets or set())
        if choice not in allowed:
            raise ReducerError(f"{choice!r} is not an allowed asset")
        old = next(iter(active(draft, "asset")), None)
        new = make("asset", choice)
        _replace(cands, old, new, rev) if old else cands.append(new.model_copy(update={"revision": rev}))

    elif t in (IssueType.MISSING_UNIT, IssueType.AMBIGUOUS_UNIT):
        old = by_id[issue.key.split("|", 1)[1]]
        if choice != "unknown" and choice not in issue.options and t == IssueType.AMBIGUOUS_UNIT:
            raise ReducerError(f"{choice!r} is not an allowed unit")
        if choice != "unknown" and t == IssueType.MISSING_UNIT and choice not in units_for_kind(old.meta.get("kind")):
            raise ReducerError(f"{choice!r} is not a unit of {old.meta.get('kind')}")
        new = old.model_copy(deep=True, update={"id": new_id(), "origin": origin,
                                                "evidence": old.evidence + ev, "status": CandidateStatus.PROPOSED})
        new.meta = {**old.meta, "unit_ambiguous": False}
        if choice == "unknown":
            new.unit, waived = None, True
            new.meta["unit_status"] = "unknown"
        else:
            new.unit = choice
        _replace(cands, old, new, rev)

    elif t == IssueType.MISSING_VALUE:
        old = by_id[issue.key.split("|", 1)[1]]
        new = old.model_copy(deep=True, update={"id": new_id(), "origin": origin, "evidence": old.evidence + ev})
        new.meta = {**old.meta, "value_missing": False}
        if choice == "unknown":
            new.status, new.normalised_value, waived = CandidateStatus.UNKNOWN, None, True
            new.meta["value_status"] = "unknown"
        else:
            try:
                number = float(choice)
            except ValueError:
                raise ReducerError(f"{choice!r} is not a number") from None
            if not math.isfinite(number) or abs(number) > 1e9:
                raise ReducerError(f"{choice!r} is not a usable number")
            new.normalised_value = int(number) if number == int(number) else number
            new.raw_value, new.status = str(choice), CandidateStatus.PROPOSED
        _replace(cands, old, new, rev)

    elif t == IssueType.AMBIGUOUS_TIME:
        old = by_id[issue.key.split("|", 1)[1]]
        if choice not in ("am", "pm", "unknown"):
            raise ReducerError("time answer must be am, pm or unknown")
        new = old.model_copy(deep=True, update={"id": new_id(), "origin": origin,
                                                "evidence": old.evidence + ev})
        if choice == "unknown":
            new.status, new.normalised_value, waived = CandidateStatus.UNKNOWN, None, True
        else:
            h, m = old.meta["hour_spoken"], old.meta["minute"]
            new.normalised_value = f"{h % 12 + (12 if choice == 'pm' else 0):02d}:{m:02d}"
            new.status = CandidateStatus.PROPOSED
            new.meta = {**old.meta, "am_pm": choice, "am_pm_source": "clarification"}
        _replace(cands, old, new, rev)

    elif t == IssueType.CONFLICTING_OBSERVATION:
        if choice not in issue.options:
            raise ReducerError(f"{choice!r} is not an allowed answer")
        a, b = [by_id[k] for k in issue.key.split("|")[1:3]]
        if issue.options == LEAK_OPTIONS:
            absent = a if a.field_path == "symptom.leakage" else b
            if choice == "leakage_confirmed":
                _replace(cands, absent, make("symptom.leakage", "present"), rev)
            else:  # water seen, source unknown: leakage is neither confirmed nor denied
                _replace(cands, absent, make("symptom.leakage", "not_confirmed", status=CandidateStatus.UNKNOWN), rev)
                waived = True
        else:
            keep_path, keep_value = choice.split("=", 1)
            drop = b if (a.field_path, str(a.normalised_value)) == (keep_path, keep_value) else a
            for c in cands:
                if c.id == drop.id:
                    c.status = CandidateStatus.SUPERSEDED
    elif t == IssueType.MISSING_URGENCY:
        if choice not in ANSWERS:
            raise ReducerError(f"{choice!r} is not an allowed urgency")
        unknown = choice == "unknown"
        quote = ev[0].quote if ev else choice
        new = FieldCandidate(field_path="urgency", raw_value=quote, normalised_value=None if unknown else choice,
                             origin=origin, evidence=ev, status=CandidateStatus.UNKNOWN if unknown else CandidateStatus.PROPOSED)
        old = next((c for c in active(draft, "urgency")), None)
        _replace(cands, old, new, rev) if old else cands.append(new.model_copy(update={"revision": rev}))
        waived = unknown

    elif t == IssueType.MISSING_SYMPTOM:
        path, _, state = choice.partition("=")
        if state != "present" or not path.startswith("symptom.") or path[len("symptom."):] not in symptom_choices():
            raise ReducerError(f"{choice!r} is not an allowed symptom")
        old = next((c for c in active(draft, "symptom") if c.field_path == path), None)  # e.g. an earlier "no smoke"
        new = make(path, "present")
        _replace(cands, old, new, rev) if old else cands.append(new.model_copy(update={"revision": rev}))

    else:
        raise ReducerError(f"{t.value} cannot be answered with a choice; submit a new turn instead")

    return _finish(draft, cands, draft.issues, ev, waived)
