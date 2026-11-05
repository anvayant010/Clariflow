import { beforeEach, describe, expect, it } from "vitest";
import type { WorkOrder } from "./types";
import { exportObject, rememberSaved, savedIds, summarise, to12h } from "./workorder";

const payload = {
  synthetic_demonstration: true,
  asset: { id: "P-12", name: "Feed Water Pump 12" },
  symptoms: [{ concept: "vibration", state: "present" }, { concept: "smoke", state: "present" }],
  reported_incident_time: { raw: "ten thirty", value: "10:30", status: "stated", corrected_from: "10:20" },
  measurements: [
    { kind: "pressure", value: 50, unit: "PSI", corrected_from: { value: 15, unit: null } },
    { kind: "temperature", value: 80, unit: null, unit_status: "missing" },
    { kind: "vibration_level", value: null, unit: null, unit_status: "unknown", earlier_value_not_heard: true },
  ],
  cause: { status: "unknown", value: null },
  immediate_action: null,
};

const rows = (p: object, loc: string | null = "Boiler House, Line 1") => Object.fromEntries(summarise(p as never, loc).map((r) => [r.label, r.value]));

describe("summarise", () => {
  it("shows exactly what was saved", () => {
    const r = rows(payload);
    expect(r["Equipment"]).toBe("P-12 · Feed Water Pump 12");
    expect(r["Location"]).toBe("Boiler House, Line 1");
    expect(r["Observed"]).toBe("vibration: present, smoke: present");
    expect(r["Reported time"]).toBe("10:30 AM (corrected from 10:20 AM)");
    expect(r["Pressure"]).toBe("50 PSI (corrected from 15)");
    expect(r["Cause"]).toBe("unknown");
    expect(r["Immediate action"]).toBe("not reported");
  });
  it("shows a reported cause as the speaker's own words, and unknown as unknown", () => {
    expect(rows({ ...payload, cause: { status: "reported", value: "belt slipped", quote: ["belt slipped"] } })["Cause"]).toBe("belt slipped (as reported)");
    expect(rows({ ...payload, cause: { status: "unknown", value: null } })["Cause"]).toBe("unknown");
    expect(rows({ ...payload, cause: { status: "not_reported", value: null } })["Cause"]).toBe("not reported");
  });
  it("never turns a missing unit or value into a guess", () => {
    const r = rows(payload);
    expect(r["Temperature"]).toBe("80 no unit given");
    expect(r["Vibration level"]).toBe("value unreadable unit unknown (an earlier value was not heard)");
  });
  it("handles an almost empty payload without inventing anything", () => {
    const r = rows({ asset: null, symptoms: [], reported_incident_time: null, measurements: [], cause: { status: "not_reported" } }, null);
    expect(r).toEqual({ Equipment: "not identified", Observed: "nothing recorded", "Reported time": "not reported", Cause: "not reported", "Immediate action": "not reported" });
  });
});

describe("export and remembered ids", () => {
  beforeEach(() => localStorage.clear());
  const wo: WorkOrder = { id: "abc", short_id: "WO-ABC", session_id: "s1", language: "mr", confirmed_revision: 2, location: null, readback: "x", readbacks: { mr: "x", hi: "y", en: "z" }, routing: null, payload, created_at: "2026-11-04T10:00:00+00:00" };

  it("labels the download as synthetic and not sent anywhere, and carries no session id", () => {
    const o = exportObject(wo);
    expect(o.synthetic_demonstration).toBe(true);
    expect(String(o.note)).toMatch(/Not sent to any maintenance system/);
    expect(JSON.stringify(o)).not.toContain("s1");
    expect(o.payload).toBe(payload);
    expect(o.readbacks).toEqual({ mr: "x", hi: "y", en: "z" });
    expect(o.confirmed_readback_language).toBe("mr");
  });
  it("remembers report ids newest first, without duplicates", () => {
    rememberSaved("a"); rememberSaved("b"); rememberSaved("a");
    expect(savedIds()).toEqual(["a", "b"]);
  });
  it("survives corrupt or blocked storage", () => {
    localStorage.setItem("clariflow.saved", "{not json");
    expect(savedIds()).toEqual([]);
  });
});

describe("summarise: urgency and routing rows", () => {
  const routing = {
    simulated: true, rule: "stop_work", note: null, urgency_labels: { en: "stop work now", mr: "x", hi: "y" },
    notify: [{ role: "maintenance_head", labels: { en: "Maintenance head", mr: "देखभाल प्रमुख", hi: "रखरखाव प्रमुख" } }],
  };
  const table = (rows: { label: string; value: string }[]) => Object.fromEntries(rows.map((x) => [x.label, x.value]));

  it("shows the person's own urgency answer and, when given, who would be notified (simulated)", () => {
    const r = table(summarise({ ...payload, urgency: { status: "stated", level: "stop_work" } } as never, null, routing, "mr"));
    expect(r["Urgency"]).toBe("Stop work now");
    expect(r["Would notify (simulated)"]).toBe("देखभाल प्रमुख");
  });
  it("shows 'not sure' as not sure, never as a level", () => {
    expect(table(summarise({ ...payload, urgency: { status: "unknown", level: null } } as never, null))["Urgency"]).toBe("not sure");
  });
  it("adds nothing for a record saved before urgency existed", () => {
    const labels = summarise(payload as never, null).map((x) => x.label);
    expect(labels).not.toContain("Urgency");
    expect(labels).not.toContain("Would notify (simulated)");
  });
});


describe("12-hour clock", () => {
  it.each([["14:00", "2:00 PM"], ["00:30", "12:30 AM"], ["12:00", "12:00 PM"], ["09:05", "9:05 AM"], ["23:59", "11:59 PM"], ["00:00", "12:00 AM"]])(
    "%s -> %s", (v, shown) => expect(to12h(v)).toBe(shown));
  it("leaves anything that is not a time alone", () => {
    expect(to12h(null)).toBe("");
    expect(to12h("25:00")).toBe("25:00");
    expect(to12h("ten thirty")).toBe("ten thirty");
  });
  it("shows the card's reported time in 12-hour form", () => {
    const rows = summarise({ ...payload, reported_incident_time: { raw: "दो बजे", value: "14:00", status: "stated" } } as never, null);
    expect(rows.find((r) => r.label === "Reported time")?.value).toBe("2:00 PM");
  });
});
