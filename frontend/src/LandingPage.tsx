import type { AuthUser } from "./api";

interface Props {
  onEnter: () => void;
  onShowAuth: () => void;
  user: AuthUser | null;
}

const STATS = [
  { value: "1.4B", label: "people in India" },
  { value: "22", label: "scheduled languages" },
  { value: "19,500+", label: "mother tongues" },
  { value: "89%", label: "Indians don't speak English as first language" },
];

const HOW = [
  {
    num: "01",
    icon: "🎙️",
    title: "Speak the fault",
    desc: "A technician speaks in Marathi, Hindi, English — or any mix. No typing, no forms.",
  },
  {
    num: "02",
    icon: "🔍",
    title: "AI understands & asks",
    desc: "Gnani Prisma transcribes the speech. Clariflow extracts: asset, symptom, readings, time — and asks exactly one focused follow-up if something's unclear.",
  },
  {
    num: "03",
    icon: "✅",
    title: "Confirm & save",
    desc: "A human confirms the spoken read-back. Only then is the work order saved — permanently, with full evidence trails.",
  },
];

const FEATURES = [
  { icon: "🗣️", title: "Code-mixed speech", desc: "Handles Marathi-English, Hindi-English and pure speech seamlessly." },
  { icon: "🔗", title: "Full evidence trail", desc: "Every field links back to the exact words the technician said." },
  { icon: "🤖", title: "Gnani Prisma STT", desc: "Sovereign Indian AI — no data leaves the country." },
  { icon: "📢", title: "Gnani Timbre TTS", desc: "Questions and read-backs spoken aloud in the right language." },
  { icon: "🔒", title: "Human confirmation gate", desc: "Zero false saves — work orders only write after a person confirms." },
  { icon: "📱", title: "Mobile-first", desc: "Built for shop-floor conditions: noisy environments, one-hand use." },
];

export function LandingPage({ onEnter, onShowAuth, user }: Props) {
  return (
    <div className="landing">
      {/* ---- NAV ---- */}
      <nav className="land-nav">
        <div className="land-nav-in">
          <div className="land-brand">
            <span className="cf-mark" aria-hidden="true">CF</span>
            <span className="land-brand-name">Clariflow</span>
          </div>
          <div className="land-nav-actions">
            <a href="#how" className="land-link">How it works</a>
            <a href="#features" className="land-link">Features</a>
            {user ? (
              <button type="button" className="btn primary small" onClick={onEnter}>Open app →</button>
            ) : (
              <>
                <button type="button" className="btn secondary small" onClick={onShowAuth}>Sign in</button>
                <button type="button" className="btn primary small" onClick={onShowAuth}>Get started free</button>
              </>
            )}
          </div>
        </div>
      </nav>

      {/* ---- HERO ---- */}
      <section className="land-hero">
        <div className="land-hero-in">
          <span className="land-eyebrow">Great Indian AI Internship Challenge · Gnani.ai</span>
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
              <span className="land-badge-icon">🗣️</span>
              <div>
                <strong>Gnani Prisma v3.0</strong>
                <span>Speech-to-Text — Marathi, Hindi, English code-mix</span>
              </div>
            </div>
            <div className="land-badge-item">
              <span className="land-badge-icon">📢</span>
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
        <span className="badge demo">Synthetic demonstration — fictional plant & made-up data only</span>
        <span>Speech by Gnani Prisma &amp; Gnani Timbre. Built for the Great Indian AI Internship Challenge.</span>
      </footer>
    </div>
  );
}

