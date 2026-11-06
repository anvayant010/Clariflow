import type {
  AppConfig, BreakResult, CompareResult, DemoClip, Evaluation, Lang, SessionState, TurnOutcome, WorkOrder,
} from "./types";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public requestId?: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { credentials: "include", ...init });
  } catch {
    throw new ApiError("network", "Cannot reach the server. Check that it is running and try again.", 0);
  }
  if (!res.ok) {
    let code = "http_" + res.status;
    let message = "Something went wrong.";
    let requestId: string | undefined;
    try {
      const j = await res.json();
      code = j.error?.code ?? code;
      message = j.error?.message ?? message;
      requestId = j.error?.request_id;
    } catch {
      /* non-JSON error body: keep the generic message */
    }
    throw new ApiError(code, message, res.status, requestId);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** File name only tells the server nothing: it identifies the container from the bytes. */
function audioForm(blob: Blob, extra: Record<string, string> = {}): FormData {
  const f = new FormData();
  f.append("file", blob, "clip");
  for (const [k, v] of Object.entries(extra)) f.append(k, v);
  return f;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface UserStats {
  total_sessions: number;
  saved_orders: number;
  languages: Record<string, number>;
}

export const api = {
  config: () => call<AppConfig>("/api/config"),
  createSession: (language: Lang) => call<SessionState>("/api/sessions", json({ language })),
  getSession: (id: string) => call<SessionState>(`/api/sessions/${id}`),
  setLanguage: (id: string, language: Lang) => call<SessionState>(`/api/sessions/${id}/language`, json({ language })),
  sendAudio: (id: string, blob: Blob, mode: "report" | "answer" | "cause") =>
    call<TurnOutcome>(`/api/sessions/${id}/audio`, { method: "POST", body: audioForm(blob, { mode }) }),
  sendText: (id: string, text: string, mode: "report" | "answer" | "cause") =>
    call<TurnOutcome>(`/api/sessions/${id}/text`, json({ text, mode, source: "typed" })),
  choose: (id: string, issueId: string, choice: string) =>
    call<SessionState>(`/api/sessions/${id}/choose`, json({ issue_id: issueId, choice })),
  confirm: (id: string, revision: number, idempotencyKey: string) =>
    call<SessionState>(`/api/sessions/${id}/confirm`, json({ revision, idempotency_key: idempotencyKey })),

  lookupWorkOrders: (sessionIds: string[]) =>
    call<{ work_orders: WorkOrder[] }>("/api/work-orders/lookup", json({ session_ids: sessionIds })),

  breakMode: () => call<BreakResult>("/api/break"),
  evaluation: () => call<Evaluation>("/api/evaluation"),
  demoClips: () => call<{ note: string; clips: DemoClip[] }>("/api/demo-clips"),
  compareDemo: (clipId: string, live: boolean) =>
    call<CompareResult>(`/api/compare/demo/${clipId}?live=${live}`, { method: "POST" }),
  compareAudio: (blob: Blob) => call<CompareResult>("/api/compare/audio", { method: "POST", body: audioForm(blob) }),
  compareText: (text: string) => call<CompareResult>("/api/compare/text", json({ text })),

  // Auth
  authRegister: (email: string, name: string, password: string) =>
    call<{ user: AuthUser; access_token: string }>("/api/auth/register", json({ email, name, password })),
  authLogin: (email: string, password: string) =>
    call<{ user: AuthUser; access_token: string }>("/api/auth/login", json({ email, password })),
  authLogout: () => call<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  authMe: () => call<AuthUser>("/api/auth/me"),
  authStats: () => call<UserStats>("/api/auth/stats"),
};

/** A fresh key per (session, revision); a retry of the same click reuses it so a double tap cannot save twice. */
export function newKey(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return Array.from({ length: 24 }, () => Math.floor(Math.random() * 36).toString(36)).join("");
  }
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.requestId ? `${e.message} (ref ${e.requestId})` : e.message;
  return "Something went wrong.";
}
