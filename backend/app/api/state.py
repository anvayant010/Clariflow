"""Build the one JSON document a UI needs to draw a session. Read-only: it never changes anything."""
import json

from backend.app.api.schemas import (
    ChoiceOut, FieldOut, NoteOut, QuestionOut, ReceiptOut, ReviewOut, RoleOut, RoutingOut, SessionState, TurnOut, UsageOut,
    WorkOrderOut,
)
from backend.app.domain.issues import active, next_blocker, plan_question
from backend.app.domain.schemas import CandidateStatus, IssueStatus, IssueType, SegmentSource
from backend.app.services import routing, workorder
from backend.app.services.pipeline import MAX_ATTEMPTS, Pipeline
from backend.app.services.view import FieldRow, draft_rows, history_rows, question_view

SOURCE_LABEL = {
    SegmentSource.GNANI_STT.value: "Gnani Prisma (live speech)",
    SegmentSource.TYPED_CLARIFICATION.value: "Typed (not speech)",
    SegmentSource.FIXTURE.value: "FIXTURE transcript (not live speech)",
    SegmentSource.MANUAL_EDIT.value: "Manual edit (not speech)",
}
READBACK_LANGUAGES = ("mr", "hi", "en")
NOTE_TYPES = (IssueType.UNCONFIRMED_CORRECTION, IssueType.POSSIBLE_DROPPED_VALUE, IssueType.OPTIONAL_DETAIL)


def seg_audio_url(session_id: str, seg_id: str) -> str:
    return f"/api/sessions/{session_id}/segments/{seg_id}/audio"


def _field(row: FieldRow, session_id: str, seg_ids: dict[int, str]) -> FieldOut:
    return FieldOut(
        candidate_id=row.candidate_id, label=row.label, value=row.value, state=row.state, origin=row.origin,
        heard=row.heard, understood_as=row.understood_as,
        receipts=[ReceiptOut(turn_index=r.turn_index, source=r.source, source_label=SOURCE_LABEL.get(r.source, r.source),
                             quote=r.quote, marked_html=r.marked_html,
                             audio_url=seg_audio_url(session_id, r.segment_id) if r.audio_ref else None)
                  for r in row.receipts])


def routing_out(payload: dict) -> RoutingOut | None:
    """Labels for the saved/proposed routing, in every language. Old records (no routing key) give None."""
    route = payload.get("routing")
    if not route:
        return None
    level = (payload.get("urgency") or {}).get("level") or "unknown"
    levels = workorder._readback_data()["urgency_levels"]
    return RoutingOut(rule=route["rule"], urgency_labels={lang: levels[level][lang] for lang in READBACK_LANGUAGES},
                      notify=[RoleOut(role=r, labels=routing.role_labels(r)) for r in route["notify"]], note=route.get("note"))


def work_order_out(ctx, row: dict, language: str) -> WorkOrderOut:
    payload = json.loads(row["payload"])
    asset = (payload.get("asset") or {}).get("id")
    location = next((a.synthetic_location for a in ctx.catalogue if a.id == asset), None)
    return WorkOrderOut(id=row["id"], short_id="WO-" + row["id"][:8].upper(), session_id=row["session_id"],
                        language=language, confirmed_revision=row["confirmed_revision"], location=location,
                        readback=workorder.readback(payload, language),
                        readbacks={lang: workorder.readback(payload, lang) for lang in READBACK_LANGUAGES},
                        routing=routing_out(payload), payload=payload, created_at=row["created_at"])


def build_state(ctx, session_id: str) -> SessionState:
    store, catalogue = ctx.store, ctx.catalogue
    sess = store.session(session_id)
    language = sess["language"]
    segments = store.segments(session_id)
    draft = store.draft(session_id)
    row = store.work_order_for(session_id)
    seg_ids = {s.turn_index: s.id for s in segments.values()}

    turns = [TurnOut(index=s.turn_index, source=s.source.value, source_label=SOURCE_LABEL.get(s.source.value, s.source.value),
                     text=s.text, audio_url=seg_audio_url(session_id, s.id) if s.audio_ref else None,
                     language_code=s.language_code) for s in segments.values()]

    question = None
    q = plan_question(draft, catalogue, language)
    if q is not None:
        issue = next_blocker(draft)
        attempts = store.attempts(session_id, issue.key)
        qv = question_view(q, draft, catalogue, language)
        question = QuestionOut(issue_id=qv.issue_id, type=qv.type, text=qv.text, language=qv.language,
                               choices=[ChoiceOut(value=c.value, label=c.label) for c in qv.choices],
                               accepts_number=qv.accepts_number,
                               audio_url=f"/api/sessions/{session_id}/question-audio?q={qv.issue_id}&lang={language}",
                               attempts=attempts, fallback_offered=attempts >= MAX_ATTEMPTS)

    notes = [NoteOut(type=i.type.value, fields=i.field_paths, quotes=[e.quote for e in i.evidence])
             for i in draft.issues if i.status == IssueStatus.OPEN and not i.blocking and i.type in NOTE_TYPES]

    if row is not None:
        status = "saved"
    elif not segments:
        status = "empty"
    elif question is not None:
        status = "needs_answer"
    else:
        status = "ready_for_review"

    review = None
    if status == "ready_for_review":
        r = Pipeline(store, catalogue, language).review(session_id)
        review = ReviewOut(revision=r.revision, language=r.language, readback=r.readback, payload=r.payload,
                           audio_url=f"/api/sessions/{session_id}/review-audio?rev={r.revision}&lang={language}",
                           routing=routing_out(r.payload))

    work_order = None
    if row is not None:
        work_order = work_order_out(ctx, row, language)

    urgency_c = next((c for c in active(draft, "urgency") if c.status != CandidateStatus.UNKNOWN), None)
    urgency_level = str(urgency_c.normalised_value) if urgency_c and urgency_c.normalised_value else None

    left = ctx.limits.remaining(session_id)
    return SessionState(
        session_id=session_id, language=language, status=status, revision=draft.revision, turns=turns,
        fields=[_field(r, session_id, seg_ids) for r in draft_rows(draft, catalogue, segments)],
        history=[_field(r, session_id, seg_ids) for r in history_rows(draft, catalogue, segments)],
        question=question, notes=notes, review=review, work_order=work_order, urgency_level=urgency_level,
        usage=UsageOut(recordings_left=left["recordings"], voice_prompts_left=left["voice_prompts"]))
