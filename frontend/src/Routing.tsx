import type { AppConfig, Lang, Routing } from "./types";

const LABEL: Record<Lang, string> = { mr: "मराठी", hi: "हिन्दी", en: "English" };

/**
 * The safety notice for an emergency. Shown in the report's language, and in English too when that is different, so
 * anyone looking at the screen can read it. It never promises anything: this demo cannot dispatch anyone.
 */
export function EmergencyNotice({ config, language }: { config: AppConfig; language: Lang }) {
  const notice = config.routing.emergency_notice;
  return (
    <div className="notice danger" role="alert">
      <strong lang={language}>{notice[language]}</strong>
      {language !== "en" && <div lang="en">{notice.en}</div>}
    </div>
  );
}

/** "If saved, this would notify (simulated): …". Always says simulated; names who, never claims anything was sent. */
export function RoutingLine({ routing, language, saved = false }: { routing: Routing; language: Lang; saved?: boolean }) {
  const who = routing.notify.map((n) => n.labels[language] ?? n.labels.en).join(", ");
  return (
    <div className="routing" aria-label="Simulated routing">
      <div>
        <span className="badge st-needs_answer">simulated</span>{" "}
        <strong>Urgency:</strong> <span lang={language}>{routing.urgency_labels[language]}</span>
      </div>
      <div>
        {saved ? "Would have notified" : "If saved, this would notify"}: <strong lang={language}>{who}</strong>
      </div>
      {routing.note && <div className="hint">Rule: {routing.note}.</div>}
      <div className="hint">Nothing is sent to anyone: this is a demonstration of the routing rule.</div>
    </div>
  );
}

/** The visible rule table: urgency level to roles. It is read from routing.json, so changing that file changes this. */
export function RoutingRules({ config, language }: { config: AppConfig; language: Lang }) {
  return (
    <details className="more">
      <summary>How routing works (simulated)</summary>
      <table className="tbl">
        <thead>
          <tr><th>Urgency</th><th>Would notify</th></tr>
        </thead>
        <tbody>
          {config.routing.rules.map((r) => (
            <tr key={r.level}>
              <td lang={language}>{r.labels[language]}</td>
              <td lang={language}>{r.notify.map((n) => n.labels[language]).join(", ")}{r.note ? ` (${r.note})` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">
        The rules live in the file <span className="mono">backend/app/services/routing.json</span> and can be edited. Role names are a
        fictional plant's. Marathi and Hindi wording is a draft awaiting native-speaker review. Nothing is ever sent.
      </p>
      <p className="hint">Shown in {LABEL[language]}.</p>
    </details>
  );
}
