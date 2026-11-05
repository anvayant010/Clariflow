"""Language lexicons (numbers, time words, correction markers, units) merged into one lookup.

Code-mixed speech means all configured languages are active at once, so the normaliser
only ever sees this merged, language-agnostic structure. Adding a language = adding a JSON file.
"""
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

LEXICON_DIR = Path(__file__).resolve().parents[1] / "lexicon"
DEFAULT_LANGUAGES = ("mr", "hi", "en", "en_deva")  # en_deva = English as Prisma writes it in Devanagari

_DROP = dict.fromkeys(map(ord, "​‌‍﻿"))


def norm(s: str) -> str:
    """Lookup key: NFC, casefold, no zero-width chars/nukta, chandrabindu->anusvara, ऱ->र."""
    s = unicodedata.normalize("NFC", s).casefold().translate(_DROP)
    return (
        s.replace("़", "")
        .replace("ँ", "ं")
        .replace("ऱ", "र")
        .replace("’", "'")
    )


@dataclass
class Lexicon:
    numbers: dict[str, int] = field(default_factory=dict)
    multipliers: dict[str, int] = field(default_factory=dict)
    tens_compound_words: set[str] = field(default_factory=set)
    clock_plain: set[str] = field(default_factory=set)
    clock_with_minutes: set[str] = field(default_factory=set)
    minute_markers: set[str] = field(default_factory=set)
    time_fractions: list[dict] = field(default_factory=list)
    attach_prefixes: list[str] = field(default_factory=list)  # longest first
    cues_before: set[str] = field(default_factory=set)
    cues_after: set[str] = field(default_factory=set)
    am: list[list[str]] = field(default_factory=list)
    pm: list[list[str]] = field(default_factory=list)
    dayparts: dict[str, str] = field(default_factory=dict)
    correction_markers: list[list[str]] = field(default_factory=list)  # longest first
    units: dict[str, dict] = field(default_factory=dict)
    unit_phrases: list[list[str]] = field(default_factory=list)  # multi-word unit keys, longest first
    concepts: dict[str, list[list[str]]] = field(default_factory=dict)  # "symptom:leakage" -> phrases (word lists)
    negators: set[str] = field(default_factory=set)
    cause_fillers: set[str] = field(default_factory=set)  # "cause IS overload": words dropped right after a cause cue
    clause_breaks: set[str] = field(default_factory=set)  # "and", "but"...: a negation does not reach across them
    temporal_markers: set[str] = field(default_factory=set)
    measure_nouns: dict[str, str] = field(default_factory=dict)  # word -> measurement kind
    number_suffix_hints: list[str] = field(default_factory=list)  # word endings that signal a number part (mr "शे")
    decimal_points: set[str] = field(default_factory=set)  # "two POINT five"
    plus_half: list[list[str]] = field(default_factory=list)  # "three AND A HALF"


def _merge_unique(target: dict, source: dict, label: str, lang: str) -> None:
    for key, value in source.items():
        if key in target and target[key] != value:
            raise ValueError(f"lexicon conflict in {label}: {key!r} = {target[key]} vs {value} ({lang})")
        target[key] = value


def load_lexicon(languages: tuple[str, ...] = DEFAULT_LANGUAGES, directory: Path = LEXICON_DIR) -> Lexicon:
    lex = Lexicon()
    for lang in languages:
        data = json.loads((Path(directory) / f"{lang}.json").read_text(encoding="utf-8"))
        _merge_unique(lex.numbers, {norm(k): v for k, v in data["numbers"].items()}, "numbers", lang)
        _merge_unique(lex.multipliers, {norm(k): v for k, v in data["multipliers"].items()}, "multipliers", lang)
        _merge_unique(lex.units, {norm(k): v for k, v in data["units"].items()}, "units", lang)
        _merge_unique(lex.dayparts, {norm(k): v for k, v in data["dayparts"].items()}, "dayparts", lang)
        lex.tens_compound_words |= {norm(w) for w in data["tens_compound_words"]}
        lex.clock_plain |= {norm(w) for w in data["clock_markers_plain"]}
        lex.clock_with_minutes |= {norm(w) for w in data["clock_markers_with_minutes"]}
        lex.minute_markers |= {norm(w) for w in data["minute_markers"]}
        lex.cues_before |= {norm(w) for w in data["time_cues_before"]}
        lex.cues_after |= {norm(w) for w in data["time_cues_after"]}
        lex.attach_prefixes += [norm(w) for w in data["attach_prefixes"]]
        lex.am += [[norm(w) for w in seq] for seq in data["ampm"]["am"]]
        lex.pm += [[norm(w) for w in seq] for seq in data["ampm"]["pm"]]
        for entry in data["time_fractions"]:
            lex.time_fractions.append({**entry, "words": [norm(w) for w in entry["words"]]})
        lex.correction_markers += [[norm(w) for w in seq] for seq in data["correction_markers"]]
        for cid, phrases in data.get("concepts", {}).items():
            lex.concepts.setdefault(cid, []).extend([norm(w) for w in ph.split()] for ph in phrases)
        lex.number_suffix_hints += [norm(w) for w in data.get("number_suffix_hints", [])]
        lex.decimal_points |= {norm(w) for w in data.get("decimal_points", [])}
        lex.plus_half += [[norm(w) for w in seq] for seq in data.get("plus_half", [])]
        lex.negators |= {norm(w) for w in data.get("negators", [])}
        lex.clause_breaks |= {norm(w) for w in data.get("clause_breaks", [])}
        lex.cause_fillers |= {norm(w) for w in data.get("cause_fillers", [])}
        lex.temporal_markers |= {norm(w) for w in data.get("temporal_markers", [])}
        _merge_unique(lex.measure_nouns, {norm(k): v for k, v in data.get("measure_nouns", {}).items()}, "measure_nouns", lang)
    lex.unit_phrases = sorted((k.split() for k in lex.units if " " in k), key=len, reverse=True)
    lex.attach_prefixes = sorted(set(lex.attach_prefixes), key=len, reverse=True)
    lex.correction_markers.sort(key=len, reverse=True)
    lex.plus_half.sort(key=len, reverse=True)
    lex.time_fractions.sort(key=lambda e: len(e["words"]), reverse=True)
    return lex
