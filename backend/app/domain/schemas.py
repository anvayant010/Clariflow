"""Core domain models. Language-agnostic: nothing here branches on mr/hi/en."""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- enums ----------

class SegmentSource(str, Enum):
    GNANI_STT = "gnani_stt"
    TYPED_CLARIFICATION = "typed_clarification"
    MANUAL_EDIT = "manual_transcript_edit"
    FIXTURE = "fixture"  # development only; never presented as live transcription


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    NEEDS_CLARIFICATION = "needs_clarification"
    CONFIRMED = "confirmed"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class CandidateOrigin(str, Enum):
    SPEECH = "speech"  # derived from a transcript segment
    HUMAN_EDIT = "human_edit"  # typed/selected by the user, kept distinguishable


class IssueType(str, Enum):
    AMBIGUOUS_ASSET = "ambiguous_asset"
    UNKNOWN_ASSET = "unknown_asset"
    CONFLICTING_OBSERVATION = "conflicting_observation"
    MISSING_UNIT = "missing_unit"
    AMBIGUOUS_UNIT = "ambiguous_unit"
    MISSING_VALUE = "missing_value"  # a unit/measure was heard but the number could not be read
    POSSIBLE_DROPPED_VALUE = "possible_dropped_value"  # a correction was heard but the earlier value was not
    AMBIGUOUS_TIME = "ambiguous_time"
    UNCONFIRMED_CORRECTION = "unconfirmed_correction"
    MISSING_SYMPTOM = "missing_symptom"
    MISSING_URGENCY = "missing_urgency"  # "how urgent is this?": asked last, answered by the person, never guessed
    OPTIONAL_DETAIL = "optional_detail"


class IssueStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED_UNKNOWN = "waived_unknown"  # user explicitly accepted "unknown"


class SessionStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_REVIEW = "ready_for_review"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SAVED = "saved"


# ---------- catalogue ----------

class Asset(BaseModel):
    id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    asset_type: str
    synthetic_location: str


# ---------- transcript + evidence ----------

class TranscriptSegment(BaseModel):
    """Immutable once stored. Edits create a new segment, never mutate text."""

    model_config = {"frozen": True}

    id: str = Field(default_factory=new_id)
    session_id: str
    turn_index: int
    text: str
    source: SegmentSource
    language_code: str | None = None  # e.g. mr-IN, as sent to / reported by STT
    model: str | None = None  # e.g. prisma-v3.0
    request_id: str | None = None
    audio_ref: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class EvidenceRef(BaseModel):
    segment_id: str
    quote: str
    start_char: int | None = None  # None when offsets cannot be verified
    end_char: int | None = None


# ---------- draft ----------

class FieldCandidate(BaseModel):
    id: str = Field(default_factory=new_id)
    field_path: str  # e.g. "asset_id", "measurements.pressure", "cause"
    raw_value: str | None = None  # exactly as heard
    normalised_value: str | float | int | None = None
    unit: str | None = None  # never inferred; None means not stated
    origin: CandidateOrigin = CandidateOrigin.SPEECH
    evidence: list[EvidenceRef] = Field(default_factory=list)
    status: CandidateStatus = CandidateStatus.PROPOSED
    replaces_candidate_id: str | None = None
    revision: int = 0
    meta: dict = Field(default_factory=dict)  # structured extras, e.g. time parts, unit_ambiguous


class Issue(BaseModel):
    id: str = Field(default_factory=new_id)
    type: IssueType
    field_paths: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    blocking: bool = True
    status: IssueStatus = IssueStatus.OPEN
    question: str | None = None
    resolution_evidence: list[EvidenceRef] = Field(default_factory=list)
    created_revision: int = 0
    resolved_revision: int | None = None
    key: str = ""  # stable identity across revisions (type + involved candidates)
    options: list[str] = Field(default_factory=list)  # allowed answers, e.g. asset ids


class Draft(BaseModel):
    """One immutable-per-revision view of the report under construction."""

    session_id: str
    revision: int = 0
    candidates: list[FieldCandidate] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)

    def open_blockers(self) -> list[Issue]:
        return [i for i in self.issues if i.blocking and i.status == IssueStatus.OPEN]


# ---------- saved record ----------

class WorkOrder(BaseModel):
    id: str = Field(default_factory=new_id)
    session_id: str
    confirmed_revision: int
    payload: dict
    evidence_snapshot: list[EvidenceRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
