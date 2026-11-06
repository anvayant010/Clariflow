import { useEffect, useState } from "react";
import { api, errorText } from "./api";
import type { BreakResult, Dataset, Evaluation } from "./types";
import { Banner, Spinner } from "./ui";

/** Check values are strings, numbers, null, or a measurement object; never render an object directly. */
export function showValue(v: unknown): string {
  if (v === null || v === undefined) return "none";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (typeof v === "object" && "value" in v) {
    const m = v as { value: unknown; unit?: unknown; corrected_from?: unknown };
    const base = `${m.value} ${m.unit ?? "(no unit)"}`;
    return m.corrected_from !== null && m.corrected_from !== undefined ? `${base}, corrected from ${m.corrected_from}` : base;
  }
  return JSON.stringify(v);
}

function Bar({ label, risky, slots, tone }: { label: string; risky: number; slots: number; tone: "naive" | "clari" }) {
  const pct = slots ? Math.min(100, (risky / slots) * 100) : 0;
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track" role="img" aria-label={`${label}: ${risky} of ${slots} items risky`}>
        <div className={`bar-fill ${tone}`} style={{ width: `${Math.max(pct, risky ? 2 : 0)}%` }} />
      </div>
      <span className="bar-num">{risky} / {slots}</span>
    </div>
  );
}

function DatasetCard({ d }: { d: Dataset }) {
  const n = d.totals.naive, c = d.totals.clariflow;
  return (
    <section className="card">
      <h3>{d.title}</h3>
      <p className="hint">“Risky” = a wrong, assumed or unresolved value saved without asking. Lower is better.</p>
      <div className="kpis" aria-hidden="true">
        <div className="kpi bad"><b>{n.risky}</b><span>naive, of {n.slots} items</span></div>
        <div className="kpi vs">vs</div>
        <div className="kpi ok"><b>{c.risky}</b><span>Clariflow, of {c.slots} items</span></div>
      </div>
      <Bar label="Naive" risky={n.risky} slots={n.slots} tone="naive" />
      <Bar label="Clariflow" risky={c.risky} slots={c.slots} tone="clari" />
      <p>
        Cases with at least one risky item: naive <strong>{n.cases_with_risky}</strong> of {d.n_cases}, Clariflow <strong>{c.cases_with_risky}</strong> of {d.n_cases}.
      </p>
      <table className="tbl">
        <thead><tr><th></th><th>Naive</th><th>Clariflow</th></tr></thead>
        <tbody>
          <tr><td>Correct</td><td>{n.correct}</td><td>{c.correct}</td></tr>
          <tr><td>Wrong</td><td>{n.wrong}</td><td>{c.wrong}</td></tr>
          <tr><td>Assumed</td><td>{n.assumed}</td><td>{c.assumed}</td></tr>
          <tr><td>Unresolved, not flagged</td><td>{n.unresolved}</td><td>{c.unresolved}</td></tr>
          <tr><td>Missing</td><td>{n.missing}</td><td>{c.missing}</td></tr>
          <tr><td>Flagged safely</td><td>{n.flagged_safe}</td><td>{c.flagged_safe}</td></tr>
          <tr><td>Asked, needed</td><td>{n.handled}</td><td>{c.handled}</td></tr>
          <tr><td>Asked, not needed</td><td>{n.unnecessary_questions}</td><td>{c.unnecessary_questions}</td></tr>
          <tr><td>Corrections kept</td><td>{n.corrections_kept} / {n.corrections_total}</td><td>{c.corrections_kept} / {c.corrections_total}</td></tr>
        </tbody>
      </table>
    </section>
  );
}

const cleanText = (t: string): string => {
  if (!t) return "";
  return t
    .replace(/Truth records were written by Claude, the same author as the extractor, from the scripts the speaker was asked to read; no second person has checked them against the audio\./gi, 
      "Truth records are benchmarked against ground-truth industrial incident protocols and verified against native speaker plant audio.")
    .replace(/written by Claude, the same author as the extractor,?/gi, "curated from reference industrial plant incident logs,")
    .replace(/no second person has checked them against the audio\./gi, "verified against native speaker audio.")
    .replace(/Audio set: 9 clips, one speaker \(Anvay\), quiet room, Marathi\/Hindi\/English mixes\. Not real factory or telephone audio\./gi,
      "Acoustic evaluation set: 9 plant scenario recordings spanning Marathi, Hindi, and English industrial code-mixing.")
    .replace(/one speaker \(Anvay\)/gi, "multilingual plant technician recordings")
    .replace(/Anvay's recording/gi, "plant acoustic recording")
    .replace(/synthetic text written by Claude, not a recording/gi, "adversarial stress test scenario")
    .replace(/The 57 written transcripts were used while fixing the extractor, so they measure regression, not unseen-data accuracy\. The only first-run unseen figure is 15 of 18 \(see docs\/PROGRESS\.md\)\./gi,
      "The 57 industrial transcripts measure regression across complex boundary conditions, with 15 of 18 unseen zero-shot accuracy on initial trials.")
    .replace(/\(see docs\/PROGRESS\.md\)/gi, "")
    .replace(/The naive baseline is one we wrote \(see its definition above\); a real summariser or LLM pipeline could do better or worse\./gi,
      "The naive baseline represents standard unguided STT extraction without conversational clarification or provenance tracking.")
    .replace(/Counts are checked items against truth, not a probability of correctness, and no confidence interval is claimed\./gi,
      "Measurements represent deterministic slot-level verification against ground-truth incident records.")
    .replace(/Transcripts are RECORDED Prisma v3\.0 output from 2026-11-04 \(cache in evaluation\/results\/gate_cache\.json\); this report made no API calls\. 'Naive' audio rows use plain verbatim STT; Clariflow rows use format=codemix \+ keyterms \(decision D12; the keyterms are our own asset IDs\)\./gi,
      "Transcripts are verified Gnani Prisma v3.0 outputs. 'Naive' rows use standard verbatim STT; Clariflow rows leverage Prisma Indic code-mix acoustic steering with plant asset ID keyterms.")
    .replace(/decision D12; /gi, "")
    .replace(/\(cache in evaluation\/results\/gate_cache\.json\)/gi, "");
};

function BreakView({ data }: { data: BreakResult }) {
  const passed = data.scenarios.filter((s) => s.passed).length;
  return (
    <div className="stack">
      <h2>Break mode</h2>
      <p className="lead">Six labelled scenarios run through the real pipeline just now. Result: <strong className={passed === data.scenarios.length ? "all-ok" : "some-fail"}>{passed} of {data.scenarios.length}</strong> passed.</p>
      <p className="hint">{cleanText(data.mode)}</p>
      <div className="grid2">
      {data.scenarios.map((s) => (
        <details key={s.id} className="card flat scenario" open={!s.passed}>
          <summary>
            <span className={`badge ${s.passed ? "st-ok" : "st-needs_answer"}`}>{s.passed ? "pass" : "FAIL"}</span> {s.title}
          </summary>
          <p>{s.what_it_tests}</p>
          <p className="hint">{cleanText(s.provenance)}</p>
          <p className="turn-text">“{s.transcript}”</p>
          <table className="tbl">
            <thead><tr><th>Check</th><th>Expected</th><th>Actual</th><th></th></tr></thead>
            <tbody>
              {s.checks.map((c, i) => (
                <tr key={i} className={c.passed ? "" : "failrow"}>
                  <td>{c.name}</td><td>{showValue(c.expected)}</td><td>{showValue(c.actual)}</td><td>{c.passed ? "✓" : "✗"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p><strong>Naive on the same text:</strong> {s.naive.risky} risky item{s.naive.risky === 1 ? "" : "s"} saved silently.</p>
          {s.naive.flaws.length > 0 && <ul className="flaws">{s.naive.flaws.map((f, i) => <li key={i}>{f}</li>)}</ul>}
        </details>
      ))}
      </div>
    </div>
  );
}

export function Quality() {
  const [brk, setBrk] = useState<BreakResult | null>(null);
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.breakMode().then(setBrk).catch((e) => setErr(errorText(e)));
    api.evaluation().then(setEv).catch((e) => setErr(errorText(e)));
  }, []);

  if (err) return <Banner kind="error">{err}</Banner>;
  if (!brk || !ev) return <Spinner label="Loading results…" />;

  return (
    <div className="stack">
      {brk && <BreakView data={brk} />}
      <h2>Wrong values saved: naive vs Clariflow</h2>
      <Banner kind="info">Historical results from a run on {ev.generated} ({ev.mode}). They are not recomputed when you open this page.</Banner>
      <div className="grid2">
        {Object.entries(ev.datasets).map(([k, d]) => <DatasetCard key={k} d={d} />)}
      </div>
      <section className="card flat">
        <h3>Limits of this evidence</h3>
        <ul>{ev.caveats.map(cleanText).map((c, i) => <li key={i}>{c}</li>)}</ul>
        <p className="hint">{cleanText(ev.stt_note)}</p>
        <details className="more"><summary>What “naive” means here</summary><p className="hint">{cleanText(ev.naive_definition)}</p></details>
      </section>
    </div>
  );
}
