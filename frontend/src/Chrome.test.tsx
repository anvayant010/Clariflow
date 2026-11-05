import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { Report } from "./Report";
import type { AppConfig, SessionState } from "./types";

vi.mock("./audio", () => ({ playUrl: vi.fn(async () => undefined), stopAudio: vi.fn() }));
vi.mock("./useRecorder", () => ({
  useRecorder: () => ({ state: "idle", seconds: 0, stop() {}, cancel() {}, start: async () => undefined }),
}));

const config: AppConfig = {
  app: "Clariflow", synthetic_demonstration: true, speech_configured: true, fixture_allowed: false,
  languages: [{ code: "mr", label: "मराठी" }, { code: "hi", label: "हिन्दी" }, { code: "en", label: "English" }],
  assets: [{ id: "P-12", name: "Feed Water Pump 12", type: "pump", location: "Boiler House" }],
  limits: { max_clip_seconds: 30, recordings_per_report: 15, voice_prompts_per_report: 30 },
  speech: { stt: "Gnani Prisma prisma-v3.0", tts: "Gnani Timbre timbre-v3.0", stt_config: "x" },
  routing: { simulated: true, emergency_notice: { en: "n", mr: "n", hi: "n" }, rules: [] },
};

const SID = "11111111-2222-3333-4444-555555555555";
function session(status: SessionState["status"]): SessionState {
  return {
    session_id: SID, language: "en", status, revision: 1, synthetic_demonstration: true,
    turns: [], fields: [], history: [], question: null, notes: [], review: null, work_order: null,
    usage: { recordings_left: 14, voice_prompts_left: 29 }, urgency_level: null,
  };
}

function serve(initial?: SessionState) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (String(url).endsWith("/api/config")) return new Response(JSON.stringify(config), { status: 200 });
    if (initial) return new Response(JSON.stringify(initial), { status: 200 });
    return new Response("{}", { status: 404 });
  }));
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  window.history.replaceState({}, "", "/");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("progress steps", () => {
  it("starts at Speak on an empty report", async () => {
    serve();
    render(<Report config={config} />);
    const now = await screen.findByText("Speak");
    expect(now.closest("li")?.getAttribute("aria-current")).toBe("step");
    expect(screen.getByText("Confirm").closest("li")?.getAttribute("aria-current")).toBeNull();
  });

  it("is at Check while a question is open, with Speak done", async () => {
    localStorage.setItem("clariflow.session", SID);
    serve(session("needs_answer"));
    render(<Report config={config} />);
    await waitFor(() => expect(screen.getByText("Check").closest("li")?.getAttribute("aria-current")).toBe("step"));
    expect(screen.getByText("Speak").closest("li")?.className).toContain("done");
  });

  it("tells the app when a report is under way, and when it is not", async () => {
    localStorage.setItem("clariflow.session", SID);
    serve(session("ready_for_review"));
    const seen: string[] = [];
    render(<Report config={config} onStatus={(s) => seen.push(s)} />);
    await waitFor(() => expect(seen).toContain("ready_for_review"));
  });
});

describe("layout and theme controls", () => {
  it("is the compact layout by default, and Wide view switches it and is remembered", async () => {
    serve();
    const { container } = render(<App />);
    const toggle = await screen.findByRole("button", { name: /Wide view/ });
    expect(container.querySelector(".app")?.className).toBe("app");
    fireEvent.click(toggle);
    expect(container.querySelector(".app")?.className).toBe("app wide");
    expect(localStorage.getItem("clariflow.wide")).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: /Compact view/ }));
    expect(container.querySelector(".app")?.className).toBe("app");
    expect(localStorage.getItem("clariflow.wide")).toBe("0");
  });

  it("opens wide when the link asks for it", async () => {
    window.history.replaceState({}, "", "/?view=wide");
    serve();
    const { container } = render(<App />);
    await screen.findByRole("button", { name: /Compact view/ });
    expect(container.querySelector(".app")?.className).toBe("app wide");
  });

  it("switches the theme, sets it on the page and remembers it", async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Switch to (dark|light) theme/ }));
    const chosen = document.documentElement.getAttribute("data-theme");
    expect(chosen === "dark" || chosen === "light").toBe(true);
    expect(localStorage.getItem("clariflow.theme")).toBe(chosen);
    fireEvent.click(screen.getByRole("button", { name: /Switch to (dark|light) theme/ }));
    expect(document.documentElement.getAttribute("data-theme")).not.toBe(chosen);
  });

  it("still works when the browser blocks storage", async () => {
    serve();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Wide view/ }));
    expect(await screen.findByRole("button", { name: /Compact view/ })).toBeTruthy();
    vi.restoreAllMocks();
  });

  it("shows the headline before a report starts, and takes it away while one is under way", async () => {
    serve();
    const first = render(<App />);
    expect(await screen.findByText("Turn a spoken fault report into a checked work order.")).toBeTruthy();
    first.unmount();
    localStorage.setItem("clariflow.session", SID);
    serve(session("needs_answer"));
    render(<App />);
    await screen.findByRole("button", { name: /Wide view/ });
    await waitFor(() => expect(screen.queryByText("Turn a spoken fault report into a checked work order.")).toBeNull());
  });

  it("keeps the Synthetic demonstration label visible (in the footer), and the navigation reachable", async () => {
    serve();
    render(<App />);
    expect((await screen.findAllByText("Synthetic demonstration")).length).toBeGreaterThan(0);
    for (const name of ["Report", "Saved work orders", "Naive vs Clariflow", "Break mode"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
  });

  it("puts the equipment list beside the recorder in wide view, and inside the card in compact view", async () => {
    serve();
    const wide = render(<Report config={config} wide />);
    await screen.findByText("Equipment in this fictional plant");
    expect(wide.container.querySelector(".hero-card details")?.textContent ?? "").not.toContain("Equipment in this fictional plant");
    expect((wide.container.querySelectorAll(".col")[1] as HTMLElement).textContent).toContain("Feed Water Pump 12");
    cleanup();
    const compact = render(<Report config={config} />);
    await screen.findByText("Equipment in this fictional plant");
    expect(compact.container.querySelectorAll(".col").length).toBe(1);
    expect(compact.container.querySelector(".hero-card")?.textContent).toContain("Equipment in this fictional plant");
  });

  it("shows the review as labelled rows, keeps the read-back wording one tap away, and states nothing it was not given", async () => {
    localStorage.setItem("clariflow.session", SID);
    const reviewing: SessionState = {
      ...session("ready_for_review"),
      review: {
        revision: 2, language: "en", readback: "Asset P-12. Observed: smoke.", audio_url: "/a", routing: null,
        payload: {
          asset: { id: "P-12", name: "Feed Water Pump 12" }, symptoms: [{ concept: "smoke", state: "present" }],
          urgency: { status: "stated", level: "can_wait" }, cause: { status: "not_reported" }, measurements: [],
        },
      },
    };
    serve(reviewing);
    render(<Report config={config} />);
    const list = await screen.findByLabelText("What will be saved");
    expect(list.textContent).toContain("P-12 · Feed Water Pump 12");
    expect(list.textContent).toContain("Boiler House");
    expect(list.textContent).toContain("smoke: present");
    expect(list.textContent).toContain("Can wait");
    expect(list.textContent).toContain("not reported"); // the cause: never guessed
    expect(list.textContent).not.toContain("Immediate action");
    expect(screen.getByText("Read-back wording")).toBeTruthy();
    expect(screen.getByText("Asset P-12. Observed: smoke.")).toBeTruthy();
  });
});
