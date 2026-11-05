"""Side by side: the same report through the naive baseline and through Clariflow.

Nothing is saved by this module. The naive column is the baseline defined in services/evaluation.py
(ours, not a real product); the Clariflow column is the draft BEFORE any human answer.
"""
from backend.app.domain.schemas import Asset
from backend.app.services import evaluation as ev

NAIVE_STT = "plain verbatim STT, no keyterms"
CLARIFLOW_STT = "codemix STT + keyterms (our own asset IDs)"


def _assumptions(record: ev.Record, flags: list[str]) -> list[str]:
    """What the naive path did silently, for each thing a careful system would have asked about."""
    out = []
    for f in flags:
        if f == "ambiguous_asset" and record.asset:
            out.append(f"Picked {record.asset} out of several possible assets, without asking.")
        elif f == "ambiguous_unit" and any(m.unit == "°C" for m in record.measurements):
            out.append("Assumed Celsius for 'degree', without asking.")
        elif f == "ambiguous_time" and record.time:
            out.append(f"Saved the time as {record.time} with no AM/PM, without asking.")
        elif f == "missing_unit" and any(m.unit is None for m in record.measurements):
            out.append("Saved a number with no unit and no warning.")
        elif f == "conflicting_observation":
            out.append("Saved two statements that contradict each other, both as fact.")
        elif f == "missing_value":
            out.append("Dropped a measurement it could not read, without saying so.")
        elif f == "unknown_asset" and not record.asset:
            out.append("Saved the report with no asset and no warning.")
        elif f == "missing_symptom":
            out.append("Saved the report with no symptom and no warning.")
    return out


def compare(naive_text: str, clariflow_text: str, catalogue: list[Asset], mode: str, truth: dict | None = None) -> dict:
    naive = ev.naive_record(naive_text, catalogue)
    clari = ev.clariflow_record(clariflow_text, catalogue)
    careful_flags = ev.clariflow_record(naive_text, catalogue).flags  # what a careful system raises for THIS transcript
    out = {
        "mode": mode,  # "recorded" (historical Prisma output), "live", or "typed"
        "definition": ev.NAIVE_DEFINITION,
        "naive": {"stt": NAIVE_STT, "transcript": naive_text, "record": naive.model_dump(),
                  "assumptions": _assumptions(naive, careful_flags), "asked": []},
        "clariflow": {"stt": CLARIFLOW_STT, "transcript": clariflow_text, "record": clari.model_dump(),
                      "asked": clari.flags},
        "score": None,
    }
    if truth is not None:
        sn, sc = ev.score(truth, naive), ev.score(truth, clari)
        out["score"] = {"naive": sn.model_dump() | {"risky": sn.risky}, "clariflow": sc.model_dump() | {"risky": sc.risky},
                        "note": "Scored against truth written by the code author from the recording script."}
    return out
