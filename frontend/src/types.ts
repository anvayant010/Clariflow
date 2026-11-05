// Mirrors backend/app/api/schemas.py. The server decides every rule; the UI only draws what it is given.

export type Lang = "mr" | "hi" | "en";

export interface Receipt {
  turn_index: number;
  source: string;
  source_label: string;
  quote: string;
  marked_html: string; // server HTML-escapes the text and wraps the quote in <mark>; we parse it, never inject it
  audio_url: string | null;
}

export interface Field {
  candidate_id: string;
  label: string;
  value: string;
  state: "ok" | "needs_answer" | "unknown" | "history" | string;
  origin: string;
  receipts: Receipt[];
  heard: string | null; // the words as spoken/typed, when the language handling converted them ("पंधरा")
  understood_as: string | null; // what they became ("15")
}

export interface Turn {
  index: number;
  source: string;
  source_label: string;
  text: string;
  audio_url: string | null;
  language_code: string | null;
}

export interface Choice {
  value: string;
  label: string;
}

export interface Question {
  issue_id: string;
  type: string;
  text: string;
  language: Lang;
  choices: Choice[];
  accepts_number: boolean;
  audio_url: string;
  attempts: number;
  fallback_offered: boolean;
}

export interface Note {
  type: string;
  fields: string[];
  quotes: string[];
}

/** SIMULATED routing: who would be told. Nothing is ever sent. */
export interface Routing {
  simulated: boolean;
  rule: string; // the urgency level whose rule applied ("unknown" when the person was not sure)
  urgency_labels: Record<Lang, string>;
  notify: { role: string; labels: Record<Lang, string> }[];
  note: string | null;
}

export interface Review {
  revision: number;
  language: Lang;
  readback: string;
  payload: Record<string, unknown>;
  audio_url: string;
  routing: Routing | null;
}

export interface WorkOrder {
  id: string;
  short_id: string; // "WO-D4D6EE98"
  session_id: string;
  language: Lang;
  confirmed_revision: number;
  location: string | null; // from the fictional plant catalogue
  readback: string; // the read-back the person heard and confirmed, in the report's language
  readbacks: Record<Lang, string>; // the same saved record in every language (fixed templates)
  routing: Routing | null; // null for records saved before urgency existed
  payload: Record<string, unknown>;
  created_at: string;
}

export interface SessionState {
  session_id: string;
  language: Lang;
  status: "empty" | "needs_answer" | "ready_for_review" | "saved";
  revision: number;
  synthetic_demonstration: boolean;
  turns: Turn[];
  fields: Field[];
  history: Field[];
  question: Question | null;
  notes: Note[];
  review: Review | null;
  work_order: WorkOrder | null;
  urgency_level: string | null; // the person's stated level, if any
  usage: { recordings_left: number; voice_prompts_left: number };
}

export interface TurnOutcome {
  mode_used: "report" | "answer" | "cause";
  understood: boolean;
  heard: string;
  error: string | null;
  attempts: number;
  fallback_offered: boolean;
  state: SessionState;
}

export interface AppConfig {
  app: string;
  synthetic_demonstration: boolean;
  languages: { code: Lang; label: string }[];
  speech_configured: boolean;
  fixture_allowed: boolean;
  assets: { id: string; name: string; type: string; location: string }[];
  limits: { max_clip_seconds: number; recordings_per_report: number; voice_prompts_per_report: number };
  speech: { stt: string; tts: string; stt_config: string };
  routing: {
    simulated: boolean;
    emergency_notice: Record<Lang, string>;
    rules: { level: string; labels: Record<Lang, string>; notify: { role: string; labels: Record<Lang, string> }[]; note: string | null }[];
  };
}

// ---- quality views

export interface Measurement {
  kind: string;
  value: number | null;
  unit: string | null;
  corrected_from: number | null;
  flagged: boolean;
}

export interface WorkRecord {
  system: string;
  asset: string | null;
  time: string | null;
  measurements: Measurement[];
  symptoms: Record<string, string>;
  cause: string | null;
  flags: string[];
}

export interface BreakCheck {
  name: string;
  expected: unknown; // string, number, null, or a measurement {value, unit, corrected_from}
  actual: unknown;
  passed: boolean;
}

export interface BreakScenario {
  id: string;
  title: string;
  what_it_tests: string;
  provenance: string;
  transcript: string;
  checks: BreakCheck[];
  passed: boolean;
  naive: { transcript: string; record: WorkRecord; risky: number; flaws: string[] };
}

export interface BreakResult {
  mode: string;
  naive_definition: string;
  scenarios: BreakScenario[];
}

export interface Totals {
  slots: number;
  correct: number;
  wrong: number;
  assumed: number;
  unresolved: number;
  missing: number;
  flagged_safe: number;
  handled: number;
  unnecessary_questions: number;
  corrections_total: number;
  corrections_kept: number;
  risky: number;
  cases_with_risky: number;
}

export interface Dataset {
  title: string;
  n_cases: number;
  totals: { naive: Totals; clariflow: Totals };
}

export interface Evaluation {
  historical: boolean;
  note: string;
  generated: string;
  mode: string;
  stt_note: string;
  naive_definition: string;
  caveats: string[];
  datasets: Record<string, Dataset>;
}

export interface DemoClip {
  id: string;
  mix: string;
  script: string;
  transcribed_on: string;
  audio_url: string;
}

export interface CompareSide {
  stt?: string;
  transcript: string;
  record: WorkRecord;
  assumptions?: string[];
  asked: string[];
}

export interface CompareResult {
  mode: "recorded" | "live" | "typed";
  recorded_on?: string;
  definition: string;
  naive: CompareSide;
  clariflow: CompareSide;
  score?: { naive: Record<string, unknown> & { notes?: string[]; risky?: number }; clariflow: Record<string, unknown> & { notes?: string[]; risky?: number } };
}
