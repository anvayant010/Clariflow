import { useEffect, useState } from "react";
import { api, errorText } from "./api";
import type { AppConfig, WorkOrder } from "./types";
import { Banner, Spinner } from "./ui";
import { WorkOrderCard } from "./WorkOrderCard";
import { formatSaved, savedIds } from "./workorder";

export function Saved({ config }: { config: AppConfig }) {
  const [orders, setOrders] = useState<WorkOrder[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const ids = savedIds();
    if (ids.length === 0) {
      setOrders([]);
      return;
    }
    api.lookupWorkOrders(ids).then((r) => setOrders(r.work_orders)).catch((e) => setErr(errorText(e)));
  }, []);

  if (err) return <Banner kind="error">{err}</Banner>;
  if (!orders) return <Spinner label="Loading saved work orders…" />;

  return (
    <div className="stack">
      <section className="card">
        <h2>Saved work orders</h2>
        <p>Every confirmed work order appears here, newest first. Saved records are read-only.</p>
        <p className="hint">Demo: work orders are kept in this app only and are not sent to a maintenance system.</p>
        <details className="more">
          <summary>About this list</summary>
          <p className="hint">
            There is no sign-in in this demo, so the list shows the work orders saved from this device. Clearing the site data
            empties the list, though the records themselves stay on the server.
          </p>
        </details>
      </section>
      {orders.length === 0 && <Banner kind="info">No saved work orders yet. Make a report on the Report tab and confirm it.</Banner>}
      <div className="grid2">
      {orders.map((wo) => (
        <details key={wo.id} className="card flat saved-item">
          <summary>
            <span className="mono">{wo.short_id}</span>
            {" · "}
            {(wo.payload.asset as { id?: string } | null)?.id ?? "equipment not identified"}
            {wo.routing && wo.routing.rule !== "unknown" && (
              <span className={`urg-tag${wo.routing.rule === "emergency" ? " emergency" : ""}`}>{wo.routing.urgency_labels.en}</span>
            )}
            <span className="muted"> · {formatSaved(wo.created_at)}</span>
          </summary>
          <WorkOrderCard wo={wo} config={config} />
        </details>
      ))}
      </div>
    </div>
  );
}
