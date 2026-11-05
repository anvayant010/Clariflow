import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { friendlyError, Report, prettyPath } from "./Report";
import type { AppConfig, SessionState } from "./types";

// The player is not under test here (jsdom has no audio); the shared module is replaced.
vi.mock("./audio", () => ({ playUrl: vi.fn(async () => undefined), stopAudio: vi.fn() }));
vi.mock("./useRecorder", () => ({
  useRecorder: (_max: number, onClip: (b: Blob) => void) => ({
    state: "idle", seconds: 0, stop() {}, cancel() {}, start: async () => onClip(new Blob(["x"], { type: "audio/webm" })),
  }),
}));

const SID = "11111111-2222-3333-4444-555555555555";
const config: AppConfig = {
  app: "Clariflow", synthetic_demonstration: true, speech_configured: true, fixture_allowed: false,
  languages: [{ code: "mr", label: "मराठी" }, { code: "hi", label: "हिन्दी" }, { code: "en", label: "English" }],
  assets: [{ id: "P-12", name: "Feed Water Pump 12", type: "pump", location: "Boiler House" }],
  limits: { max_clip_seconds: 30, recordings_per_report: 15, voice_prompts_per_report: 30 },
  speech: { stt: "Gnani Prisma prisma-v3.0", tts: "Gnani Timbre timbre-v3.0", stt_config: "x" },
  routing: {
    simulated: true,
    emergency_notice: { en: "If anyone is in danger, call your site emergency number now. This demo cannot dispatch anyone.", mr: "कोणी धोक्यात असेल तर आत्ताच आपत्कालीन क्रमांक लावा.", hi: "अगर कोई खतरे में है तो अभी आपातकालीन नंबर मिलाएँ।" },
    rules: [
      { level: "can_wait", labels: { en: "can wait", mr: "थांबू शकतं", hi: "इंतज़ार कर सकते हैं" }, notify: [{ role: "maintenance_queue", labels: { en: "Maintenance queue", mr: "देखभाल रांग", hi: "रखरखाव कतार" } }], note: null },
      { level: "emergency", labels: { en: "emergency", mr: "आणीबाणी", hi: "आपातकाल" }, notify: [{ role: "plant_emergency_team", labels: { en: "Plant emergency team", mr: "प्लांट आपत्कालीन टीम", hi: "प्लांट आपातकालीन टीम" } }], note: null },
    ],
  },
};

function state(over: Partial<SessionState>): SessionState {
  return {
    session_id: SID, language: "en", status: "empty", revision: 1, synthetic_demonstration: true,
    turns: [], fields: [], history: [], question: null, notes: [], review: null, work_order: null,
    usage: { recordings_left: 14, voice_prompts_left: 29 }, urgency_level: null, ...over,
  };
}

const asking = state({
  status: "needs_answer",
  turns: [{ index: 0, source: "typed_clarification", source_label: "Typed (not speech)", text: "pressure 50", audio_url: null, language_code: null }],
  fields: [{
    candidate_id: "c1", label: "Pressure", value: "50 — unit not stated", state: "needs_answer", origin: "speech", heard: null, understood_as: null,
    receipts: [{ turn_index: 0, source: "typed_clarification", source_label: "Typed (not speech)", quote: "<script>x</script>",
      marked_html: "a &lt;script&gt;alert(1)&lt;/script&gt; <mark>pressure 50</mark>", audio_url: null }],
  }],
  question: {
    issue_id: "iss1", type: "missing_unit", text: "You said pressure 50. What is the unit?", language: "en",
    choices: [{ value: "PSI", label: "PSI" }, { value: "bar", label: "bar" }, { value: "unknown", label: "I don't know" }],
    accepts_number: false, audio_url: "/api/sessions/x/question-audio", attempts: 0, fallback_offered: false,
  },
});

const reviewing = state({
  status: "ready_for_review", revision: 3,
  review: { revision: 3, language: "en", readback: "Asset P-12. Pressure 50 PSI.", payload: {}, audio_url: "/api/sessions/x/review-audio", routing: null },
});

type Call = { url: string; body: unknown };
let calls: Call[];

function mockServer(initial: SessionState, onPost?: (url: string, body: any) => Response | undefined) {
  localStorage.setItem("clariflow.session", SID);
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : undefined;
    calls.push({ url, body });
    if (init?.method === "POST") {
      const custom = onPost?.(url, body);
      if (custom) return custom;
    }
    return new Response(JSON.stringify(initial), { status: 200 });
  }));
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("question card", () => {
  it("shows the question and sends the tapped answer for that issue", async () => {
    mockServer(asking, (url) => (url.endsWith("/choose") ? new Response(JSON.stringify(reviewing), { status: 200 }) : undefined));
    render(<Report config={config} />);
    expect(await screen.findByText("You said pressure 50. What is the unit?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "PSI" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/choose"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/choose"))?.body).toEqual({ issue_id: "iss1", choice: "PSI" });
    expect(await screen.findByText("Check before saving")).toBeTruthy();
  });

  it("shows server text literally and never as markup", async () => {
    mockServer(asking);
    const { container } = render(<Report config={config} />);
    await screen.findByText("One question");
    fireEvent.click(screen.getByRole("button", { name: /Pressure/ }));
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("blockquote")?.textContent).toContain("<script>alert(1)</script>");
    expect(container.querySelector("blockquote mark")?.textContent).toBe("pressure 50");
  });

  it("tells the user a spoken answer was not understood and changes nothing", async () => {
    mockServer(asking, (url) => url.endsWith("/text")
      ? new Response(JSON.stringify({ mode_used: "answer", understood: false, heard: "banana", error: null, attempts: 1, fallback_offered: false, state: asking }), { status: 200 })
      : undefined);
    render(<Report config={config} />);
    await screen.findByText("One question");
    fireEvent.click(screen.getByText("Type an answer instead"));
    fireEvent.change(screen.getByPlaceholderText("Type your answer"), { target: { value: "banana" } });
    fireEvent.click(screen.getByRole("button", { name: "Send typed text" }));
    expect(await screen.findByText(/could not match that to an answer/)).toBeTruthy();
    expect(screen.getByText("One question")).toBeTruthy();
  });
});

describe("confirm", () => {
  it("sends the reviewed revision, and reuses the same key if the tap is retried", async () => {
    let n = 0;
    mockServer(reviewing, (url) => {
      if (!url.endsWith("/confirm")) return undefined;
      return n++ === 0
        ? new Response(JSON.stringify({ error: { code: "network_blip", message: "Try again." } }), { status: 503 })
        : new Response(JSON.stringify(state({ status: "saved", revision: 3, work_order: { id: "wo-id-1", short_id: "WO-1", session_id: SID, language: "en", confirmed_revision: 3, location: null, readback: "Asset P-12.", readbacks: { mr: "mr text", hi: "hi text", en: "Asset P-12." }, payload: {}, routing: null, created_at: "2026-11-04T10:00:00+00:00" } })), { status: 200 });
    });
    render(<Report config={config} />);
    const save = await screen.findByRole("button", { name: /Yes, this is correct/ });
    fireEvent.click(save);
    expect(await screen.findByText(/Try again/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Yes, this is correct/ }));
    await screen.findByText("Saved as WO-1");
    const posts = calls.filter((c) => c.url.endsWith("/confirm")).map((c) => c.body as { revision: number; idempotency_key: string });
    expect(posts).toHaveLength(2);
    expect(posts[0].revision).toBe(3);
    expect(posts[0].idempotency_key.length).toBeGreaterThanOrEqual(8);
    expect(posts[1].idempotency_key).toBe(posts[0].idempotency_key);
    expect(screen.queryByRole("button", { name: /Yes, this is correct/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Download JSON" })).toBeTruthy();
    expect(JSON.parse(localStorage.getItem("clariflow.saved") ?? "[]")).toEqual([SID]); // remembered for the Saved tab
  });

  it("offers no save button while a question is open", async () => {
    mockServer(asking);
    render(<Report config={config} />);
    await screen.findByText("One question");
    expect(screen.queryByRole("button", { name: /Yes, this is correct/ })).toBeNull();
  });
});

describe("helpers", () => {
  it("makes field paths readable", () => {
    expect(prettyPath("measurement.pressure")).toBe("pressure");
    expect(prettyPath("immediate_action")).toBe("immediate action");
  });
});

describe("answers that are not understood", () => {
  const openQuestion = (choices: { value: string; label: string }[]) =>
    state({ ...asking, question: { ...asking.question!, choices } });
  const typeAnswer = async (text: string) => {
    fireEvent.click(await screen.findByText("Type an answer instead"));
    fireEvent.change(screen.getByPlaceholderText("Type your answer"), { target: { value: text } });
    fireEvent.click(screen.getByRole("button", { name: "Send typed text" }));
  };
  const notUnderstood = (s: SessionState) => new Response(JSON.stringify({ mode_used: "answer", understood: false, heard: "x", error: null, attempts: 1, fallback_offered: false, state: s }), { status: 200 });

  it("only says 'tap one of the answers' when there are answers to tap", async () => {
    const withTaps = openQuestion([{ value: "PSI", label: "PSI" }]);
    mockServer(withTaps, (url) => (url.endsWith("/text") ? notUnderstood(withTaps) : undefined));
    render(<Report config={config} />);
    await typeAnswer("x");
    expect(await screen.findByText(/or tap one of the answers/)).toBeTruthy();
  });

  it("says 'type it instead' when the question has no choices", async () => {
    const noTaps = openQuestion([]);
    mockServer(noTaps, (url) => (url.endsWith("/text") ? notUnderstood(noTaps) : undefined));
    render(<Report config={config} />);
    await typeAnswer("x");
    expect(await screen.findByText(/or type it instead/)).toBeTruthy();
    expect(screen.queryByText(/tap one of the answers/)).toBeNull();
  });
});

describe("adding the cause", () => {
  const ok = (s: SessionState, mode: string, understood = true) =>
    new Response(JSON.stringify({ mode_used: mode, understood, heard: "belt slipped", error: null, attempts: 0, fallback_offered: false, state: s }), { status: 200 });

  it("sends the cause in its own mode and says it was added", async () => {
    const withCause = state({ ...reviewing, revision: 4, review: { ...reviewing.review!, revision: 4 } });
    mockServer(reviewing, (url) => (url.endsWith("/text") ? ok(withCause, "cause") : undefined));
    render(<Report config={config} />);
    fireEvent.click(await screen.findByText("Add the cause (optional)"));
    fireEvent.change(screen.getByLabelText("Type the cause"), { target: { value: "belt slipped" } });
    fireEvent.click(screen.getByRole("button", { name: "Use as the cause" }));
    expect(await screen.findByText(/Cause added, in the words you typed/)).toBeTruthy();
    const sent = calls.find((c) => c.url.endsWith("/text"))?.body as { text: string; mode: string };
    expect(sent).toMatchObject({ text: "belt slipped", mode: "cause" });
  });

  it("each text box has its own label (no shared id)", async () => {
    mockServer(reviewing);
    const { container } = render(<Report config={config} />);
    await screen.findByText("Add the cause (optional)");
    const ids = Array.from(container.querySelectorAll("textarea")).map((t) => t.id);
    expect(ids.length).toBeGreaterThanOrEqual(2);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("never stays silent when added detail changes nothing", async () => {
    mockServer(reviewing, (url) => (url.endsWith("/text") ? ok(reviewing, "report") : undefined));
    render(<Report config={config} />);
    fireEvent.click(await screen.findByText("Something is wrong or missing? Add more"));
    fireEvent.change(screen.getByLabelText("Add more detail"), { target: { value: "missing आहे" } });
    fireEvent.click(screen.getByRole("button", { name: "Send typed text" }));
    expect(await screen.findByText(/did not add anything to the work order/)).toBeTruthy();
    expect(screen.getByText(/use “Add the cause” below/)).toBeTruthy();
  });

  it("says so when no cause could be heard", async () => {
    mockServer(reviewing, (url) => (url.endsWith("/text") ? ok(reviewing, "cause", false) : undefined));
    render(<Report config={config} />);
    fireEvent.click(await screen.findByText("Add the cause (optional)"));
    fireEvent.change(screen.getByLabelText("Type the cause"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Use as the cause" }));
    expect(await screen.findByText(/could not hear a cause/)).toBeTruthy();
  });
});

describe("heard → understood next to each field", () => {
  const field = (label: string, value: string, heard: string | null, understood: string | null, stateName = "ok") => ({
    candidate_id: label, label, value, state: stateName, origin: "speech", heard, understood_as: understood, receipts: [],
  });
  const withFields = state({
    status: "ready_for_review", revision: 2,
    review: { revision: 2, language: "mr", readback: "x", payload: {}, audio_url: "/a", routing: null },
    fields: [
      field("Pressure", "50 PSI", "पन्नास", "50"),
      field("Reported time", "10:30", "साडेदहा वाजता", "10:30"),
      field("Asset", "P-12 · Feed Water Pump 12", null, null),
    ],
    history: [field("Pressure", "15", "पंधरा", "15", "history")],
  });

  it("shows the words and what they became, only where something was converted", async () => {
    mockServer(withFields);
    const { container } = render(<Report config={config} />);
    await screen.findByText("What I understood so far");
    const lines = Array.from(container.querySelectorAll(".conv")).filter((e) => !e.closest("details")).map((e) => e.textContent?.replace(/\s+/g, " ").trim());
    expect(lines).toContain("You said “पन्नास” → 50");
    expect(lines).toContain("You said “साडेदहा वाजता” → 10:30");
    expect(lines).toHaveLength(2); // the asset (P-12 -> P-12) shows nothing; history is collapsed
  });

  it("also shows it for the earlier, corrected value", async () => {
    mockServer(withFields);
    const { container } = render(<Report config={config} />);
    await screen.findByText("What I understood so far");
    const hist = Array.from(container.querySelectorAll("details .conv")).map((e) => e.textContent?.replace(/\s+/g, " ").trim());
    expect(hist).toContain("You said “पंधरा” → 15");
  });

  it("is readable by a screen reader as one sentence", async () => {
    mockServer(withFields);
    render(<Report config={config} />);
    await screen.findByText("What I understood so far");
    expect(screen.getAllByLabelText("Heard पन्नास, understood as 50").length).toBe(1);
  });
});


describe("checking a spoken cause", () => {
  const voiceCause = (heard: string, s: SessionState) =>
    new Response(JSON.stringify({ mode_used: "cause", understood: true, heard, error: null, attempts: 0, fallback_offered: false, state: s }), { status: 200 });

  it("shows what was heard, pre-fills an editable box, and lets the person correct it", async () => {
    const after = state({ ...reviewing, revision: 4, review: { ...reviewing.review!, revision: 4 } });
    mockServer(reviewing, (url) => (url.endsWith("/audio") ? voiceCause("आणि संचालक आहे", after) : undefined));
    render(<Report config={config} />);
    fireEvent.click(await screen.findByText("Add the cause (optional)"));
    fireEvent.click(screen.getByRole("button", { name: "Tap and say the cause" }));
    expect(await screen.findByText(/I heard the cause as “आणि संचालक आहे”/)).toBeTruthy();
    const box = screen.getByLabelText("Type the cause") as HTMLTextAreaElement;
    expect(box.value).toBe("आणि संचालक आहे"); // editable, not applied blindly
    fireEvent.change(box, { target: { value: "कारण ऑपरेटर आहे" } });
    fireEvent.click(screen.getByRole("button", { name: "Use as the cause" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/text"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/text"))?.body).toMatchObject({ text: "कारण ऑपरेटर आहे", mode: "cause" });
  });

  it("keeps the cause panel open after a spoken cause", async () => {
    const after = state({ ...reviewing, revision: 4, review: { ...reviewing.review!, revision: 4 } });
    mockServer(reviewing, (url) => (url.endsWith("/audio") ? voiceCause("belt slipped", after) : undefined));
    const { container } = render(<Report config={config} />);
    fireEvent.click(await screen.findByText("Add the cause (optional)"));
    fireEvent.click(screen.getByRole("button", { name: "Tap and say the cause" }));
    await screen.findByText(/I heard the cause as “belt slipped”/);
    const panel = Array.from(container.querySelectorAll("details")).find((d) => d.textContent?.includes("Add the cause (optional)"));
    expect(panel?.open).toBe(true);
  });
});

describe("plain-language errors", () => {
  it("never shows the raw reason", () => {
    expect(friendlyError("no speech recognised")).toMatch(/could not hear any speech/);
    expect(friendlyError("speech recognition failed (timeout)")).toMatch(/speech service had a problem/);
    expect(friendlyError("something internal")).toMatch(/could not be processed/);
    for (const e of ["no speech recognised", "speech recognition failed (timeout)", "x"]) expect(friendlyError(e)).not.toContain("recognised");
  });
});

describe("rows of 'What I understood so far'", () => {
  const row = (over: object) => ({ candidate_id: "r", label: "Cause", value: "belt slipped (as reported)", state: "ok", origin: "speech", heard: null, understood_as: null, receipts: [], ...over });
  it("draws a tick (not a second 'heard' word) for understood fields, and 'as reported' as a quiet note", async () => {
    mockServer(state({ ...reviewing, fields: [row({}), row({ candidate_id: "q", label: "Pressure", value: "50 — unit not stated", state: "needs_answer" })] }));
    const { container } = render(<Report config={config} />);
    await screen.findByText("What I understood so far");
    expect(screen.getByRole("img", { name: "understood" })).toBeTruthy();
    expect(screen.getByText("needs your answer")).toBeTruthy();
    expect(screen.queryByText("heard")).toBeNull();
    expect(container.querySelector(".f-note")?.textContent?.trim()).toBe("as reported");
    expect(container.querySelector(".f-value")?.textContent).toContain("belt slipped");
    expect(container.querySelector(".f-value")?.textContent).not.toContain("(as reported)");
  });
});

// ---------------------------------------------------------------- urgency and simulated routing

const role = (en: string, mr: string, hi: string) => ({ en, mr, hi });
const routingStop = {
  simulated: true, rule: "stop_work", note: null,
  urgency_labels: { en: "stop work now", mr: "आत्ताच काम थांबवा", hi: "अभी काम रोकें" },
  notify: [
    { role: "maintenance_head", labels: role("Maintenance head", "देखभाल प्रमुख", "रखरखाव प्रमुख") },
    { role: "production_supervisor", labels: role("Production supervisor", "उत्पादन सुपरवायझर", "उत्पादन सुपरवाइज़र") },
  ],
};
const urgencyQuestion = state({
  status: "needs_answer", language: "mr",
  question: {
    issue_id: "u1", type: "missing_urgency", text: "हे किती तातडीचं आहे?", language: "mr", accepts_number: false, audio_url: "/api/q", attempts: 0, fallback_offered: false,
    choices: [
      { value: "can_wait", label: "थांबू शकतं" }, { value: "today", label: "आज लक्ष द्यावं लागेल" }, { value: "stop_work", label: "आत्ताच काम थांबवा" },
      { value: "emergency", label: "आणीबाणी: माणसांना धोका किंवा आग" }, { value: "unknown", label: "I don't know" },
    ],
  },
});

describe("the urgency question", () => {
  it("shows the safety notice, the four levels and 'not sure', and sends the tapped level", async () => {
    mockServer(urgencyQuestion, (url) => (url.endsWith("/choose") ? new Response(JSON.stringify(reviewing), { status: 200 }) : undefined));
    const { container } = render(<Report config={config} />);
    expect(await screen.findByText("हे किती तातडीचं आहे?")).toBeTruthy();
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("कोणी धोक्यात असेल"); // in the report's language
    expect(alert.textContent).toContain("This demo cannot dispatch anyone"); // and in English
    expect(container.querySelectorAll(".choices .btn.choice").length).toBe(5);
    expect(container.querySelector(".btn.choice.danger")?.textContent).toContain("आणीबाणी");
    fireEvent.click(screen.getByRole("button", { name: "आत्ताच काम थांबवा" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/choose"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/choose"))?.body).toEqual({ issue_id: "u1", choice: "stop_work" });
  });

  it("does not show the emergency notice for an ordinary question", async () => {
    mockServer(asking);
    render(<Report config={config} />);
    await screen.findByText("One question");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("simulated routing on the review card", () => {
  const withRouting = state({ ...reviewing, language: "en", urgency_level: "stop_work", review: { ...reviewing.review!, routing: routingStop } });

  it("says who WOULD be notified, that it is simulated, and that nothing is sent", async () => {
    mockServer(withRouting);
    render(<Report config={config} />);
    await screen.findByText("Check before saving");
    const line = screen.getByLabelText("Simulated routing");
    expect(line.textContent).toContain("simulated");
    expect(line.textContent).toContain("stop work now");
    expect(line.textContent).toContain("If saved, this would notify: Maintenance head, Production supervisor");
    expect(line.textContent).toContain("Nothing is sent to anyone");
    expect(screen.queryByRole("alert")).toBeNull(); // stop work is not an emergency
  });

  it("names the roles in the report's language", async () => {
    mockServer(state({ ...withRouting, language: "mr" }));
    render(<Report config={config} />);
    await screen.findByText("Check before saving");
    expect(screen.getByLabelText("Simulated routing").textContent).toContain("देखभाल प्रमुख, उत्पादन सुपरवायझर");
  });

  it("shows the editable rule table from the server config", async () => {
    mockServer(withRouting);
    const { container } = render(<Report config={config} />);
    await screen.findByText("How routing works (simulated)");
    const rows = Array.from(container.querySelectorAll(".tbl tbody tr")).map((r) => r.textContent);
    expect(rows.some((t) => t?.includes("can wait") && t.includes("Maintenance queue"))).toBe(true);
    expect(rows.some((t) => t?.includes("emergency") && t.includes("Plant emergency team"))).toBe(true);
    expect(container.textContent).toContain("routing.json");
  });

  it("shows the emergency notice for a stated emergency, before and after saving", async () => {
    const emergency = state({ ...reviewing, urgency_level: "emergency", review: { ...reviewing.review!, routing: { ...routingStop, rule: "emergency" } } });
    mockServer(emergency);
    render(<Report config={config} />);
    expect((await screen.findByRole("alert")).textContent).toContain("call your site emergency number now");
    cleanup();
    const saved = state({
      status: "saved", urgency_level: "emergency",
      work_order: {
        id: "i", short_id: "WO-I", session_id: SID, language: "en", confirmed_revision: 1, location: null, readback: "x",
        readbacks: { mr: "x", hi: "x", en: "x" }, routing: { ...routingStop, rule: "emergency" }, payload: {}, created_at: "2026-11-04T10:00:00+00:00",
      },
    });
    mockServer(saved);
    render(<Report config={config} />);
    expect((await screen.findByRole("alert")).textContent).toContain("This demo cannot dispatch anyone");
    expect(screen.getAllByRole("alert").length).toBe(1); // once, not twice
  });
});
