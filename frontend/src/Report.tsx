import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, newKey } from "./api";
import { parseMarked } from "./marked";
import type { AppConfig, Field, Lang, Note, Question, SessionState, TurnOutcome } from "./types";
import { Banner, PlayButton, RecordButton, Spinner, TypeBox } from "./ui";
import { EmergencyNotice, RoutingLine, RoutingRules } from "./Routing";
import { WorkOrderCard } from "./WorkOrderCard";
import { rememberSaved, summarise } from "./workorder";

const STORE_KEY = "clariflow.session";
const remember = (id: string | null) => {
  try {
    if (id) localStorage.setItem(STORE_KEY, id);
    else localStorage.removeItem(STORE_KEY);
  } catch {
    /* storage can be blocked; the app works without it */
  }
};
const recall = (): string | null => {
  try {
    return localStorage.getItem(STORE_KEY);
  } catch {
    return null;
  }
};

type Msg = { kind: "error" | "info" | "ok"; text: string } | null;

/** "measurement.pressure" -> "pressure", "immediate_action" -> "immediate action" */
export const prettyPath = (p: string): string => (p.includes(".") ? p.split(".").slice(1).join(" ") : p).replace(/_/g, " ");
const names = (n: Note): string => n.fields.map(prettyPath).join(", ");

/** The server's technical reason is for logs; the person gets a plain sentence and a next step. */
export function friendlyError(error: string): string {
  if (/no speech/i.test(error)) {
    return "I could not hear any speech in that recording, so nothing was changed. Try again a little closer to the microphone, or type it.";
  }
  if (/recognition failed/i.test(error)) {
    return "The speech service had a problem with that recording, so nothing was changed. Please try again, or type it.";
  }
  return "That could not be processed, so nothing was changed. Try again, or type it.";
}

export const NOTE_TEXT: Record<string, (n: Note) => string> = {
  unconfirmed_correction: (n) => `A correction was heard${n.fields.length ? ` for ${names(n)}` : ""}. Check the final value below.`,
  possible_dropped_value: (n) => `An earlier value may have been missed by the speech recogniser${n.fields.length ? ` (${names(n)})` : ""}. Check it below.`,
  optional_detail: (n) => `Not mentioned, and optional${n.fields.length ? `: ${names(n)}` : ""}. It stays unknown unless you add it.`,
};

const STEPS = ["Speak", "Check", "Confirm"];
const STEP_OF: Record<string, number> = { empty: 0, needs_answer: 1, ready_for_review: 2, saved: 3 };

/** Where the report is: Speak -> Check -> Confirm. Purely a display of the session's status. */
function Stepper({ status }: { status: string }) {
  const at = STEP_OF[status] ?? 0;
  return (
    <ol className="stepper" aria-label="Progress">
      {STEPS.map((label, i) => {
        const done = i < at;
        const now = i === at;
        return (
          <li key={label} className={done ? "done" : now ? "now" : ""} aria-current={now ? "step" : undefined}>
            <span className="dot" aria-hidden="true">{done ? "✓" : i + 1}</span>
            <span className="step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Short example reports (checked against the real pipeline), so a first-time visitor knows what to say. */
const EXAMPLES: { lang: string; code: string; text: string }[] = [
  { lang: "English", code: "en", text: "Belt two stopped, smoke is coming out" },
  { lang: "हिन्दी", code: "hi", text: "पंप बारह बंद हो गया, धुआं आ रहा है" },
  { lang: "मराठी", code: "mr", text: "पंप बारा बंद पडला, धूर येतोय" },
];

export function Report({ config, wide = false, onStatus }: { config: AppConfig; wide?: boolean; onStatus?: (status: string) => void }) {
  const [lang, setLang] = useState<Lang>("mr");
  const [state, setState] = useState<SessionState | null>(null);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const [heard, setHeard] = useState("");
  const [loading, setLoading] = useState(true);
  // The cause is free text, and speech recognition on a short phrase can be wrong: after a SPOKEN cause the words it
  // heard are put in an editable box (open) so the person can fix them before the read-back is confirmed.
  const [cause, setCause] = useState({ key: 0, text: "", open: false });
  const confirmKey = useRef<{ session: string; revision: number; key: string } | null>(null);
  const maxSeconds = config.limits.max_clip_seconds;

  // Resume the report that was open in this browser, if it still exists.
  useEffect(() => {
    const id = recall();
    if (!id) {
      setLoading(false);
      return;
    }
    api.getSession(id)
      .then((s) => {
        setState(s);
        setLang(s.language);
      })
      .catch(() => remember(null))
      .finally(() => setLoading(false));
  }, []);

  // Tell the page whether a report is under way (it folds the intro away while one is).
  const currentStatus = state?.status ?? "empty";
  useEffect(() => {
    onStatus?.(currentStatus);
  }, [currentStatus, onStatus]);

  // Remember which reports this browser saved, so the "Saved work orders" tab can find them.
  useEffect(() => {
    if (state?.status === "saved") rememberSaved(state.session_id);
  }, [state?.status, state?.session_id]);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (state) return state.session_id;
    const s = await api.createSession(lang);
    remember(s.session_id);
    setState(s);
    return s.session_id;
  }, [state, lang]);

  const run = useCallback(async (label: string, job: () => Promise<void>) => {
    setBusy(label);
    setMsg(null);
    try {
      await job();
    } catch (e) {
      setMsg({ kind: "error", text: errorText(e) });
    } finally {
      setBusy("");
    }
  }, []);

  const afterTurn = (o: TurnOutcome, revisionBefore: number, viaVoice: boolean) => {
    setState(o.state);
    setHeard(o.heard);
    if (o.error) {
      setMsg({ kind: "error", text: friendlyError(o.error) });
    } else if (!o.understood) {
      setMsg({
        kind: "info",
        text: o.mode_used === "cause"
          ? "I could not hear a cause in that, so nothing was changed. Try again, or type it."
          : o.mode_used === "answer"
          ? `I could not match that to an answer, so nothing was changed. Try again, ${o.state.question?.choices.length ? "or tap one of the answers." : "or type it instead."}`
          : "I could not find a maintenance report in that. Try again, a little closer to the microphone.",
      });
    } else if (o.mode_used === "cause" && viaVoice) {
      setCause((c) => ({ key: c.key + 1, text: o.heard, open: true }));
      setMsg({
        kind: "info",
        text: `I heard the cause as “${o.heard}”. Short phrases are easy to mis-hear: if that is not what you said, correct the words in the box below, or tap the microphone and say it again.`,
      });
    } else if (o.mode_used === "cause") {
      setCause((c) => ({ key: c.key + 1, text: "", open: false }));
      setMsg({ kind: "ok", text: "Cause added, in the words you typed. Check the read-back again before saving." });
    } else if (o.state.revision === revisionBefore && o.state.status === "ready_for_review") {
      // the turn was kept in "What was said" but added nothing: never leave the person guessing
      setMsg({
        kind: "info",
        text: "I heard that, but it did not add anything to the work order. To add the cause, use “Add the cause” below.",
      });
    }
  };

  const mode = state?.status === "needs_answer" ? "answer" : "report";

  const onClip = (blob: Blob, as: "report" | "answer" | "cause" = mode) =>
    run("Listening to your recording…", async () => {
      const id = await ensureSession();
      afterTurn(await api.sendAudio(id, blob, as), state?.revision ?? 0, true);
    });

  const onText = (text: string, as: "report" | "answer" | "cause" = mode) =>
    run("Reading your text…", async () => {
      const id = await ensureSession();
      afterTurn(await api.sendText(id, text, as), state?.revision ?? 0, false);
    });

  const onChoose = (q: Question, choice: string) =>
    run("Updating the draft…", async () => {
      if (!state) return;
      setHeard("");
      setState(await api.choose(state.session_id, q.issue_id, choice));
    });

  const onLanguage = (l: Lang) => {
    setLang(l);
    if (state && state.status !== "saved") {
      void run("Changing language…", async () => setState(await api.setLanguage(state.session_id, l)));
    }
  };

  const onConfirm = () =>
    run("Saving…", async () => {
      if (!state?.review) return;
      const { session_id } = state;
      const revision = state.review.revision;
      if (!confirmKey.current || confirmKey.current.session !== session_id || confirmKey.current.revision !== revision) {
        confirmKey.current = { session: session_id, revision, key: newKey() };
      }
      setState(await api.confirm(session_id, revision, confirmKey.current.key));
      setMsg({ kind: "ok", text: "Saved." });
    });

  const startOver = () => {
    remember(null);
    setState(null);
    setHeard("");
    setMsg(null);
    setCause({ key: 0, text: "", open: false });
    confirmKey.current = null;
  };

  if (loading) return <Spinner label="Loading…" />;

  const status = state?.status ?? "empty";
  const disabled = busy !== "";

  const assetsInSide = wide && status === "empty";
  const hasSide = state !== null || assetsInSide;

  return (
    <div className={`report${status === "empty" ? " is-empty" : ""}${wide ? " wide" : ""}`}>
      <Stepper status={status} />
      <div className="report-grid">
        <div className="col">
          <div className="lang-row">
            <span className="lang-cap" aria-hidden="true">Questions and read-back in</span>
            <LanguagePicker value={state?.language ?? lang} onChange={onLanguage} languages={config.languages} disabled={disabled || status === "saved"} />
          </div>

          {busy && <Spinner label={busy} />}
          {msg && <Banner kind={msg.kind}>{msg.text}</Banner>}
          {heard && !busy && status !== "saved" && (
            <p className="heard"><span className="muted">I heard:</span> “{heard}”</p>
          )}

          {status === "empty" && (
            <section className="card hero-card">
              <h2>Report a problem</h2>
              <p>Say which equipment, what is wrong, when, and any readings. You can mix Marathi, Hindi and English.</p>
              <RecordButton maxSeconds={maxSeconds} onClip={onClip} onProblem={(t) => setMsg({ kind: "info", text: t })} disabled={disabled} idleLabel="Tap and speak" />
              <div className="examples">
                <span className="examples-title">Try saying</span>
                <ul>
                  {EXAMPLES.map((x) => (
                    <li key={x.lang}><span className="lang-chip" lang={x.code}>{x.lang}</span><q lang={x.code}>{x.text}</q></li>
                  ))}
                </ul>
              </div>
              <details className="more">
                <summary>Type instead</summary>
                <TypeBox label="Describe the problem" placeholder="e.g. P-12 pump has vibration since morning" onSend={onText} disabled={disabled} />
              </details>
              {!wide && <AssetList config={config} />}
            </section>
          )}

          {state && (state.urgency_level === "emergency" || (status !== "saved" && state.question?.type === "missing_urgency")) && (
            <EmergencyNotice config={config} language={state.language} />
          )}

          {state && status === "needs_answer" && state.question && (
            <QuestionCard q={state.question} disabled={disabled} onChoose={(c) => onChoose(state.question!, c)}
              onClip={onClip} onText={onText} onProblem={(t) => setMsg({ kind: "info", text: t })} maxSeconds={maxSeconds} />
          )}

          {state && status === "ready_for_review" && state.review && (
            <section className="card review">
              <h2>Check before saving</h2>
              <ReviewRows payload={state.review.payload} config={config} />
              <PlayButton url={state.review.audio_url} label="Hear it read back" />
              <details className="more">
                <summary>Read-back wording</summary>
                <p className="readback" lang={state.review.language}>{state.review.readback}</p>
              </details>
              {state.review.routing && <RoutingLine routing={state.review.routing} language={state.language} />}
              <RoutingRules config={config} language={state.language} />
              <p className="hint">Nothing is saved yet. Saving applies to exactly what is shown here, and saved reports cannot be edited in this demo.</p>
              <button type="button" className="btn primary big save" onClick={onConfirm} disabled={disabled}>Yes, this is correct. Save it</button>
              <details className="more" open={cause.open}
                onToggle={(e) => { const open = (e.currentTarget as HTMLDetailsElement).open; setCause((c) => (c.open === open ? c : { ...c, open })); }}>
                <summary>Add the cause (optional)</summary>
                <p className="hint">Say or type what caused it, in your own words. It is saved exactly as written and marked “as reported”.</p>
                <RecordButton maxSeconds={maxSeconds} onClip={(b) => onClip(b, "cause")} onProblem={(t) => setMsg({ kind: "info", text: t })} disabled={disabled} idleLabel="Tap and say the cause" />
                <TypeBox key={cause.key} initial={cause.text} sendLabel="Use as the cause" label="Type the cause" placeholder="Type the cause, e.g. belt slipped due to overload" onSend={(t) => onText(t, "cause")} disabled={disabled} />
              </details>
              <details className="more">
                <summary>Something is wrong or missing? Add more</summary>
                <RecordButton maxSeconds={maxSeconds} onClip={onClip} onProblem={(t) => setMsg({ kind: "info", text: t })} disabled={disabled} idleLabel="Tap and add detail" />
                <TypeBox label="Add more detail" placeholder="Type the extra detail or correction" onSend={onText} disabled={disabled} />
              </details>
            </section>
          )}

          {state && status === "saved" && state.work_order && (
            <section className="card saved">
              <h2>Saved as {state.work_order.short_id}</h2>
              <p className="hint">
                This demo keeps the work order in its own database. It does not send it to a maintenance system. Download or print it below,
                or find it later under “Saved work orders”.
              </p>
              <WorkOrderCard wo={state.work_order} />
              <button type="button" className="btn primary big" onClick={startOver}>Start a new report</button>
            </section>
          )}
        </div>

        {hasSide && (
          <div className="col">
            {assetsInSide && <AssetList config={config} open />}

            {state && state.notes.length > 0 && status !== "saved" && (
              <ul className="notes">
                {state.notes.map((n, i) => (
                  <li key={i}>{(NOTE_TEXT[n.type] ?? (() => n.type))(n)}</li>
                ))}
              </ul>
            )}

            {state && state.fields.length > 0 && <Draft fields={state.fields} history={state.history} saved={status === "saved"} />}

            {state && state.turns.length > 0 && (
              <details className="more card flat">
                <summary>What was said ({state.turns.length})</summary>
                <ol className="turns">
                  {state.turns.map((t) => (
                    <li key={t.index}>
                      <div className="turn-head">
                        <span className="badge">{t.source_label}</span>
                        {t.audio_url && <PlayButton url={t.audio_url} label="Play clip" />}
                      </div>
                      <p className="turn-text">{t.text}</p>
                    </li>
                  ))}
                </ol>
              </details>
            )}

            {state && status !== "saved" && (
              <footer className="foot">
                <span>Recordings left for this report: {state.usage.recordings_left}</span>
                <button type="button" className="link" onClick={startOver}>Discard and start over</button>
              </footer>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const NOT_STATED = new Set(["not reported", "not identified", "nothing recorded", "unknown", "not sure"]);

/** The review as labelled rows (the same fields, from the same data, as the sentence that is read aloud). */
function ReviewRows({ payload, config }: { payload: Record<string, unknown>; config: AppConfig }) {
  const asset = payload.asset && typeof payload.asset === "object" ? (payload.asset as { id?: string }) : null;
  const location = config.assets.find((a) => a.id === asset?.id)?.location ?? null;
  const rows = summarise(payload, location, null).filter((r) => !(r.label === "Immediate action" && r.value === "not reported"));
  return (
    <dl className="rv" aria-label="What will be saved">
      {rows.map((r) => (
        <div className="rv-row" key={r.label}>
          <dt>{r.label}</dt>
          <dd className={NOT_STATED.has(r.value) ? "rv-none" : undefined}>{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function LanguagePicker({ value, onChange, languages, disabled }: {
  value: Lang; onChange: (l: Lang) => void; languages: { code: Lang; label: string }[]; disabled: boolean;
}) {
  return (
    <div className="seg" role="radiogroup" aria-label="Language for questions and read-back">
      {languages.map((l) => (
        <button key={l.code} lang={l.code} type="button" role="radio" aria-checked={value === l.code} className={value === l.code ? "on" : ""}
          onClick={() => onChange(l.code)} disabled={disabled}>
          {l.label}
        </button>
      ))}
    </div>
  );
}

function AssetList({ config, open = false }: { config: AppConfig; open?: boolean }) {
  return (
    <details className={open ? "more card flat" : "more"} open={open || undefined}>
      <summary>Equipment in this fictional plant</summary>
      <ul className="assets">
        {config.assets.map((a) => (
          <li key={a.id}><strong className="mono">{a.id}</strong> {a.name} <span className="muted">({a.location})</span></li>
        ))}
      </ul>
    </details>
  );
}

function QuestionCard({ q, disabled, onChoose, onClip, onText, onProblem, maxSeconds }: {
  q: Question; disabled: boolean; onChoose: (c: string) => void; onClip: (b: Blob) => void;
  onText: (t: string) => void; onProblem: (m: string) => void; maxSeconds: number;
}) {
  const [num, setNum] = useState("");
  return (
    <section className="card question" aria-labelledby="q-title">
      <h2 id="q-title">One question</h2>
      <p className="q-text" lang={q.language}>{q.text}</p>
      <PlayButton key={q.audio_url} url={q.audio_url} label="Hear the question" auto big />
      {q.fallback_offered && (
        <Banner kind="info">I could not understand your spoken answer after {q.attempts} tries. Please tap one of the answers below.</Banner>
      )}
      {q.choices.length > 0 && (
        <div className={q.choices.some((c) => c.label.length > 18) ? "choices list" : "choices"}>
          {q.choices.map((c) => (
            <button key={c.value} type="button" className={`btn choice${c.value === "emergency" ? " danger" : ""}`} data-value={c.value} onClick={() => onChoose(c.value)} disabled={disabled}>{c.label}</button>
          ))}
        </div>
      )}
      {q.accepts_number && (
        <form className="numform" onSubmit={(e) => { e.preventDefault(); if (num.trim()) { onChoose(num.trim()); setNum(""); } }}>
          <label htmlFor="numval">Or type the number</label>
          <div className="row">
            <input id="numval" inputMode="decimal" value={num} onChange={(e) => setNum(e.target.value)} placeholder="e.g. 50" disabled={disabled} />
            <button type="submit" className="btn secondary" disabled={disabled || !num.trim()}>Use this</button>
          </div>
        </form>
      )}
      {!q.fallback_offered && (
        <div className="voice-answer">
          <p className="muted">Or answer by voice:</p>
          <RecordButton maxSeconds={maxSeconds} onClip={onClip} onProblem={onProblem} disabled={disabled} idleLabel="Tap and say your answer" />
        </div>
      )}
      <details className="more">
        <summary>Type an answer instead</summary>
        <TypeBox label="Type your answer" placeholder="Type your answer" onSend={onText} disabled={disabled} />
      </details>
    </section>
  );
}

const STATE_TEXT: Record<string, string> = {
  ok: "heard",
  needs_answer: "needs your answer",
  unknown: "unknown",
  history: "earlier value",
};

function Draft({ fields, history, saved }: { fields: Field[]; history: Field[]; saved: boolean }) {
  return (
    <section className="card flat" aria-labelledby="draft-title">
      <h2 id="draft-title">{saved ? "What was saved" : "What I understood so far"}</h2>
      <p className="hint">Tap a line to see exactly where it came from.</p>
      <ul className="fields">
        {fields.map((f) => <FieldRow key={f.candidate_id} f={f} />)}
      </ul>
      {history.length > 0 && (
        <details className="more">
          <summary>Earlier values that were corrected ({history.length})</summary>
          <ul className="fields">
            {history.map((f) => <FieldRow key={f.candidate_id} f={f} />)}
          </ul>
        </details>
      )}
    </section>
  );
}

const AS_REPORTED = " (as reported)";

/** "…  (as reported)" is drawn as a quiet suffix, so the person's own words stay the main thing on the line. */
function splitReported(value: string): { text: string; reported: boolean } {
  return value.endsWith(AS_REPORTED) ? { text: value.slice(0, -AS_REPORTED.length), reported: true } : { text: value, reported: false };
}

function StatusMark({ state }: { state: string }) {
  if (state === "ok") return <span className="tick" role="img" aria-label="understood">✓</span>;
  return <span className={`badge st-${state}`}>{STATE_TEXT[state] ?? state}</span>;
}

function FieldRow({ f }: { f: Field }) {
  const [open, setOpen] = useState(false);
  const typed = f.origin !== "speech";
  const { text, reported } = splitReported(f.value);
  return (
    <li className={`field ${f.state}`}>
      <button type="button" className="field-head" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="f-label">{f.label}</span>
        <span className="f-main">
          <span className="f-value">
            {text}
            {reported && <span className="f-note"> as reported</span>}
          </span>
          {f.heard && f.understood_as && (
            <span className="conv" aria-label={`Heard ${f.heard}, understood as ${f.understood_as}`}>
              You said “{f.heard}” <span aria-hidden="true">→</span> <strong>{f.understood_as}</strong>
            </span>
          )}
        </span>
        <span className="f-side">
          <StatusMark state={f.state} />
          {typed && <span className="badge">{f.origin}</span>}
          <span className="chev" aria-hidden="true">{open ? "▾" : "▸"}</span>
        </span>
      </button>
      {open && (
        <div className="receipts">
          {f.receipts.length === 0 && <p className="hint">No transcript quote: this value was chosen or typed by you.</p>}
          {f.receipts.map((r, i) => {
            const p = parseMarked(r.marked_html);
            return (
              <div key={i} className="receipt">
                <div className="muted">Turn {r.turn_index + 1} · {r.source_label}</div>
                <blockquote>
                  {p.before}{p.hit && <mark>{p.hit}</mark>}{p.after}
                </blockquote>
                {r.audio_url ? <PlayButton url={r.audio_url} label="Play the clip for this turn" /> : <span className="hint">No audio for this turn.</span>}
              </div>
            );
          })}
          {f.receipts.length > 0 && <p className="hint">The clip is the whole turn, not just the highlighted words.</p>}
        </div>
      )}
    </li>
  );
}
