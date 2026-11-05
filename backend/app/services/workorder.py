"""Build the saved work-order payload and a plain read-back from a draft's ACTIVE candidates."""
import json
from functools import lru_cache
from pathlib import Path

from backend.app.domain.issues import active
from backend.app.services import routing
from backend.app.services.timefmt import clock12
from backend.app.domain.schemas import Asset, CandidateStatus, Draft

LEXICON_DIR = Path(__file__).resolve().parents[1] / "lexicon"


@lru_cache(maxsize=1)
def _readback_data() -> dict:
    return json.loads((LEXICON_DIR / "readback.json").read_text(encoding="utf-8"))


def _cause(c) -> dict:
    """Never inferred: either the person said it was unknown, or these are their own words (with the quote)."""
    if c is None:
        return {"status": "not_reported", "value": None}
    if c.status == CandidateStatus.UNKNOWN or c.normalised_value is None:
        return {"status": "unknown", "value": None}
    return {"status": "reported", "value": str(c.normalised_value), "quote": [e.quote for e in c.evidence]}


def _urgency(c) -> dict:
    """The person's own answer (stated in the report, answered, or 'not sure'): never inferred."""
    if c is None:
        return {"status": "not_reported", "level": None}
    if c.status == CandidateStatus.UNKNOWN or c.normalised_value is None:
        return {"status": "unknown", "level": None, "quote": [e.quote for e in c.evidence]}
    return {"status": "stated", "level": str(c.normalised_value), "quote": [e.quote for e in c.evidence],
            "origin": c.origin.value}


def build_payload(draft: Draft, catalogue: list[Asset]) -> dict:
    by_id = {c.id: c for c in draft.candidates}
    asset_c = next(iter(active(draft, "asset")), None)
    asset = next((a for a in catalogue if asset_c and a.id == asset_c.normalised_value), None)
    time_c = next(iter(active(draft, "time")), None)
    urgency = _urgency(next(iter(active(draft, "urgency")), None))
    cause_c = next(iter(active(draft, "cause")), None)
    action_c = next(iter(active(draft, "immediate_action")), None)

    measurements, corrections = [], []
    for c in active(draft, "measurement"):
        entry = {"kind": c.meta.get("kind"), "value": c.normalised_value, "unit": c.unit,
                 "value_status": "stated" if c.normalised_value is not None else "unknown",
                 "unit_status": "unknown" if c.meta.get("unit_status") == "unknown" else ("stated" if c.unit else "missing"),
                 "earlier_value_not_heard": bool(c.meta.get("old_value_missing")),
                 "quote": [e.quote for e in c.evidence]}
        old = by_id.get(c.meta.get("corrected_from_id"))
        if old is not None:
            entry["corrected_from"] = {"value": old.normalised_value, "unit": old.unit}
            corrections.append({"field": c.field_path, "from": old.normalised_value, "to": c.normalised_value})
        measurements.append(entry)

    return {
        "synthetic_demonstration": True,
        "revision": draft.revision,
        "asset": {"id": asset.id, "name": asset.display_name} if asset else None,
        "symptoms": [{"concept": c.field_path.split(".", 1)[1], "state": c.normalised_value,
                      "origin": c.origin.value, "quote": [e.quote for e in c.evidence]} for c in active(draft, "symptom")],
        "reported_incident_time": None if not time_c else {
            "raw": time_c.raw_value, "value": time_c.normalised_value,
            "status": "unknown" if time_c.status == CandidateStatus.UNKNOWN else "stated",
            **({"corrected_from": by_id[time_c.meta["corrected_from_id"]].normalised_value}
               if time_c.meta.get("corrected_from_id") in by_id else {})},
        "measurements": measurements,
        "cause": _cause(cause_c),
        "urgency": urgency,
        "routing": routing.route(urgency["level"]),  # SIMULATED: which roles would be told; nothing is sent
        "immediate_action": action_c.normalised_value if action_c else None,
        "corrections": corrections,
        "waived_unknowns": [i.field_paths for i in draft.issues if i.status.value == "waived_unknown"],
    }


def evidence_snapshot(draft: Draft) -> list[dict]:
    out = []
    for c in active(draft):
        for e in c.evidence:
            out.append({"field": c.field_path, "origin": c.origin.value, "segment_id": e.segment_id,
                        "quote": e.quote, "start": e.start_char, "end": e.end_char})
    return out


def readback(payload: dict, language: str = "en") -> str:
    """Read-back of exactly the payload that will be saved, from templates (no free-form generation).
    Marathi/Hindi wording is DRAFT until a native speaker has reviewed lexicon/readback.json."""
    data = _readback_data()
    T, lang = data["templates"][language], language

    def label(group: str, key: str) -> str:
        return data[group].get(key, {}).get(lang, key.replace("_", " "))

    def names(state: str) -> list[str]:
        return [label("symptoms", s["concept"]) for s in payload["symptoms"] if s["state"] == state]

    parts = []
    a = payload["asset"]
    parts.append(T["asset"].format(id=a["id"], name=a["name"]) if a else T["no_asset"])
    for state, key in (("present", "observed"), ("absent", "absent"), ("not_confirmed", "not_confirmed")):
        if names(state):
            parts.append(T[key].format(list=T["join"].join(names(state))))
    t = payload["reported_incident_time"]
    if t:
        fix = T["time_fix"].format(old=clock12(t["corrected_from"])) if t.get("corrected_from") else ""
        parts.append(T["time"].format(t=clock12(t["value"]), fix=fix) if t["value"] else T["time_unknown"].format(fix=fix))
    for m in payload["measurements"]:
        kind = label("kinds", m["kind"])
        if m["value"] is None:
            parts.append(T["measure_unknown"].format(kind=kind))
            continue
        unit = m["unit"] or (T["unit_unknown"] if m["unit_status"] == "unknown" else T["unit_none"])
        fix = T["measure_fix"].format(old=m["corrected_from"]["value"]) if "corrected_from" in m else ""
        if m.get("earlier_value_not_heard"):
            fix += T["dropped"]
        parts.append(T["measure"].format(kind=kind, value=m["value"], unit=unit, fix=fix))
    cause = payload["cause"]
    parts.append(T["cause_reported"].format(c=cause["value"]) if cause["status"] == "reported"
                 else T["cause_unknown"] if cause["status"] == "unknown" else T["cause_none"])
    if payload["immediate_action"]:
        parts.append(T["action"].format(a=label("actions", payload["immediate_action"])))
    urgency = payload.get("urgency")  # records saved before urgency existed have none
    if urgency and urgency["status"] != "not_reported":
        parts.append(T["urgency"].format(u=label("urgency_levels", urgency["level"] or "unknown")))
    route = payload.get("routing")
    if route:
        parts.append(T["notify"].format(r=", ".join(routing.role_label(r, lang) for r in route["notify"])))
    return " ".join(parts)
