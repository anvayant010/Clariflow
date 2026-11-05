import { useRef, useState } from "react";
import { EmergencyNotice } from "./Routing";
import type { AppConfig, Lang, WorkOrder } from "./types";
import { PlayButton } from "./ui";
import { exportObject, formatSaved, LANG_LABEL, LANGS, summarise } from "./workorder";

function download(wo: WorkOrder) {
  const blob = new Blob([JSON.stringify(exportObject(wo), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${wo.short_id}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Print just this card: everything else on the page is hidden by the print stylesheet. */
function print(card: HTMLElement | null) {
  if (!card) return;
  card.classList.add("print-this");
  document.body.classList.add("print-one");
  const done = () => {
    card.classList.remove("print-this");
    document.body.classList.remove("print-one");
    window.removeEventListener("afterprint", done);
  };
  window.addEventListener("afterprint", done);
  window.print();
}

export function WorkOrderCard({ wo, config }: { wo: WorkOrder; config?: AppConfig }) {
  const ref = useRef<HTMLElement | null>(null);
  const [lang, setLang] = useState<Lang>(wo.language);
  const rows = summarise(wo.payload, wo.location, wo.routing, lang);
  return (
    <article className="wo" ref={ref} aria-label={`Work order ${wo.short_id}`}>
      <header className="wo-head">
        <div>
          <div className="wo-num mono">{wo.short_id}</div>
          <div className="muted">Saved {formatSaved(wo.created_at)}</div>
        </div>
        <span className="badge demo">Synthetic demonstration</span>
      </header>
      {config && wo.routing?.rule === "emergency" && <EmergencyNotice config={config} language={lang} />}
      <dl className="wo-rows">
        {rows.map((r, i) => (
          <div key={i} className="wo-row">
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
      <div className="wo-lang no-print">
        <div className="seg" role="radiogroup" aria-label="Show this work order in">
          {LANGS.map((l) => (
            <button key={l} type="button" role="radio" aria-checked={lang === l} className={lang === l ? "on" : ""} onClick={() => setLang(l)}>
              {LANG_LABEL[l]}
            </button>
          ))}
        </div>
        <p className="wo-readback" lang={lang}>{wo.readbacks[lang]}</p>
        <PlayButton key={lang} url={`/api/sessions/${wo.session_id}/work-order-audio?lang=${lang}`} label={`Read aloud in ${LANG_LABEL[lang]}`} />
        <p className="hint">
          {lang === wo.language
            ? `This is the read-back that was confirmed (${LANG_LABEL[wo.language]}).`
            : `The same saved record in ${LANG_LABEL[lang]}, made from fixed templates. The person confirmed the ${LANG_LABEL[wo.language]} version.`}{" "}
          Marathi and Hindi wording is a draft awaiting native-speaker review.
        </p>
      </div>
      <div className="print-only">
        {LANGS.map((l) => (
          <p key={l} lang={l} className="wo-readback"><strong>{LANG_LABEL[l]}:</strong> {wo.readbacks[l]}</p>
        ))}
      </div>
      <p className="hint">Saved after a person confirmed revision {wo.confirmed_revision}. Saved work orders cannot be edited in this demo.</p>
      <div className="actions no-print">
        <button type="button" className="btn secondary" onClick={() => download(wo)}>Download JSON</button>
        <button type="button" className="btn secondary" onClick={() => print(ref.current)}>Print</button>
      </div>
    </article>
  );
}
