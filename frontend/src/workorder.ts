import type { Lang, Routing, WorkOrder } from "./types";

export const LANG_LABEL: Record<Lang, string> = { mr: "मराठी", hi: "हिन्दी", en: "English" };
export const LANGS: Lang[] = ["mr", "hi", "en"];

/** "14:00" -> "2:00 PM" (the saved value stays 24-hour; people read and hear the 12-hour clock). Non-times are returned as they are. */
export function to12h(value: unknown): string {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(value ?? "").trim());
  if (!m) return value == null ? "" : String(value);
  const h = Number(m[1]);
  const min = Number(m[2]);
  if (h > 23 || min > 59) return String(value);
  return `${h % 12 || 12}:${m[2]} ${h < 12 ? "AM" : "PM"}`;
}

export const LEVEL_EN: Record<string, string> = {
  can_wait: "Can wait", today: "Needs attention today", stop_work: "Stop work now", emergency: "Emergency",
};

export interface Row {
  label: string;
  value: string;
}

type Obj = Record<string, unknown>;
const asObj = (v: unknown): Obj | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : null);
const words = (s: string): string => s.replace(/_/g, " ");
const cap = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * Turn the saved payload into plain rows for the card. Nothing is added: a value that was not
 * stated shows as "unknown" or "not reported", never as a guess.
 */
export function summarise(payload: Obj, location: string | null, routing: Routing | null = null, lang: Lang = "en"): Row[] {
  const rows: Row[] = [];
  const asset = asObj(payload.asset);
  rows.push({ label: "Equipment", value: asset ? `${asset.id} · ${asset.name}` : "not identified" });
  if (location) rows.push({ label: "Location", value: location });

  const symptoms = Array.isArray(payload.symptoms) ? payload.symptoms.map(asObj).filter((s): s is Obj => !!s) : [];
  rows.push({
    label: "Observed",
    value: symptoms.length ? symptoms.map((s) => `${words(String(s.concept))}: ${s.state}`).join(", ") : "nothing recorded",
  });

  const urgency = asObj(payload.urgency); // records saved before urgency existed have none: no row, nothing invented
  if (urgency) {
    rows.push({
      label: "Urgency",
      value: urgency.status === "stated" ? (LEVEL_EN[String(urgency.level)] ?? String(urgency.level)) : urgency.status === "unknown" ? "not sure" : "not reported",
    });
  }

  const t = asObj(payload.reported_incident_time);
  if (!t) rows.push({ label: "Reported time", value: "not reported" });
  else if (t.status === "unknown" || t.value == null) rows.push({ label: "Reported time", value: "unknown" });
  else {
    const fix = t.corrected_from != null ? ` (corrected from ${to12h(t.corrected_from)})` : "";
    rows.push({ label: "Reported time", value: `${to12h(t.value)}${fix}` });
  }

  const ms = Array.isArray(payload.measurements) ? payload.measurements.map(asObj).filter((m): m is Obj => !!m) : [];
  for (const m of ms) {
    const from = asObj(m.corrected_from);
    const unit = m.unit ? String(m.unit) : m.unit_status === "unknown" ? "unit unknown" : "no unit given";
    const value = m.value == null ? "value unreadable" : String(m.value);
    let text = `${value} ${unit}`.trim();
    if (from) text += ` (corrected from ${from.value}${from.unit ? " " + from.unit : ""})`;
    if (m.earlier_value_not_heard) text += " (an earlier value was not heard)";
    rows.push({ label: cap(words(String(m.kind ?? "reading"))), value: text });
  }

  const cause = asObj(payload.cause);
  rows.push({
    label: "Cause",
    value: cause?.status === "reported" && typeof cause.value === "string" ? `${cause.value} (as reported)`
      : cause?.status === "unknown" ? "unknown" : "not reported",
  });
  const action = payload.immediate_action;
  rows.push({ label: "Immediate action", value: typeof action === "string" && action ? words(action) : "not reported" });
  if (routing) {
    rows.push({ label: "Would notify (simulated)", value: routing.notify.map((n) => n.labels[lang] ?? n.labels.en).join(", ") });
  }
  return rows;
}

/** The file a person downloads: the saved record exactly as stored, plus the readable fields. */
export function exportObject(wo: WorkOrder): Record<string, unknown> {
  return {
    work_order_number: wo.short_id,
    id: wo.id,
    saved_at: wo.created_at,
    confirmed_revision: wo.confirmed_revision,
    language: wo.language,
    location: wo.location,
    confirmed_readback: wo.readback,
    confirmed_readback_language: wo.language,
    readbacks: wo.readbacks,
    routing: wo.routing, // SIMULATED: who would have been told; nothing was sent
    routing_note: "Simulated routing from a rule file. Nothing was sent to anyone.",
    readbacks_note: "Same record in each language, produced from fixed templates. Marathi and Hindi wording is a draft awaiting native-speaker review.",
    synthetic_demonstration: true,
    note: "Synthetic demonstration record from a fictional plant. Not sent to any maintenance system.",
    payload: wo.payload,
  };
}

export function formatSaved(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

// ---- the report ids this browser created (a convenience: the records themselves live on the server)

const KEY = "clariflow.saved";
const MAX_REMEMBERED = 50;

export function savedIds(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string").slice(0, MAX_REMEMBERED) : [];
  } catch {
    return [];
  }
}

export function rememberSaved(sessionId: string): void {
  try {
    const next = [sessionId, ...savedIds().filter((x) => x !== sessionId)].slice(0, MAX_REMEMBERED);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* storage can be blocked; the saved screen still works */
  }
}
