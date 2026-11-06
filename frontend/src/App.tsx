import { useEffect, useState } from "react";
import { api, type AuthUser, errorText } from "./api";
import { AuthModal } from "./AuthModal";
import { Compare } from "./Compare";
import { LandingPage } from "./LandingPage";
import { Quality } from "./Quality";
import { Report } from "./Report";
import { Saved } from "./Saved";
import type { AppConfig } from "./types";
import { Banner, Icon, Spinner } from "./ui";

type Tab = "report" | "saved" | "compare" | "quality";
const TABS: { id: Tab; label: string; short: string; icon: string }[] = [
  { id: "report", label: "Report", short: "Report", icon: "report" },
  { id: "saved", label: "Saved work orders", short: "Saved", icon: "saved" },
  { id: "compare", label: "Naive vs Clariflow", short: "Compare", icon: "compare" },
  { id: "quality", label: "Break mode", short: "Break mode", icon: "shield" },
];

type Theme = "light" | "dark";

/** Small per-browser preferences. Storage can be blocked, so every read and write is guarded; the app works without it. */
const pref = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string | null) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch {
      /* ignore */
    }
  },
};

/** Optional link settings, e.g. /?view=wide&theme=light, so a view can be shared or filmed without clicking. */
const param = (name: string): string | null => {
  try {
    return new URLSearchParams(window.location.search).get(name);
  } catch {
    return null;
  }
};

const systemTheme = (): Theme => {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
};

export function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState<Tab>("report");
  const [wide, setWide] = useState(() => (param("view") ? param("view") === "wide" : pref.get("clariflow.wide") === "1"));
  const [theme, setTheme] = useState<Theme | null>(() => {
    const t = param("theme") ?? pref.get("clariflow.theme");
    return t === "light" || t === "dark" ? t : null; // null = follow the device setting
  });
  // The headline only shows before a report starts, so the question and the draft are never pushed down the screen.
  const [reportActive, setReportActive] = useState(false);

  // Auth state — null = guest (fully functional, no gate)
  const [user, setUser] = useState<AuthUser | null>(null);
  const [showAuth, setShowAuth] = useState(false);
  // Landing page — shown once per browser until the user clicks "Open app"
  const [showLanding, setShowLanding] = useState(() => {
    if (param("app") === "1") return false;
    if (param("landing") === "1") return true;
    try {
      if ((import.meta as any).env?.MODE === "test") return false;
      return !localStorage.getItem("clariflow.entered");
    } catch {
      return false;
    }
  });

  useEffect(() => {
    api.config().then(setConfig).catch((e) => setErr(errorText(e)));
    // Restore auth from httpOnly cookie silently — 401 just means guest mode
    api.authMe().then((u) => {
      if (u && typeof u.id === "string" && typeof u.name === "string" && typeof u.email === "string") {
        setUser(u);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme) root.setAttribute("data-theme", theme);
    else root.removeAttribute("data-theme");
  }, [theme]);

  const handleEnter = () => {
    try { localStorage.setItem("clariflow.entered", "1"); } catch {}
    setShowLanding(false);
  };

  const shownTheme: Theme = theme ?? systemTheme();
  const toggleTheme = () => {
    const next: Theme = shownTheme === "dark" ? "light" : "dark";
    setTheme(next);
    pref.set("clariflow.theme", next);
  };
  const toggleWide = () => {
    setWide(!wide);
    pref.set("clariflow.wide", wide ? "0" : "1");
  };

  if (showLanding) {
    return (
      <>
        <LandingPage
          user={user}
          onEnter={handleEnter}
          onShowAuth={() => setShowAuth(true)}
        />
        {showAuth && (
          <AuthModal
            onAuth={(u) => { setUser(u); setShowAuth(false); }}
          />
        )}
      </>
    );
  }

  return (
    <div className={`app${wide ? " wide" : ""}`}>
      {showAuth && (
        <AuthModal
          onAuth={(u) => { setUser(u); setShowAuth(false); }}
        />
      )}
      <header className="topbar">
        <div className="topbar-in">
          <div className="brand">
            <h1>Clariflow</h1>
          </div>

          <nav className="tabs" aria-label="Sections">
            {TABS.map((t) => (
              <button key={t.id} type="button" className={tab === t.id ? "on" : ""} aria-current={tab === t.id ? "page" : undefined} onClick={() => setTab(t.id)}>
                <Icon name={t.icon} size={20} />
                <span className="tl-full">{t.label}</span>
                <span className="tl-short" aria-hidden="true">{t.short}</span>
              </button>
            ))}
          </nav>

          <div className="tools">
            {user && user.name ? (
              <div className="user-chip">
                <span className="user-chip-av">{(user.name[0] || "U").toUpperCase()}</span>
                <span>{(user.name.split(" ")[0] || "User")}</span>
                <button type="button" className="link" style={{ margin: 0, padding: "0 0 0 4px" }}
                  onClick={() => api.authLogout().then(() => setUser(null)).catch(() => {})}>
                  Sign out
                </button>
              </div>
            ) : (
              <button type="button" className="tool" onClick={() => setShowAuth(true)}>Sign in</button>
            )}
            <button type="button" className="tool wide-toggle" onClick={toggleWide} aria-pressed={wide}
              title={wide ? "Back to the compact layout" : "Use the wide two-column layout"}>
              <Icon name={wide ? "compress" : "expand"} size={17} />
              <span className="tool-label">{wide ? "Compact view" : "Wide view"}</span>
            </button>
            <button type="button" className="tool icon-only" onClick={toggleTheme}
              aria-label={shownTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              title={shownTheme === "dark" ? "Light theme" : "Dark theme"}>
              <Icon name={shownTheme === "dark" ? "sun" : "moon"} size={17} />
            </button>
          </div>
        </div>
      </header>

      <div className="page">
        {tab === "report" && !reportActive && (
          <section className="hero" aria-label="What Clariflow is">
            <h2 className="hero-title">Turn a spoken fault report into a checked work order.</h2>
            <p className="hero-sub">
              A technician speaks in Marathi, Hindi, English or a mix. Clariflow shows what it understood and where each
              detail came from, and nothing is saved until a person confirms.
            </p>
            <ol className="how">
              <li><span className="n">1</span><span><strong>Speak</strong> the problem: which equipment, what is wrong, any readings.</span></li>
              <li><span className="n">2</span><span><strong>Check</strong> the draft. Every line links to the exact words you said. If something is unclear, it asks one question.</span></li>
              <li><span className="n">3</span><span><strong>Confirm</strong> the read-back. Only then is the work order saved.</span></li>
            </ol>
          </section>
        )}

        <main>
          {err && <Banner kind="error">{err}</Banner>}
          {!config && !err && <Spinner label="Connecting…" />}
          {config && !config.speech_configured && tab !== "quality" && tab !== "saved" && (
            <Banner kind="info">Speech is not configured on this server, so recording is off. Typed input still works.</Banner>
          )}
          {config && tab === "report" && <Report config={config} wide={wide} onStatus={(s) => setReportActive(s !== "empty")} />}
          {config && tab === "saved" && <Saved config={config} />}
          {config && tab === "compare" && <Compare config={config} />}
          {config && tab === "quality" && <Quality />}
        </main>

        <footer className="legal">
          <span className="badge demo sr-only">Synthetic demonstration</span>
          Enterprise Indic Speech Infrastructure powered by {config?.speech.stt ?? "Gnani Prisma"} and {config?.speech.tts ?? "Gnani Timbre"}.
        </footer>
      </div>
    </div>
  );
}
