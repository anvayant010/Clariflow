import { useEffect, useId, useRef, useState } from "react";
import { errorText } from "./api";
import { playUrl, stopAudio } from "./audio";
import { useRecorder } from "./useRecorder";

export function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

const ICONS: Record<string, React.ReactNode> = {
  report: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
  saved: <><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" /><rect x="9" y="3" width="6" height="4" rx="1.5" /><path d="M9 13l2 2 4-4" /></>,
  compare: <><rect x="3" y="4" width="7" height="16" rx="2" /><rect x="14" y="4" width="7" height="16" rx="2" /></>,
  shield: <><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" /><path d="M9 12l2 2 4-4" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  moon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
  expand: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  compress: <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />,
  speaker: <><path d="M11 5L6 9H3v6h3l5 4V5z" /><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /></>,
  help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h.01" /></>,
};

/** Small line icons, drawn inline so the app needs no icon library. Decorative: the button or heading carries the name. */
export function Icon({ name, size = 18 }: { name: keyof typeof ICONS | string; size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {ICONS[name]}
    </svg>
  );
}

export function Logo({ size = 46 }: { size?: number }) {
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} aria-hidden="true" focusable="false" className="logo">
      <defs>
        <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff781f" />
          <stop offset="1" stopColor="#ea580c" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#lg)" />
      <path d="M8 24h4M15 18v12M20 13v22M25 19v10" stroke="rgba(255,255,255,.75)" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M28 25l5 5 8-10" stroke="#fff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="busy" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function Banner({ kind, children }: { kind: "error" | "info" | "ok"; children: React.ReactNode }) {
  return (
    <div className={`banner ${kind}`} role={kind === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}

/** Plays a server audio URL. `auto` tries to play once when the URL first appears (a tap just happened). */
export function PlayButton({ url, label, auto = false, big = false }: { url: string; label: string; auto?: boolean; big?: boolean }) {
  const [phase, setPhase] = useState<"idle" | "loading" | "playing">("idle");
  const [problem, setProblem] = useState("");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const play = async (quiet: boolean) => {
    setProblem("");
    setPhase("loading");
    try {
      await playUrl(url, () => alive.current && setPhase("idle"));
      if (alive.current) setPhase("playing");
    } catch (e) {
      if (!alive.current) return;
      setPhase("idle");
      const code = (e as { code?: string }).code;
      if (!(quiet && code === "blocked")) setProblem(errorText(e));
    }
  };

  useEffect(() => {
    if (auto) void play(true);
    return () => {
      if (auto) stopAudio();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, auto]);

  const toggle = () => {
    if (phase === "playing") {
      stopAudio();
      setPhase("idle");
    } else void play(false);
  };

  return (
    <div className="play">
      <button type="button" className={big ? "btn secondary big-play" : "btn secondary small"} onClick={toggle} disabled={phase === "loading"}>
        {phase === "loading" ? "Loading…" : phase === "playing" ? "■ Stop" : `▶ ${label}`}
      </button>
      {problem && <span className="hint warn">{problem}</span>}
    </div>
  );
}

/** Tap to start, tap to stop. The parent gets the recorded blob. */
export function RecordButton({ maxSeconds, onClip, onProblem, disabled, idleLabel }: {
  maxSeconds: number;
  onClip: (b: Blob) => void;
  onProblem: (m: string) => void;
  disabled?: boolean;
  idleLabel: string;
}) {
  const { state, seconds, start, stop } = useRecorder(Math.max(5, maxSeconds - 2), onClip, onProblem);

  if (state === "unsupported") {
    return <Banner kind="info">Recording is not available in this browser or on this connection (it needs https or localhost). You can type instead.</Banner>;
  }
  const recording = state === "recording";
  const limit = Math.max(5, maxSeconds - 2);
  const used = Math.min(1, seconds / limit); // the ring fills as the time limit is used up
  return (
    <div className="recorder">
      <div className={`rec-wrap${recording ? " live" : ""}`} style={{ "--p": used } as React.CSSProperties}>
        <button
          type="button"
          className={`rec ${recording ? "on" : ""}`}
          onClick={recording ? stop : () => void start()}
          disabled={disabled && !recording}
          aria-pressed={recording}
          aria-label={recording ? "Stop recording" : idleLabel}
        >
          {recording ? <span className="stop-square" aria-hidden="true" /> : <MicIcon />}
        </button>
      </div>
      {recording && (
        <div className="wave" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => <span key={i} style={{ animationDelay: `${i * 0.11}s` }} />)}
        </div>
      )}
      <div className="rec-label" aria-live="polite">
        {recording ? `Recording… ${seconds}s (max ${maxSeconds - 2}s). Tap to stop.` : idleLabel}
      </div>
      {state === "denied" && (
        <Banner kind="error">The microphone is blocked. Allow it in your browser's site settings, or type instead.</Banner>
      )}
    </div>
  );
}

export function TypeBox({ placeholder, onSend, disabled, label, initial = "", sendLabel = "Send typed text" }: {
  placeholder: string; onSend: (t: string) => void; disabled?: boolean; label: string; initial?: string; sendLabel?: string;
}) {
  const [text, setText] = useState(initial);
  const id = useId(); // several text boxes can be on screen: each label must point at its own box
  return (
    <form
      className="typebox"
      onSubmit={(e) => {
        e.preventDefault();
        const t = text.trim();
        if (t) {
          onSend(t);
          setText("");
        }
      }}
    >
      <label className="sr-only" htmlFor={id}>{label}</label>
      <textarea id={id} value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} rows={2} maxLength={2000} disabled={disabled} />
      <button type="submit" className="btn secondary" disabled={disabled || !text.trim()}>{sendLabel}</button>
      <p className="hint">Typed text is labelled “not speech” in the record.</p>
    </form>
  );
}
