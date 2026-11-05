"""Presentation helpers: turn a Draft into plain rows the UI can show. No decisions are made here."""
import html
import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from backend.app.domain.issues import Question, active
from backend.app.domain.lexicon import norm
from backend.app.domain.normaliser import default_lexicon
from backend.app.domain.reducer import symptom_choices
from backend.app.domain.urgency import ANSWERS, LABEL_EN
from backend.app.services.timefmt import clock12
from backend.app.domain.schemas import (
    Asset, CandidateOrigin, CandidateStatus, Draft, EvidenceRef, FieldCandidate, IssueType, TranscriptSegment,
)

FIELD_LABELS = {
    "asset": "Asset", "time": "Reported time", "cause": "Cause", "immediate_action": "Immediate action", "urgency": "Urgency",
}
CONCEPT_LABELS = {"stopped": "Stopped", "running": "Running", "vibration": "Vibration", "noise": "Noise",
                  "leakage": "Leakage", "water": "Water seen", "heat": "Heat", "smoke": "Smoke", "fire": "Fire",
                  "broken": "Broken", "jammed": "Jammed", "smell": "Smell", "sparks": "Sparks"}


class Receipt(BaseModel):
    """One piece of evidence: the exact quote, where it sits in the transcript, and which clip it came from."""
    segment_id: str
    turn_index: int
    quote: str
    marked_html: str  # the full segment text with the quote highlighted (escaped)
    audio_ref: str | None = None
    source: str


class FieldRow(BaseModel):
    candidate_id: str
    label: str
    value: str
    state: str  # "ok" | "needs_answer" | "unknown" | "history"
    origin: str  # "speech" | "typed / selected"
    receipts: list[Receipt] = Field(default_factory=list)
    heard: str | None = None  # the words as spoken/typed ("पंधरा") ...
    understood_as: str | None = None  # ... and what they were turned into ("15"); None when nothing was converted


def mark(text: str, start: int | None, end: int | None) -> str:
    if start is None or end is None or not (0 <= start < end <= len(text)):
        return html.escape(text)
    return f"{html.escape(text[:start])}<mark>{html.escape(text[start:end])}</mark>{html.escape(text[end:])}"


def receipts_for(evidence: list[EvidenceRef], segments: dict[str, TranscriptSegment]) -> list[Receipt]:
    out = []
    for e in evidence:
        seg = segments.get(e.segment_id)
        if seg is None:
            continue
        out.append(Receipt(segment_id=seg.id, turn_index=seg.turn_index, quote=e.quote,
                           marked_html=mark(seg.text, e.start_char, e.end_char),
                           audio_ref=seg.audio_ref, source=seg.source.value))
    return out


def _label(path: str) -> str:
    head, _, rest = path.partition(".")
    if head == "symptom":
        return CONCEPT_LABELS.get(rest, rest.title())
    if head == "measurement":
        return rest.title()
    return FIELD_LABELS.get(path, path)


def _same(a: str, b: str) -> bool:
    return norm(a) == norm(b)


def conversion(c: FieldCandidate, catalogue: list[Asset]) -> tuple[str, str] | None:
    """(words as heard, what they became), only when the language handling actually changed something:
    "पंधरा" -> "15", "साडेदहा वाजता" -> "10:30", "पी ट्वेल्व" -> "P-12", "धूर" -> "Smoke". "P-12" -> "P-12" is not shown."""
    raw = (c.raw_value or "").strip()
    if c.origin != CandidateOrigin.SPEECH or not raw:
        return None  # a typed/selected value has no spoken words behind it
    head = c.field_path.split(".")[0]
    if head == "asset":
        if c.status == CandidateStatus.NEEDS_CLARIFICATION or not c.normalised_value:
            return None
        to = str(c.normalised_value)
        if norm(to) in norm(raw):
            return None  # the ID itself was spoken ("C-04 / compressor"): nothing was converted
    elif head == "time":
        if c.status != CandidateStatus.PROPOSED or not c.normalised_value:
            return None
        to = clock12(c.normalised_value)
    elif head == "measurement":
        if c.meta.get("value_missing") or c.normalised_value is None:
            return None
        to = f"{c.normalised_value} {c.unit}".strip() if c.unit and not c.meta.get("unit_ambiguous") else str(c.normalised_value)
    elif head == "urgency":
        if c.status != CandidateStatus.PROPOSED or not c.normalised_value:
            return None
        to = LABEL_EN.get(str(c.normalised_value), str(c.normalised_value))
    elif head == "symptom":
        label = _label(c.field_path)
        to = label if c.normalised_value == "present" else f"{label}: not present" if c.normalised_value == "absent" else label
    else:
        return None  # a cause is kept exactly as said; there is nothing to convert
    return None if _same(raw, to) else (raw, to)


def _value(c: FieldCandidate, catalogue: list[Asset], by_id: dict[str, FieldCandidate]) -> tuple[str, str]:
    """(display value, state)."""
    head = c.field_path.split(".")[0]
    if head == "asset":
        if c.status == CandidateStatus.NEEDS_CLARIFICATION:
            return "unclear: " + " or ".join(c.meta.get("options", [])), "needs_answer"
        a = next((a for a in catalogue if a.id == c.normalised_value), None)
        return (f"{a.id} · {a.display_name}" if a else str(c.normalised_value)), "ok"
    if head == "time":
        if c.status == CandidateStatus.UNKNOWN:
            return "unknown", "unknown"
        old = by_id.get(c.meta.get("corrected_from_id"))
        fix = f"  (corrected from {clock12(old.normalised_value) if old.normalised_value else old.raw_value})" if old else ""
        if c.status == CandidateStatus.NEEDS_CLARIFICATION or not c.normalised_value:
            return f"“{c.raw_value}” — AM or PM not stated{fix}", "needs_answer"
        return f"{clock12(c.normalised_value)}{fix}", "ok"
    if head == "measurement":
        old = by_id.get(c.meta.get("corrected_from_id"))
        fix = f"  (corrected from {old.normalised_value})" if old else ""
        if c.meta.get("old_value_missing"):
            fix += "  (a correction was heard; the earlier value was not transcribed)"
        if c.meta.get("value_missing"):
            return f"“{c.raw_value}” — number could not be read", "needs_answer"
        if c.normalised_value is None:
            return "value unknown", "unknown"
        if c.meta.get("unit_ambiguous"):
            return f"{c.normalised_value} “{c.meta.get('raw_unit')}” — exact unit unclear{fix}", "needs_answer"
        if c.unit:
            return f"{c.normalised_value} {c.unit}{fix}", "ok"
        if c.meta.get("unit_status") == "unknown":
            return f"{c.normalised_value} (unit unknown){fix}", "unknown"
        return f"{c.normalised_value} — unit not stated{fix}", "needs_answer"
    if head == "symptom":
        return {"present": "present", "absent": "reported NOT present",
                "not_confirmed": "not confirmed (source unknown)"}.get(str(c.normalised_value), str(c.normalised_value)), \
            ("unknown" if c.status == CandidateStatus.UNKNOWN else "ok")
    if head == "urgency":
        if c.status == CandidateStatus.UNKNOWN or c.normalised_value is None:
            return "not sure (stated by the reporter)", "unknown"
        return LABEL_EN.get(str(c.normalised_value), str(c.normalised_value)), "ok"
    if head == "cause":
        if c.status == CandidateStatus.UNKNOWN or c.normalised_value is None:
            return "unknown (stated by the reporter)", "unknown"
        return f"{c.normalised_value} (as reported)", "ok"
    return str(c.normalised_value).replace("_", " "), "ok"


def draft_rows(draft: Draft, catalogue: list[Asset], segments: dict[str, TranscriptSegment]) -> list[FieldRow]:
    """Active fields, in a stable reading order. Superseded values are listed by `history_rows`."""
    by_id = {c.id: c for c in draft.candidates}
    order = ["asset", "urgency", "symptom", "measurement", "time", "cause", "immediate_action"]
    rows = []
    for c in sorted(active(draft), key=lambda c: order.index(c.field_path.split(".")[0])
                    if c.field_path.split(".")[0] in order else 99):
        value, state = _value(c, catalogue, by_id)
        rows.append(FieldRow(candidate_id=c.id, label=_label(c.field_path), value=value, state=state,
                             origin="speech" if c.origin == CandidateOrigin.SPEECH else "typed / selected",
                             receipts=receipts_for(c.evidence, segments), **_heard(c, catalogue)))
    return rows


def _heard(c: FieldCandidate, catalogue: list[Asset]) -> dict:
    conv = conversion(c, catalogue)
    return {"heard": conv[0], "understood_as": conv[1]} if conv else {}


def history_rows(draft: Draft, catalogue: list[Asset], segments: dict[str, TranscriptSegment]) -> list[FieldRow]:
    by_id = {c.id: c for c in draft.candidates}
    rows = []
    for c in draft.candidates:
        if c.status != CandidateStatus.SUPERSEDED:
            continue
        value, _ = _value(c, catalogue, by_id)
        rows.append(FieldRow(candidate_id=c.id, label=_label(c.field_path), value=value, state="history",
                             origin="speech" if c.origin == CandidateOrigin.SPEECH else "typed / selected",
                             receipts=receipts_for(c.evidence, segments), **_heard(c, catalogue)))
    return rows


# ---------------------------------------------------------------- the open question, ready for a UI

_READBACK = Path(__file__).resolve().parents[1] / "lexicon" / "readback.json"
UNIT_ORDER = ["PSI", "bar", "kPa", "MPa", "°C", "°F", "RPM"]


@lru_cache(maxsize=1)
def _labels() -> dict:
    return json.loads(_READBACK.read_text(encoding="utf-8"))


class Choice(BaseModel):
    value: str
    label: str


class QuestionView(BaseModel):
    issue_id: str
    type: str
    text: str
    language: str
    choices: list[Choice]
    accepts_number: bool = False  # the answer may be a number (an unreadable value)


def _units_for(kind: str | None) -> list[str]:
    units = {u["canonical"] for u in default_lexicon().units.values() if u["kind"] == kind and not u["ambiguous"]}
    return sorted(units, key=lambda u: (UNIT_ORDER.index(u) if u in UNIT_ORDER else 99, u))


def question_view(q: Question, draft: Draft, catalogue: list[Asset], language: str) -> QuestionView:
    """The question plus the selectable answers (the typed/selected fallback; voice answers go through answers.py)."""
    labels = _labels()
    names = {a.id: f"{a.id} · {a.display_name}" for a in catalogue}
    issue = next(i for i in draft.issues if i.id == q.issue_id)

    def label(value: str) -> str:
        if q.issue_type == IssueType.MISSING_SYMPTOM and value.startswith("symptom."):
            concept = value.split("=", 1)[0].split(".", 1)[1]
            return labels["symptoms"].get(concept, {}).get(language, concept)
        if value in names:
            return names[value]
        if value in labels["choices"]:
            return labels["choices"][value][language]
        if "=" in value and value.startswith("symptom."):
            path, state = value.split("=", 1)
            concept = labels["symptoms"].get(path.split(".", 1)[1], {}).get(language, path)
            return f"{concept}: {labels['states'].get(state, {}).get(language, state)}"
        return value

    values = list(q.options)
    if q.issue_type == IssueType.MISSING_SYMPTOM:  # "what did you see?": the symptoms we know, to tap
        values = [f"symptom.{c}=present" for c in symptom_choices()]
    if q.issue_type == IssueType.MISSING_URGENCY:  # the four levels, least to most urgent, then "I don't know"
        values = list(ANSWERS)
    if q.issue_type == IssueType.UNKNOWN_ASSET:  # nothing was recognised: let the person pick from the plant list
        values = [a.id for a in catalogue]
    if q.issue_type in (IssueType.MISSING_UNIT, IssueType.AMBIGUOUS_UNIT, IssueType.MISSING_VALUE):
        cand = next(c for c in draft.candidates if issue.key.endswith(c.id))
        if q.issue_type == IssueType.MISSING_UNIT:
            values = _units_for(cand.meta.get("kind")) + ["unknown"]
        elif q.issue_type == IssueType.MISSING_VALUE:
            values = ["unknown"]
    return QuestionView(issue_id=q.issue_id, type=q.issue_type.value, text=q.text, language=language,
                        choices=[Choice(value=v, label=label(v)) for v in values],
                        accepts_number=q.issue_type == IssueType.MISSING_VALUE)
