"""Application service: one report session from first utterance to confirmed save.

Transcript text only ever flows INTO extraction/answer-interpretation. No text path leads to
`confirm_and_save`; that method is called only by an explicit user action from the UI/API.
Failures (STT error, rejected evidence, uninterpretable answer) leave the stored draft unchanged.
"""
from collections.abc import Callable

from pydantic import BaseModel, Field

from backend.app.adapters.gnani_common import GnaniError
from backend.app.domain.answers import interpret_answer
from backend.app.domain.extractor import cause_from_answer, extract
from backend.app.domain.issues import Question, next_blocker, plan_question
from backend.app.domain.reducer import ReducerError, apply_candidates, resolve_issue
from backend.app.domain.schemas import Asset, Draft, FieldCandidate, IssueType, SegmentSource, WorkOrder
from backend.app.services.workorder import build_payload, evidence_snapshot, readback
from backend.app.storage.store import Store, StoreError


MAX_ATTEMPTS = 3  # after this many answers we could not understand, the UI should lead with the choices


class TurnResult(BaseModel):
    draft: Draft
    question: Question | None = None
    understood: bool = True  # False: the answer could not be mapped to the open question
    error: str | None = None  # e.g. STT failure; the draft is unchanged
    rejected: list[FieldCandidate] = Field(default_factory=list)  # proposals with unsupported evidence
    attempts: int = 0  # answers to the CURRENT question that could not be understood
    fallback_offered: bool = False  # attempts >= MAX_ATTEMPTS: offer the selectable choices / "unknown"


class Review(BaseModel):
    revision: int
    payload: dict
    readback: str
    language: str = "en"


class Pipeline:
    def __init__(self, store: Store, catalogue: list[Asset], language: str = "mr"):
        self.store, self.catalogue, self.language = store, catalogue, language

    def start(self) -> str:
        return self.store.create_session(self.language)

    # ---- turns

    def _result(self, session_id: str, **kw) -> TurnResult:
        draft = self.store.draft(session_id)
        return TurnResult(draft=draft, question=plan_question(draft, self.catalogue, self.language), **kw)

    def submit_turn(self, session_id: str, text: str, source: SegmentSource = SegmentSource.GNANI_STT,
                    **segment_meta) -> TurnResult:
        seg = self.store.add_segment({"session_id": session_id, "text": text, "source": source, **segment_meta})
        proposals = extract(seg, self.catalogue)
        draft = self.store.draft(session_id)
        new, rejected = apply_candidates(draft, proposals, self.store.segments(session_id))
        if new.candidates != draft.candidates or new.issues != draft.issues:
            self.store.save_draft(new)
        return self._result(session_id, rejected=rejected)

    def _transcribe(self, audio: bytes, filename: str, transcriber: Callable[..., object]):
        """(SttResult | None, error | None). `transcriber(audio, filename)` returns an SttResult."""
        try:
            r = transcriber(audio, filename)
        except GnaniError as e:
            return None, f"speech recognition failed ({e.kind})"
        if not r.transcript.strip():
            return None, "no speech recognised"
        return r, None

    def submit_audio(self, session_id: str, audio: bytes, filename: str,
                     transcriber: Callable[..., object], audio_ref: str | None = None) -> TurnResult:
        r, err = self._transcribe(audio, filename, transcriber)
        if r is None:
            return self._result(session_id, error=err)
        return self.submit_turn(session_id, r.transcript, SegmentSource.GNANI_STT, audio_ref=audio_ref,
                                model=r.model, request_id=r.request_id,
                                language_code=getattr(r, "detected_language_code", None))

    def answer_audio(self, session_id: str, audio: bytes, filename: str,
                     transcriber: Callable[..., object], audio_ref: str | None = None) -> TurnResult:
        """A spoken answer to the open question. STT failure/empty -> draft unchanged."""
        r, err = self._transcribe(audio, filename, transcriber)
        if r is None:
            return self._result(session_id, error=err)
        return self.answer(session_id, r.transcript, SegmentSource.GNANI_STT, audio_ref=audio_ref,
                           model=r.model, request_id=r.request_id,
                           language_code=getattr(r, "detected_language_code", None))

    def add_cause(self, session_id: str, text: str, source: SegmentSource = SegmentSource.GNANI_STT,
                  **segment_meta) -> TurnResult:
        """The optional cause, in the person's own words. ONLY the cause is taken from this turn (never an asset,
        symptom or number), it is kept verbatim with its quote, and it replaces an earlier cause."""
        seg = self.store.add_segment({"session_id": session_id, "text": text, "source": source, **segment_meta})
        cause = cause_from_answer(seg)
        if cause is None:
            return self._result(session_id, understood=False)
        draft = self.store.draft(session_id)
        new, rejected = apply_candidates(draft, [cause], self.store.segments(session_id))
        if rejected:
            return self._result(session_id, understood=False)
        self.store.save_draft(new)
        return self._result(session_id)

    def cause_audio(self, session_id: str, audio: bytes, filename: str,
                    transcriber: Callable[..., object], audio_ref: str | None = None) -> TurnResult:
        r, err = self._transcribe(audio, filename, transcriber)
        if r is None:
            return self._result(session_id, error=err)
        return self.add_cause(session_id, r.transcript, SegmentSource.GNANI_STT, audio_ref=audio_ref,
                              model=r.model, request_id=r.request_id,
                              language_code=getattr(r, "detected_language_code", None))

    def answer(self, session_id: str, text: str, source: SegmentSource = SegmentSource.GNANI_STT,
               **segment_meta) -> TurnResult:
        """Interpret `text` as the answer to the open question. Not understood -> draft unchanged."""
        draft = self.store.draft(session_id)
        issue = next_blocker(draft)
        if issue is not None and issue.type == IssueType.MISSING_SYMPTOM:
            # "what did you see?" is answered by describing it: the text is another report turn. If it still
            # contains no symptom, the question stays open and the attempt is counted.
            res = self.submit_turn(session_id, text, source, **segment_meta)
            still = next_blocker(res.draft)
            if still is not None and still.type == IssueType.MISSING_SYMPTOM:
                n = self.store.bump_attempts(session_id, issue.key)
                return self._result(session_id, understood=False, attempts=n, fallback_offered=n >= MAX_ATTEMPTS)
            return res
        seg = self.store.add_segment({"session_id": session_id, "text": text, "source": source, **segment_meta})
        if issue is None:
            return self._result(session_id, understood=False)
        got = interpret_answer(issue, draft, seg, self.catalogue)
        if got is None:
            n = self.store.bump_attempts(session_id, issue.key)
            return self._result(session_id, understood=False, attempts=n, fallback_offered=n >= MAX_ATTEMPTS)
        choice, ev = got
        try:
            new = resolve_issue(draft, issue.id, choice, [ev], self.store.segments(session_id),
                                {a.id for a in self.catalogue})
        except ReducerError:
            n = self.store.bump_attempts(session_id, issue.key)
            return self._result(session_id, understood=False, attempts=n, fallback_offered=n >= MAX_ATTEMPTS)
        self.store.save_draft(new)
        return self._result(session_id)

    def choose(self, session_id: str, issue_id: str, choice: str) -> TurnResult:
        """Typed/selected fallback; recorded as a human edit, not speech."""
        draft = self.store.draft(session_id)
        new = resolve_issue(draft, issue_id, choice, None, None, {a.id for a in self.catalogue})
        self.store.save_draft(new)
        return self._result(session_id)

    # ---- review, confirm, save

    def review(self, session_id: str, language: str | None = None) -> Review:
        draft = self.store.draft(session_id)
        if draft.open_blockers():
            raise StoreError("blockers_open", "resolve open questions first")
        payload = build_payload(draft, self.catalogue)
        lang = language or self.language
        return Review(revision=draft.revision, payload=payload, readback=readback(payload, lang), language=lang)

    def confirm_and_save(self, session_id: str, revision: int, idempotency_key: str) -> WorkOrder:
        """Called ONLY from an explicit user action, carrying the revision the user reviewed."""
        try:
            draft = self.store.draft(session_id, revision)
        except StoreError as e:
            if e.kind == "not_found":  # a revision that never existed was not what the user reviewed
                raise StoreError("stale_revision", f"revision {revision} does not exist") from None
            raise
        self.store.confirm(session_id, revision)
        return self.store.commit(session_id, revision, idempotency_key, build_payload(draft, self.catalogue),
                                 evidence_snapshot(draft))
