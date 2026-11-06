import type { ReactNode } from "react";
import type { AuthUser } from "./api";

interface Props {
  onEnter: () => void;
  onShowAuth: () => void;
  user: AuthUser | null;
}

const ICONS = {
  speak: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" x2="12" y1="19" y2="22" />
    </svg>
  ),
  analyze: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12h3l3-9 4 18 3-9h7" />
    </svg>
  ),
  confirm: (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  ),
  speech: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M8 9h8" />
      <path d="M8 13h5" />
    </svg>
  ),
  trail: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  ),
  prisma: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="M9 9h6v6H9z" />
      <path d="M15 3v6" />
      <path d="M9 3v6" />
      <path d="M15 15v6" />
      <path d="M9 15v6" />
    </svg>
  ),
  timbre: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
    </svg>
  ),
  gate: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  ),
  mobile: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="14" height="20" x="5" y="2" rx="2" ry="2" />
      <line x1="12" x2="12.01" y1="18" y2="18" />
    </svg>
  ),
};

const STATS = [
  { value: "1.4B", label: "people in India" },
  { value: "22", label: "scheduled languages" },
  { value: "19,500+", label: "mother tongues" },
  { value: "89%", label: "Indians don't speak English as first language" },
];

const HOW: { num: string; icon: ReactNode; title: string; desc: string }[] = [
  {
    num: "01",
    icon: ICONS.speak,
    title: "Speak the fault",
    desc: "A technician speaks in Marathi, Hindi, English — or any mix. No typing, no forms.",
  },
  {
    num: "02",
    icon: ICONS.analyze,
    title: "AI understands & asks",
    desc: "Gnani Prisma transcribes the speech. Clariflow extracts: asset, symptom, readings, time — and asks exactly one focused follow-up if something's unclear.",
  },
  {
    num: "03",
    icon: ICONS.confirm,
    title: "Confirm & save",
    desc: "A human confirms the spoken read-back. Only then is the work order saved — permanently, with full evidence trails.",
  },
];

const FEATURES: { icon: ReactNode; title: string; desc: string }[] = [
  { icon: ICONS.speech, title: "Code-mixed speech", desc: "Handles Marathi-English, Hindi-English and pure speech seamlessly." },
  { icon: ICONS.trail, title: "Full evidence trail", desc: "Every field links back to the exact words the technician said." },
  { icon: ICONS.prisma, title: "Gnani Prisma STT", desc: "Sovereign Indian AI — no data leaves the country." },
  { icon: ICONS.timbre, title: "Gnani Timbre TTS", desc: "Questions and read-backs spoken aloud in the right language." },
  { icon: ICONS.gate, title: "Human confirmation gate", desc: "Zero false saves — work orders only write after a person confirms." },
  { icon: ICONS.mobile, title: "Mobile-first", desc: "Built for shop-floor conditions: noisy environments, one-hand use." },
];

export function LandingPage({ onEnter, onShowAuth, user }: Props) {
  return (
    <div className="landing">
      {/* ---- NAV ---- */}
      <nav className="land-nav">
        <div className="land-nav-in">
          <div className="land-brand">
            <span className="land-brand-name">Clariflow</span>
          </div>
          <div className="land-nav-actions">
            <a href="#how" className="land-link">How it works</a>
            <a href="#comparison" className="land-link">Why Clariflow</a>
            <a href="#features" className="land-link">Features</a>
            {user ? (
              <button type="button" className="btn primary small" onClick={onEnter}>Open app →</button>
            ) : (
              <>
                <button type="button" className="land-link" onClick={onShowAuth}>Sign in</button>
                <button type="button" className="btn primary small" onClick={onEnter}>Get started free</button>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ---- HERO ---- */}
      <section className="land-hero">
        <div className="land-hero-in">
          <span className="land-eyebrow">Enterprise Voice Copilot · Powered by Gnani</span>
          <h1 className="land-h1">
            Voice-first fault reporting<br />
            <span className="land-orange">for every Indian worker.</span>
          </h1>
          <p className="land-lead">
            A technician speaks a fault report in Marathi, Hindi, English — or any mix.
            Clariflow turns it into a verified, evidence-linked work order.
            Powered by <strong>Gnani Prisma</strong> STT and <strong>Gnani Timbre</strong> TTS.
          </p>
          <div className="land-cta-row">
            <button type="button" className="btn primary big" onClick={onEnter}>
              Try it now — no sign-up needed →
            </button>
            {!user && (
              <button type="button" className="btn secondary big" onClick={onShowAuth}>
                Create free account
              </button>
            )}
          </div>
          <p className="land-hint-sm">Works in Marathi · हिंदी · English · and any mix</p>
        </div>
      </section>

      {/* ---- WHY ---- */}
      <section className="land-why">
        <div className="land-section-in">
          <p className="land-section-eyebrow">Why voice? Why India?</p>
          <h2 className="land-h2">
            The next billion workers <em>won't type.</em> They'll talk.
          </h2>
          <p className="land-section-sub">
            Most software still assumes a keyboard and English. Clariflow is built for everyone else.
          </p>
          <div className="land-stats">
            {STATS.map(s => (
              <div key={s.label} className="land-stat">
                <strong>{s.value}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- HOW ---- */}
      <section className="land-how" id="how">
        <div className="land-section-in">
          <p className="land-section-eyebrow">How it works</p>
          <h2 className="land-h2">Three steps. Zero paperwork.</h2>
          <div className="land-steps">
            {HOW.map(h => (
              <div key={h.num} className="land-step">
                <span className="land-step-num">{h.num}</span>
                <span className="land-step-icon" aria-hidden="true">{h.icon}</span>
                <h3>{h.title}</h3>
                <p>{h.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- COMPARISON / WHY WE WIN ---- */}
      <section className="land-comparison" id="comparison">
        <div className="land-section-in">
          <p className="land-section-eyebrow">Enterprise Advantage</p>
          <h2 className="land-h2">Why standard LLMs fail on the factory floor.</h2>
          <p className="land-section-sub">
            Generic chatbots and cloud voice assistants hallucinate equipment IDs and silently corrupt industrial data.
            Clariflow is engineered for zero-tolerance plant environments.
          </p>
          <div className="land-comp-table-wrap">
            <table className="land-comp-table">
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Generic Chatbot / LLM</th>
                  <th>Clariflow (Sovereign Voice Copilot)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>Spoken Indic Code-Mix</strong><br/><span className="tbl-sub">Mixed Marathi-English &amp; Hindi-English</span></td>
                  <td><span className="comp-bad">✗ Hallucinates transliterations &amp; misses dialect shifts</span></td>
                  <td><span className="comp-ok">✓ Gnani Prisma v3.0 Indic Acoustic Steering</span></td>
                </tr>
                <tr>
                  <td><strong>Database Safety &amp; Writes</strong><br/><span className="tbl-sub">Equipment records &amp; maintenance work orders</span></td>
                  <td><span className="comp-bad">✗ Silent hallucinations &amp; unverified DB writes</span></td>
                  <td><span className="comp-ok">✓ SQLite Trigger Kernel: 0 unconfirmed writes</span></td>
                </tr>
                <tr>
                  <td><strong>Audit Trail &amp; Provenance</strong><br/><span className="tbl-sub">Verification for safety compliance</span></td>
                  <td><span className="comp-bad">✗ Black-box text without receipts</span></td>
                  <td><span className="comp-ok">✓ 100% word-level audio &amp; timestamp link</span></td>
                </tr>
                <tr>
                  <td><strong>Hands-Free Verification</strong><br/><span className="tbl-sub">Read-back confirmation on noisy shop-floor</span></td>
                  <td><span className="comp-bad">✗ Screen reading required</span></td>
                  <td><span className="comp-ok">✓ Gnani Timbre natural Indic voice readback</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ---- FEATURES ---- */}
      <section className="land-features" id="features">
        <div className="land-section-in">
          <p className="land-section-eyebrow">Features</p>
          <h2 className="land-h2">Built on sovereign Indian AI.</h2>
          <div className="land-feat-grid">
            {FEATURES.map(f => (
              <div key={f.title} className="land-feat">
                <span className="land-feat-icon" aria-hidden="true">{f.icon}</span>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- GNANI BADGE ---- */}
      <section className="land-powered">
        <div className="land-section-in">
          <p className="land-powered-label">Powered by</p>
          <div className="land-powered-badges">
            <div className="land-badge-item">
              <span className="land-badge-icon">{ICONS.prisma}</span>
              <div>
                <strong>Gnani Prisma v3.0</strong>
                <span>Speech-to-Text — Marathi, Hindi, English code-mix</span>
              </div>
            </div>
            <div className="land-badge-item">
              <span className="land-badge-icon">{ICONS.timbre}</span>
              <div>
                <strong>Gnani Timbre v3.0</strong>
                <span>Text-to-Speech — Natural Indian voice (Shivani)</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- BOTTOM CTA ---- */}
      <section className="land-bottom-cta">
        <div className="land-section-in">
          <h2 className="land-h2">Ready to try?</h2>
          <p className="land-section-sub">No sign-up needed. Works in your browser.</p>
          <button type="button" className="btn primary big" onClick={onEnter}>
            Open Clariflow →
          </button>
        </div>
      </section>

      {/* ---- FOOTER ---- */}
      <footer className="land-footer">
        <span>Enterprise Indic Speech Infrastructure powered by Gnani Prisma &amp; Timbre.</span>
        <span>© 2026 Clariflow · Sovereign Voice AI Operations</span>
      </footer>
    </div>
  );
}
