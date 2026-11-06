"""HTTP routes. Thin: every rule lives in the Pipeline, the reducer and the database.

Nothing here can create a saved work order except POST /sessions/{id}/confirm, which needs the
revision the user reviewed and a client-made idempotency key; the database refuses it otherwise.
Endpoints are plain `def` so FastAPI runs the blocking provider calls in its thread pool.
"""
import ipaddress
import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Path as PathParam, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from backend.app.api.errors import ApiError
from backend.app.api.schemas import (
    ChooseIn, CompareTextIn, ConfirmIn, LanguageIn, LookupIn, NewSession, SessionState, TextIn, TurnOutcome,
)
from backend.app.api.state import build_state, work_order_out
from backend.app.domain.issues import next_blocker, plan_question
from backend.app.domain.reducer import ReducerError
from backend.app.domain.schemas import SegmentSource
from backend.app.domain.urgency import LEVELS
from backend.app.services import audioconv, compare, evaluation as ev, routing, speech, workorder
from backend.app.services.evalreport import build as build_eval_report
from backend.app.services.pipeline import Pipeline
from backend.app.storage.store import StoreError

ROOT = Path(__file__).resolve().parents[3]
UUID_RE = r"^[0-9a-fA-F-]{36}$"
LANGUAGES = [{"code": "mr", "label": "मराठी"}, {"code": "hi", "label": "हिन्दी"}, {"code": "en", "label": "English"}]


def SessionId():  # a fresh parameter object per endpoint
    return PathParam(pattern=UUID_RE)


def ctx_of(request: Request):
    return request.app.state.ctx


def client_ip(request: Request) -> str:
    """The visitor's address. Behind a host's proxy the connection address is the proxy's, so every visitor would share
    one set of per-visitor limits. With TRUSTED_PROXY_HOPS=n the address is the n-th entry counted from the RIGHT of
    X-Forwarded-For: those entries were added by our own proxies. Anything a visitor typed sits further left and is
    never used, so it cannot be spoofed to dodge the limits."""
    direct = request.client.host if request.client else "unknown"
    hops = ctx_of(request).settings.trusted_proxy_hops
    header = request.headers.get("x-forwarded-for", "")
    if hops <= 0 or not header:
        return direct
    parts = [p.strip() for p in header.split(",") if p.strip()]
    if len(parts) < hops:
        return direct
    candidate = parts[-hops]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return direct


def rate_limit(request: Request) -> None:
    ctx_of(request).limits.check_rate(client_ip(request))


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api", dependencies=[Depends(rate_limit)])
    def pipe(ctx, session_id: str) -> Pipeline:
        return Pipeline(ctx.store, ctx.catalogue, ctx.store.session(session_id)["language"])

    def not_saved(ctx, session_id: str) -> None:
        if ctx.store.work_order_for(session_id) is not None:
            raise StoreError("already_saved", session_id)

    def read_upload(file: UploadFile) -> audioconv.Clip:
        return audioconv.to_wav(file.file.read(audioconv.MAX_BYTES + 1))

    # ------------------------------------------------------------ meta

    @router.get("/visitor")
    def visitor(request: Request):
        """Which per-visitor bucket this request falls in (a short one-way hash, not an address). A deployment check: two
        devices on different networks must show different values, or the proxy setting is wrong."""
        return {"visitor": ctx_of(request).limits.ip_key(client_ip(request))}

    @router.get("/health")
    def health():
        return {"ok": True}

    @router.get("/config")
    def config(request: Request):
        ctx = ctx_of(request)
        s = ctx.settings
        return {
            "app": "Clariflow", "synthetic_demonstration": True, "languages": LANGUAGES,
            "speech_configured": ctx.speech_configured, "fixture_allowed": s.allow_fixture,
            "assets": [{"id": a.id, "name": a.display_name, "type": a.asset_type, "location": a.synthetic_location}
                       for a in ctx.catalogue],
            "limits": {"max_clip_seconds": audioconv.MAX_SECONDS, "recordings_per_report": s.session_audio_cap,
                       "voice_prompts_per_report": s.session_tts_cap},
            "routing": {
                "simulated": True, "emergency_notice": routing.emergency_notice(),
                "rules": [{"level": lv, "labels": workorder._readback_data()["urgency_levels"][lv],
                           "notify": [{"role": r, "labels": routing.role_labels(r)} for r in routing.table()["levels"][lv]["notify"]],
                           "note": routing.table()["levels"][lv].get("note")}
                          for lv in (*LEVELS, "unknown")],
            },
            "speech": {"stt": "Gnani Prisma " + s.gnani_stt_model, "tts": "Gnani Timbre " + s.gnani_tts_model,
                       "stt_config": "format=codemix with keyterms (our own asset IDs) and a short topic"},
        }

    # ------------------------------------------------------------ sessions

    @router.post("/sessions", status_code=201, response_model=SessionState)
    def create_session(body: NewSession, request: Request):
        ctx = ctx_of(request)
        ctx.limits.take_session(client_ip(request))
        sid = ctx.store.create_session(body.language)
        return build_state(ctx, sid)

    @router.get("/sessions/{sid}", response_model=SessionState)
    def get_session(request: Request, sid: str = SessionId()):
        return build_state(ctx_of(request), sid)

    @router.post("/sessions/{sid}/language", response_model=SessionState)
    def set_language(body: LanguageIn, request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        ctx.store.session(sid)
        ctx.store.set_language(sid, body.language)
        return build_state(ctx, sid)

    # ------------------------------------------------------------ turns

    def outcome(ctx, sid: str, mode_used: str, res, before: int) -> TurnOutcome:
        segs = list(ctx.store.segments(sid).values())
        heard = segs[-1].text if len(segs) > before else ""
        return TurnOutcome(mode_used=mode_used, understood=res.understood, heard=heard, error=res.error,
                           attempts=res.attempts, fallback_offered=res.fallback_offered, state=build_state(ctx, sid))

    def effective_mode(ctx, sid: str, mode: str) -> str:
        """An 'answer' with no open question is just more detail about the incident."""
        if mode == "cause":
            return "cause"
        return "answer" if mode == "answer" and next_blocker(ctx.store.draft(sid)) is not None else "report"

    @router.post("/sessions/{sid}/audio", response_model=TurnOutcome)
    def post_audio(request: Request, file: UploadFile = File(...), mode: str = Form("report"), sid: str = SessionId()):
        ctx = ctx_of(request)
        if mode not in ("report", "answer", "cause"):
            raise ApiError(422, "invalid_request", "mode must be report, answer or cause")
        ctx.store.session(sid)
        not_saved(ctx, sid)
        clip = read_upload(file)  # AudioError -> 422 before any provider call or quota use
        ctx.limits.take_stt(sid, client_ip(request))
        ref = speech.save_audio(sid, clip.wav, "clip.wav")
        used = mode if mode == "cause" else effective_mode(ctx, sid, mode)
        p, before = pipe(ctx, sid), len(ctx.store.segments(sid))
        transcriber = lambda audio, name: ctx.ears.transcribe(audio)  # noqa: E731
        run = {"answer": p.answer_audio, "cause": p.cause_audio}.get(used, p.submit_audio)
        return outcome(ctx, sid, used, run(sid, clip.wav, "clip.wav", transcriber, audio_ref=ref), before)

    @router.post("/sessions/{sid}/text", response_model=TurnOutcome)
    def post_text(body: TextIn, request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        ctx.store.session(sid)
        not_saved(ctx, sid)
        if body.source == "fixture" and not ctx.settings.allow_fixture:
            raise ApiError(403, "fixture_disabled", "Pasted transcripts are disabled on this server.")
        source = SegmentSource.FIXTURE if body.source == "fixture" else SegmentSource.TYPED_CLARIFICATION
        used = body.mode if body.mode == "cause" else effective_mode(ctx, sid, body.mode)
        p, before = pipe(ctx, sid), len(ctx.store.segments(sid))
        if used == "cause":
            res = p.add_cause(sid, body.text, source)
        else:
            res = p.answer(sid, body.text, source) if used == "answer" else p.submit_turn(sid, body.text, source)
        return outcome(ctx, sid, used, res, before)

    @router.post("/sessions/{sid}/choose", response_model=SessionState)
    def choose(body: ChooseIn, request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        not_saved(ctx, sid)
        try:
            pipe(ctx, sid).choose(sid, body.issue_id, body.choice)
        except ReducerError:
            raise ApiError(422, "invalid_choice", "That answer is not valid for the current question.") from None
        return build_state(ctx, sid)

    # ------------------------------------------------------------ audio out

    def voice_response(request: Request, sid: str, text: str, language: str) -> Response:
        ctx = ctx_of(request)
        if not ctx.voice.cached(text, language):
            ctx.limits.take_tts(sid, client_ip(request))
        audio = ctx.voice.speak(text, language)
        return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})

    @router.get("/sessions/{sid}/question-audio")
    def question_audio(request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        language = ctx.store.session(sid)["language"]
        q = plan_question(ctx.store.draft(sid), ctx.catalogue, language)
        if q is None:
            raise ApiError(404, "no_question", "There is no open question.")
        return voice_response(request, sid, q.text, language)

    @router.get("/sessions/{sid}/review-audio")
    def review_audio(request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        rev = pipe(ctx, sid).review(sid)  # StoreError(blockers_open) -> 409
        return voice_response(request, sid, rev.readback, rev.language)

    @router.get("/sessions/{sid}/work-order-audio")
    def work_order_audio(request: Request, lang: str = Query(pattern="^(mr|hi|en)$"), sid: str = SessionId()):
        """The saved work order read aloud in the chosen language (same record, fixed templates)."""
        ctx = ctx_of(request)
        row = ctx.store.work_order_for(sid)
        if row is None:
            raise ApiError(404, "no_work_order", "This report has not been saved.")
        return voice_response(request, sid, workorder.readback(json.loads(row["payload"]), lang), lang)

    @router.get("/sessions/{sid}/segments/{seg}/audio")
    def segment_audio(request: Request, seg: str = PathParam(pattern=UUID_RE), sid: str = SessionId()):
        ctx = ctx_of(request)
        segment = ctx.store.segments(sid).get(seg)
        data = speech.load_audio(segment.audio_ref) if segment else None
        if data is None:
            raise ApiError(404, "no_audio", "There is no recording for that turn.")
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "private, max-age=3600"})

    # ------------------------------------------------------------ confirm

    @router.post("/sessions/{sid}/confirm", response_model=SessionState)
    def confirm(body: ConfirmIn, request: Request, sid: str = SessionId()):
        ctx = ctx_of(request)
        pipe(ctx, sid).confirm_and_save(sid, body.revision, body.idempotency_key)
        return build_state(ctx, sid)

    # ------------------------------------------------------------ saved work orders (read-only)

    @router.post("/work-orders/lookup")
    def lookup_work_orders(body: LookupIn, request: Request):
        """The saved work orders for the report ids the browser remembers. There is no 'list everything':
        a report id is an unguessable UUID, so only the browser that made a report can ask for it."""
        ctx = ctx_of(request)
        out = []
        for sid in dict.fromkeys(body.session_ids):  # de-duplicated, order kept
            if not re.match(UUID_RE, sid):
                raise ApiError(422, "invalid_request", "Invalid report id.")
            row = ctx.store.work_order_for(sid)
            if row is not None:
                out.append(work_order_out(ctx, row, ctx.store.session(sid)["language"]))
        out.sort(key=lambda w: w.created_at, reverse=True)
        return {"work_orders": out}

    # ------------------------------------------------------------ evidence of quality

    @router.get("/break")
    def break_mode(request: Request):
        ctx = ctx_of(request)
        if "break" not in ctx.cache:
            ctx.cache["break"] = ev.run_all_break(ctx.catalogue)
        return {"mode": "recorded Prisma v3.0 transcripts (2026-11-04), re-run through the production pipeline now; no API calls",
                "naive_definition": ev.NAIVE_DEFINITION, "scenarios": ctx.cache["break"]}

    def latest_eval_files() -> list[Path]:
        return sorted((ROOT / "evaluation" / "results").glob("eval_*.json"))

    @router.get("/evaluation")
    def evaluation_report(request: Request):
        ctx = ctx_of(request)
        files = latest_eval_files()
        if files:
            data = json.loads(files[-1].read_text(encoding="utf-8"))
        else:
            data = ctx.cache.setdefault("eval", build_eval_report(ctx.catalogue))
        return {"historical": True, "note": "Results of a past run on the date shown, not recomputed on request.", **data}

    @router.get("/evaluation/chart.svg")
    def evaluation_chart():
        svgs = sorted((ROOT / "evaluation" / "results").glob("eval_*.svg"))
        if not svgs:
            raise ApiError(404, "no_chart", "No evaluation chart has been generated yet.")
        return FileResponse(svgs[-1], media_type="image/svg+xml")

    # ------------------------------------------------------------ naive vs Clariflow

    def clip_by_id(clip_id: str) -> dict:
        clip = next((c for c in ev.load_clips() if c["id"] == clip_id), None)
        if clip is None:
            raise ApiError(404, "no_clip", "Unknown demo clip.")
        return clip

    @router.get("/demo-clips")
    def demo_clips():
        return {"note": "Recordings of the developer's own voice, quiet room; scripts are fictional.",
                "clips": [{"id": c["id"], "mix": c["mix"], "script": c["script"], "transcribed_on": c["transcribed_on"],
                           "audio_url": f"/api/demo-clips/{c['id']}/audio"} for c in ev.load_clips()]}

    @router.get("/demo-clips/{clip_id}/audio")
    def demo_clip_audio(clip_id: str = PathParam(pattern=r"^[A-Z]{2,3}[0-9]$")):
        clip_by_id(clip_id)
        path = ROOT / "fixtures" / "audio" / f"{clip_id}.m4a"
        if not path.is_file():
            raise ApiError(404, "no_audio", "That recording is not available.")
        return FileResponse(path, media_type="audio/mp4")

    def live_compare(request: Request, wav: bytes, truth: dict | None) -> dict:
        ctx = ctx_of(request)
        ctx.limits.take_stt(None, client_ip(request), n=2)  # the naive and the Clariflow transcription
        naive_t, clari_t = ctx.ears.transcribe(wav, plain=True), ctx.ears.transcribe(wav, plain=False)
        if not naive_t.transcript.strip() or not clari_t.transcript.strip():
            raise ApiError(422, "no_speech", "No speech was recognised in that recording.")
        return compare.compare(naive_t.transcript, clari_t.transcript, ctx.catalogue, "live", truth)

    @router.post("/compare/demo/{clip_id}")
    def compare_demo(request: Request, live: bool = False, clip_id: str = PathParam(pattern=r"^[A-Z]{2,3}[0-9]$")):
        ctx = ctx_of(request)
        clip = clip_by_id(clip_id)
        if not live:
            t = clip["transcripts"]
            result = compare.compare(t["plain_verbatim"], t["codemix_keyterms"], ctx.catalogue, "recorded", clip["truth"])
            result["recorded_on"] = clip["transcribed_on"]
            return result
        path = ROOT / "fixtures" / "audio" / f"{clip_id}.m4a"
        if not path.is_file():
            raise ApiError(404, "no_audio", "That recording is not available.")
        return live_compare(request, audioconv.to_wav(path.read_bytes()).wav, clip["truth"])

    @router.post("/compare/audio")
    def compare_audio(request: Request, file: UploadFile = File(...)):
        ctx = ctx_of(request)
        return live_compare(request, read_upload(file).wav, None)

    @router.post("/compare/text")
    def compare_text(body: CompareTextIn, request: Request):
        ctx = ctx_of(request)
        return compare.compare(body.text, body.text, ctx.catalogue, "typed")

    return router
