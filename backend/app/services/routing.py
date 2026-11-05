"""Simulated routing: who WOULD be told about a work order, from a visible, editable rule file (routing.json).

Nothing is ever sent. The saved work order records which roles the rule named at the time it was saved, and every
screen that shows them says "simulated". Urgency is the person's own answer; this module never decides it.
"""
import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("routing.json")
LANGUAGES = ("mr", "hi", "en")


@lru_cache(maxsize=1)
def table() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def route(level: str | None) -> dict:
    """The rule for an urgency level; an unknown/missing level uses the 'unknown' rule (a supervisor decides)."""
    levels = table()["levels"]
    key = level if level in levels else "unknown"
    out = {"simulated": True, "rule": key, "notify": list(levels[key]["notify"])}
    if levels[key].get("note"):
        out["note"] = levels[key]["note"]
    return out


def role_label(role: str, language: str) -> str:
    labels = table()["roles"].get(role, {})
    return labels.get(language) or labels.get("en") or role.replace("_", " ")


def role_labels(role: str) -> dict[str, str]:
    return {lang: role_label(role, lang) for lang in LANGUAGES}


def emergency_notice() -> dict[str, str]:
    return dict(table()["emergency_notice"])
