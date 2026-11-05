"""Response and request models. Internal paths (audio_ref) never appear here; clients get URLs."""
from typing import Literal

from pydantic import BaseModel, Field


class ReceiptOut(BaseModel):
    turn_index: int
    source: str
    source_label: str
    quote: str
    marked_html: str  # the transcript with the quote wrapped in <mark>; text is HTML-escaped by the server
    audio_url: str | None = None


class FieldOut(BaseModel):
    candidate_id: str
    label: str
    value: str
    state: str  # ok | needs_answer | unknown | history
    origin: str  # speech | typed / selected
    receipts: list[ReceiptOut] = Field(default_factory=list)
    heard: str | None = None  # the words as spoken or typed, when the language handling converted them ...
    understood_as: str | None = None  # ... and what they became ("पंधरा" -> "15")


class TurnOut(BaseModel):
    index: int
    source: str
    source_label: str
    text: str
    audio_url: str | None = None
    language_code: str | None = None


class ChoiceOut(BaseModel):
    value: str
    label: str


class QuestionOut(BaseModel):
    issue_id: str
    type: str
    text: str
    language: str
    choices: list[ChoiceOut]
    accepts_number: bool = False
    audio_url: str
    attempts: int = 0
    fallback_offered: bool = False


class NoteOut(BaseModel):
    type: str  # unconfirmed_correction | possible_dropped_value | optional_detail
    fields: list[str]
    quotes: list[str] = Field(default_factory=list)


class RoleOut(BaseModel):
    role: str
    labels: dict[str, str]  # the role's name in each language


class RoutingOut(BaseModel):
    """SIMULATED routing: who would be told. Nothing is ever sent."""
    simulated: bool = True
    rule: str  # the urgency level whose rule applied ("unknown" when the person was not sure)
    urgency_labels: dict[str, str]  # the person's urgency answer in each language
    notify: list[RoleOut]
    note: str | None = None


class ReviewOut(BaseModel):
    revision: int
    language: str
    readback: str
    payload: dict
    audio_url: str
    routing: RoutingOut | None = None


class WorkOrderOut(BaseModel):
    id: str
    short_id: str  # "WO-D4D6EE98": the readable number (first 8 characters of the id)
    session_id: str
    language: str
    confirmed_revision: int
    location: str | None = None  # from the fictional plant catalogue
    readback: str  # the read-back the person heard and confirmed, in the report's language
    readbacks: dict[str, str]  # the SAME saved record in every supported language (fixed templates, no new content)
    routing: RoutingOut | None = None  # None for records saved before urgency existed
    payload: dict
    created_at: str


class UsageOut(BaseModel):
    recordings_left: int
    voice_prompts_left: int


class SessionState(BaseModel):
    session_id: str
    language: str
    status: Literal["empty", "needs_answer", "ready_for_review", "saved"]
    revision: int
    synthetic_demonstration: bool = True
    turns: list[TurnOut]
    fields: list[FieldOut]
    history: list[FieldOut]
    question: QuestionOut | None = None
    notes: list[NoteOut]
    review: ReviewOut | None = None
    work_order: WorkOrderOut | None = None
    urgency_level: str | None = None  # the person's stated level, if any ("emergency" shows the safety notice)
    usage: UsageOut


class TurnOutcome(BaseModel):
    mode_used: Literal["report", "answer", "cause"]
    understood: bool
    heard: str = ""
    error: str | None = None
    attempts: int = 0
    fallback_offered: bool = False
    state: SessionState


class NewSession(BaseModel):
    language: Literal["mr", "hi", "en"] = "mr"


class LanguageIn(BaseModel):
    language: Literal["mr", "hi", "en"]


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    mode: Literal["report", "answer", "cause"] = "report"
    source: Literal["typed", "fixture"] = "typed"


class ChooseIn(BaseModel):
    issue_id: str = Field(min_length=1, max_length=64)
    choice: str = Field(min_length=1, max_length=64)


class ConfirmIn(BaseModel):
    revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class LookupIn(BaseModel):
    session_ids: list[str] = Field(min_length=1, max_length=50, description="reports this browser created")


class CompareTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
