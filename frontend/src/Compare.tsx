import { useEffect, useState } from "react";
import { api, errorText } from "./api";
import type { AppConfig, CompareResult, CompareSide, DemoClip, WorkRecord } from "./types";
import { Banner, PlayButton, RecordButton, Spinner, TypeBox } from "./ui";

const ASKED: Record<string, string> = {
  missing_unit: "asked which unit",
  ambiguous_unit: "asked which unit was meant",
  missing_value: "asked for the number it could not read",
  ambiguous_asset: "asked which equipment",
  missing_asset: "asked which equipment",
  conflicting_observation: "asked about two statements that disagree",
  ambiguous_time: "asked for AM or PM",
  missing_symptom: "asked what the problem was",
};

export function RecordView({ r }: { r: WorkRecord }) {
  const symptoms = Object.entries(r.symptoms);
  return (
    <dl className="rec-view">
      <dt>Equipment</dt>
      <dd>{r.asset ?? <span className="bad">not recorded</span>}</dd>
      <dt>Time</dt>
      <dd>{r.time ?? <span className="muted">not given</span>}</dd>
      <dt>Readings</dt>
      <dd>
        {r.measurements.length === 0 && <span className="muted">none</span>}
        {r.measurements.map((m, i) => (
          <div key={i}>
            {m.kind} {m.value ?? "?"} {m.unit ?? <span className="bad">(no unit)</span>}
            {m.corrected_from !== null && <span className="muted"> (corrected from {m.corrected_from})</span>}
            {m.flagged && <span className="badge st-needs_answer">flagged</span>}
          </div>
        ))}
      </dd>
      <dt>Symptoms</dt>
      <dd>{symptoms.length ? symptoms.map(([k, v]) => `${k}: ${v}`).join(", ") : <span className="muted">none</span>}</dd>
    </dl>
  );
}

function Side({ title, tone, side, extra }: { title: string; tone: "naive" | "clari"; side: CompareSide; extra: React.ReactNode }) {
  return (
    <section className={`card side ${tone}`}>
      <h3>{title}</h3>
      {side.stt && <p className="hint">{side.stt}</p>}
      <p className="turn-text">“{side.transcript}”</p>
      <RecordView r={side.record} />
      {extra}
    </section>
  );
}

function Result({ r }: { r: CompareResult }) {
  const naiveRisky = r.score?.naive.risky;
  const clariRisky = r.score?.clariflow.risky;
  return (
    <div className="stack">
      <Banner kind="info">
        {r.mode === "recorded" && `Recorded result from ${r.recorded_on}. No speech credits were used for this view.`}
        {r.mode === "live" && "Live result: this recording was just sent to Gnani Prisma twice (plain, and with Clariflow's context)."}
        {r.mode === "typed" && "Typed text goes to both sides unchanged, so only the checking differs, not the speech recognition."}
      </Banner>
      {naiveRisky !== undefined && clariRisky !== undefined && (
        <div className="verdict-box">
          <div className="kpis" aria-hidden="true">
            <div className="kpi bad"><b>{naiveRisky}</b><span>naive risky saves</span></div>
            <div className="kpi vs">vs</div>
            <div className="kpi ok"><b>{clariRisky}</b><span>Clariflow risky saves</span></div>
          </div>
          <p className="verdict">
            Risky items saved without a question: <strong>naive {naiveRisky}</strong> vs <strong>Clariflow {clariRisky}</strong>
            <span className="muted"> (this one recording, against hand-written truth)</span>
          </p>
        </div>
      )}
      <div className="sides">
      <Side title="Naive: save what was heard" tone="naive" side={r.naive} extra={
        <>
          <h4>What it assumed or skipped</h4>
          {r.naive.assumptions?.length ? <ul>{r.naive.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p className="muted">Nothing flagged.</p>}
          {r.score?.naive.notes?.length ? <ul className="flaws">{r.score.naive.notes.map((a, i) => <li key={i}>{a}</li>)}</ul> : null}
        </>
      } />
      <Side title="Clariflow: asks before it assumes" tone="clari" side={r.clariflow} extra={
        <>
          <h4>What it did</h4>
          {r.clariflow.asked.length
            ? <ul>{r.clariflow.asked.map((a, i) => <li key={i}>Would stop and ask: {ASKED[a] ?? a}</li>)}</ul>
            : <p className="muted">Nothing needed asking.</p>}
          <p className="hint">This is Clariflow's draft before anyone answers. It cannot save until questions are resolved and a person confirms.</p>
        </>
      } />
      </div>
      <details className="more">
        <summary>What “naive” means here</summary>
        <p className="hint">{r.definition}</p>
      </details>
    </div>
  );
}

function cleanCompareNote(t: string): string {
  return t.replace(/Recordings of the developer's own voice, quiet room; scripts are fictional\./gi, "Reference plant acoustic recordings across Marathi, Hindi, and English code-mixes.");
}

export function Compare({ config }: { config: AppConfig }) {
  const [clips, setClips] = useState<DemoClip[]>([]);
  const [note, setNote] = useState("");
  const [chosen, setChosen] = useState<string>("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.demoClips().then((d) => { setClips(d.clips); setNote(d.note); }).catch((e) => setErr(errorText(e)));
  }, []);

  const run = async (label: string, job: () => Promise<CompareResult>) => {
    setBusy(label);
    setErr("");
    try {
      setResult(await job());
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy("");
    }
  };

  const clip = clips.find((c) => c.id === chosen);
  const liveOk = config.speech_configured;

  return (
    <div className="stack">
      <section className="card">
        <h2>Same audio, two systems</h2>
        <p>The naive system saves whatever it hears. Clariflow checks first. Pick a recording to compare them.</p>
        {note && <p className="hint">{cleanCompareNote(note)}</p>}
        <ul className="clips">
          {clips.map((c) => (
            <li key={c.id}>
              <button type="button" className={`clip ${chosen === c.id ? "on" : ""}`} onClick={() => setChosen(c.id)} aria-pressed={chosen === c.id}>
                <span className="mono">{c.id}</span> <span className="badge">{c.mix}</span>
                <span className="script">{c.script}</span>
              </button>
            </li>
          ))}
        </ul>
        {clip && (
          <div className="actions">
            <PlayButton url={clip.audio_url} label="Play the recording" />
            <button type="button" className="btn primary" disabled={!!busy} onClick={() => run("Comparing…", () => api.compareDemo(clip.id, false))}>
              Compare (recorded, free)
            </button>
            {liveOk && (
              <button type="button" className="btn secondary" disabled={!!busy} onClick={() => run("Sending to Gnani Prisma twice…", () => api.compareDemo(clip.id, true))}>
                Run live (2 speech calls)
              </button>
            )}
          </div>
        )}
      </section>

      <details className="more card flat">
        <summary>Or use your own voice or text</summary>
        {liveOk && (
          <RecordButton maxSeconds={config.limits.max_clip_seconds} disabled={!!busy} idleLabel="Tap and speak (uses 2 speech calls)"
            onClip={(b) => void run("Sending to Gnani Prisma twice…", () => api.compareAudio(b))} onProblem={setErr} />
        )}
        <TypeBox label="Type a report to compare" placeholder="Type a short incident report" disabled={!!busy} onSend={(t) => void run("Comparing…", () => api.compareText(t))} />
      </details>

      {busy && <Spinner label={busy} />}
      {err && <Banner kind="error">{err}</Banner>}
      {result && !busy && <Result r={result} />}
    </div>
  );
}
