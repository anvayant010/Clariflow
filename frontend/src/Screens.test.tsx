import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Compare } from "./Compare";
import { Quality } from "./Quality";
import { Saved } from "./Saved";
import type { AppConfig } from "./types";
import breakData from "./fixtures/break.json";
import clips from "./fixtures/demo-clips.json";
import evaluation from "./fixtures/evaluation.json";
import cmpHE3 from "./fixtures/compare-he3.json";
import cmpME1 from "./fixtures/compare-me1.json";

// These payloads were captured from the running server (not hand-written), so a renamed or
// missing field in the API shows up here instead of as a blank screen in the browser.
vi.mock("./audio", () => ({ playUrl: vi.fn(async () => undefined), stopAudio: vi.fn() }));

const config = {
  speech_configured: true,
  limits: { max_clip_seconds: 30, recordings_per_report: 15, voice_prompts_per_report: 30 },
} as AppConfig;

function serve(routes: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    return key ? new Response(JSON.stringify(routes[key]), { status: 200 }) : new Response("{}", { status: 404 });
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Break mode and results", () => {
  it("shows every scenario with pass state, and the evaluation labelled as historical", async () => {
    serve({ "/api/break": breakData, "/api/evaluation": evaluation });
    render(<Quality />);
    await screen.findByText("Break mode");
    expect(screen.getAllByText("pass").length).toBe(breakData.scenarios.length);
    expect(screen.getByText(new RegExp(`${breakData.scenarios.length} of ${breakData.scenarios.length}`))).toBeTruthy();
    expect(screen.getByText(/Historical results from a run on/)).toBeTruthy();
    expect(screen.getByText("Limits of this evidence")).toBeTruthy();
    // every dataset draws a naive and a Clariflow bar with numerator / denominator
    for (const d of Object.values(evaluation.datasets)) {
      expect(screen.getByText(d.title)).toBeTruthy();
      expect(screen.getAllByText(`${d.totals.naive.risky} / ${d.totals.naive.slots}`).length).toBeGreaterThan(0);
      expect(screen.getAllByText(`${d.totals.clariflow.risky} / ${d.totals.clariflow.slots}`).length).toBeGreaterThan(0);
    }
  });

  it("flags a failing scenario instead of hiding it", async () => {
    const failing = structuredClone(breakData);
    failing.scenarios[0].passed = false;
    failing.scenarios[0].checks[0].passed = false;
    serve({ "/api/break": failing, "/api/evaluation": evaluation });
    render(<Quality />);
    await screen.findByText("FAIL");
    expect(screen.getByText(/5 of 6/)).toBeTruthy();
  });
});

describe("Naive vs Clariflow", () => {
  it("lists the demo recordings and shows the recorded comparison", async () => {
    serve({ "/api/demo-clips": clips, "/api/compare/demo/HE3": cmpHE3 });
    render(<Compare config={config} />);
    const he3 = await screen.findByRole("button", { name: /^HE3/ });
    fireEvent.click(he3);
    fireEvent.click(screen.getByRole("button", { name: /Compare \(recorded, free\)/ }));
    await screen.findByText("Naive: save what was heard");
    expect(screen.getByText("Clariflow: asks before it assumes")).toBeTruthy();
    expect(screen.getByText(/Recorded result from/)).toBeTruthy();
    expect(screen.getByText(/Would stop and ask/)).toBeTruthy();
    expect(screen.getAllByText(/no unit/).length).toBeGreaterThan(0);
  });

  it("renders a correction in the record view", async () => {
    serve({ "/api/demo-clips": clips, "/api/compare/demo/ME1": cmpME1 });
    render(<Compare config={config} />);
    fireEvent.click(await screen.findByRole("button", { name: /^ME1/ }));
    fireEvent.click(screen.getByRole("button", { name: /Compare \(recorded, free\)/ }));
    await waitFor(() => expect(screen.getByText(/corrected from 15/)).toBeTruthy());
  });
});

describe("Saved work orders tab", () => {
  const wo = {
    id: "d4d6ee98-aaaa", short_id: "WO-D4D6EE98", session_id: "s", language: "en", confirmed_revision: 1,
    location: "Boiler House, Line 1", readback: "Asset P-12. Observed: smoke.", readbacks: { mr: "असेट P-12. धूर.", hi: "असेट P-12. धुआं.", en: "Asset P-12. Observed: smoke." }, routing: null, created_at: "2026-11-04T10:00:00+00:00",
    payload: { asset: { id: "P-12", name: "Feed Water Pump 12" }, symptoms: [{ concept: "smoke", state: "present" }], reported_incident_time: null, measurements: [], cause: { status: "not_reported" }, immediate_action: null },
  };

  it("says so when nothing was saved from this browser, without calling the server", async () => {
    localStorage.clear();
    serve({});
    render(<Saved config={config} />);
    await screen.findByText(/No saved work orders yet/);
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("asks only for the ids this browser remembers and lists what comes back", async () => {
    localStorage.setItem("clariflow.saved", JSON.stringify(["11111111-2222-3333-4444-555555555555"]));
    serve({ "/api/work-orders/lookup": { work_orders: [wo] } });
    render(<Saved config={config} />);
    expect((await screen.findAllByText("WO-D4D6EE98")).length).toBeGreaterThan(0);
    const [, init] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ session_ids: ["11111111-2222-3333-4444-555555555555"] });
    expect(screen.getByText(/not sent to a maintenance system/)).toBeTruthy();
  });
});

describe("work order in every language", () => {
  const wo = {
    id: "abc12345-x", short_id: "WO-ABC12345", session_id: "11111111-2222-3333-4444-555555555555", language: "mr" as const,
    confirmed_revision: 2, location: "Boiler House, Line 1", readback: "असेट P-12. धूर.",
    readbacks: { mr: "असेट P-12. धूर.", hi: "एसेट P-12. धुआं.", en: "Asset P-12. Observed: smoke." }, routing: null,
    created_at: "2026-11-04T10:00:00+00:00",
    payload: { asset: { id: "P-12", name: "Feed Water Pump 12" }, symptoms: [{ concept: "smoke", state: "present" }], reported_incident_time: null, measurements: [], cause: { status: "not_reported" }, immediate_action: null },
  };

  it("opens in the language of the report, and switches to the others on tap", async () => {
    const { WorkOrderCard } = await import("./WorkOrderCard");
    const { container } = render(<WorkOrderCard wo={wo} />);
    const shown = () => container.querySelector(".wo-lang .wo-readback")?.textContent;
    expect(shown()).toBe("असेट P-12. धूर.");
    expect(screen.getByText(/This is the read-back that was confirmed \(मराठी\)/)).toBeTruthy();

    fireEvent.click(screen.getByRole("radio", { name: "English" }));
    expect(shown()).toBe("Asset P-12. Observed: smoke.");
    expect(screen.getByText(/The person confirmed the मराठी version/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Read aloud in English/ })).toBeTruthy();

    fireEvent.click(screen.getByRole("radio", { name: "हिन्दी" }));
    expect(shown()).toBe("एसेट P-12. धुआं.");
  });

  it("asks the server for the audio of the language on screen", async () => {
    const audio = await import("./audio");
    const { WorkOrderCard } = await import("./WorkOrderCard");
    render(<WorkOrderCard wo={wo} />);
    fireEvent.click(screen.getByRole("radio", { name: "हिन्दी" }));
    fireEvent.click(screen.getByRole("button", { name: /Read aloud in हिन्दी/ }));
    await waitFor(() => expect(audio.playUrl).toHaveBeenCalledWith(`/api/sessions/${wo.session_id}/work-order-audio?lang=hi`, expect.any(Function)));
  });

  it("prints all three languages", async () => {
    const { WorkOrderCard } = await import("./WorkOrderCard");
    const { container } = render(<WorkOrderCard wo={wo} />);
    const printed = container.querySelector(".print-only")?.textContent ?? "";
    for (const text of Object.values(wo.readbacks)) expect(printed).toContain(text);
  });
});

describe("work order urgency and simulated routing", () => {
  const routing = {
    simulated: true, rule: "emergency", note: null, urgency_labels: { en: "emergency", mr: "आणीबाणी", hi: "आपातकाल" },
    notify: [{ role: "plant_emergency_team", labels: { en: "Plant emergency team", mr: "प्लांट आपत्कालीन टीम", hi: "प्लांट आपातकालीन टीम" } }],
  };
  const base = {
    id: "abc12345-x", short_id: "WO-ABC12345", session_id: "11111111-2222-3333-4444-555555555555", language: "en" as const, confirmed_revision: 2,
    location: "Boiler House, Line 1", readback: "Asset P-12.", readbacks: { mr: "असेट P-12.", hi: "एसेट P-12.", en: "Asset P-12." },
    created_at: "2026-11-04T10:00:00+00:00",
    payload: {
      asset: { id: "P-12", name: "Feed Water Pump 12" }, symptoms: [], reported_incident_time: null, measurements: [], cause: { status: "not_reported" }, immediate_action: null,
      urgency: { status: "stated", level: "emergency", quote: ["emergency"] }, routing: { simulated: true, rule: "emergency", notify: ["plant_emergency_team"] },
    },
  };
  const cfg = {
    ...config,
    routing: { simulated: true, emergency_notice: { en: "If anyone is in danger, call your site emergency number now. This demo cannot dispatch anyone.", mr: "मराठी सूचना", hi: "हिन्दी सूचना" }, rules: [] },
  } as AppConfig;
  const rowsOf = (c: HTMLElement) => Object.fromEntries(Array.from(c.querySelectorAll(".wo-row")).map((r) => [r.querySelector("dt")?.textContent, r.querySelector("dd")?.textContent]));

  it("shows the urgency, the simulated recipients in the language on screen, and the safety notice", async () => {
    const { WorkOrderCard } = await import("./WorkOrderCard");
    const { container } = render(<WorkOrderCard wo={{ ...base, routing }} config={cfg} />);
    expect(rowsOf(container)["Urgency"]).toBe("Emergency");
    expect(rowsOf(container)["Would notify (simulated)"]).toBe("Plant emergency team");
    expect(screen.getByRole("alert").textContent).toContain("This demo cannot dispatch anyone");
    fireEvent.click(screen.getByRole("radio", { name: "मराठी" }));
    expect(rowsOf(container)["Would notify (simulated)"]).toBe("प्लांट आपत्कालीन टीम");
  });

  it("an older record without urgency shows no urgency or routing row, and invents none", async () => {
    const { WorkOrderCard } = await import("./WorkOrderCard");
    const legacy = { ...base.payload } as Record<string, unknown>;
    delete legacy.urgency;
    delete legacy.routing;
    const { container } = render(<WorkOrderCard wo={{ ...base, routing: null, payload: legacy }} config={cfg} />);
    const labels = Array.from(container.querySelectorAll(".wo-row dt")).map((d) => d.textContent);
    expect(labels).not.toContain("Urgency");
    expect(labels).not.toContain("Would notify (simulated)");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("the downloaded JSON carries the routing and says nothing was sent", async () => {
    const { exportObject } = await import("./workorder");
    const o = exportObject({ ...base, routing }) as Record<string, unknown>;
    expect(o.routing).toEqual(routing);
    expect(String(o.routing_note)).toMatch(/Nothing was sent to anyone/);
  });

  it("tags an emergency in the saved list", async () => {
    localStorage.setItem("clariflow.saved", JSON.stringify([base.session_id]));
    serve({ "/api/work-orders/lookup": { work_orders: [{ ...base, routing }] } });
    const { container } = render(<Saved config={cfg} />);
    await screen.findAllByText("WO-ABC12345");
    const tag = container.querySelector(".urg-tag");
    expect(tag?.textContent).toBe("emergency");
    expect(tag?.className).toContain("emergency");
  });
});
