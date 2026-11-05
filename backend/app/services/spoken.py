"""Text -> text for the voice: spell numbers, asset IDs, times and units as words in the target
language before sending to Timbre (the Gnani docs advise writing numbers as spoken words).

Pure and deterministic. Number words come from the same lexicon files the normaliser reads, so the
spoken form and the recognised form cannot drift apart. Wording is DRAFT until a native speaker
has listened to it.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

LEX_DIR = Path(__file__).resolve().parents[1] / "lexicon"
_ID = re.compile(r"\b([A-Z])-(\d{1,3})\b")
_CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})(?:\s?(AM|PM)\b)?")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_UNIT = re.compile(r"°[CF]|\b(?:PSI|RPM|kPa|MPa|Hz|kW|bar)\b|%")


@lru_cache(maxsize=None)
def _inverse_numbers(lang: str) -> dict[int, str]:
    data = json.loads((LEX_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    inv: dict[int, str] = {}
    for word, value in data["numbers"].items():
        inv.setdefault(value, word)
    return inv


@lru_cache(maxsize=1)
def _readback_data() -> dict:
    return json.loads((LEX_DIR / "readback.json").read_text(encoding="utf-8"))


def _sub_hundred_en(n: int) -> str:
    inv = _inverse_numbers("en")
    if n in inv:
        return inv[n]
    return f"{inv[n // 10 * 10]} {inv[n % 10]}"


def number_words(n: int, lang: str) -> str | None:
    """Spoken form of 0 <= n < 100000, or None if out of range (callers then keep the digits)."""
    if not 0 <= n < 100000:
        return None
    words = _readback_data()["spoken_words"][lang]
    inv = _inverse_numbers(lang)
    if n < 100:
        return _sub_hundred_en(n) if lang == "en" else inv[n]
    if n >= 1000:
        thousands, rest = divmod(n, 1000)
        head = f"{number_words(thousands, lang)} {words['thousand']}"
        return head if rest == 0 else f"{head} {number_words(rest, lang)}"
    hundreds, rest = divmod(n, 100)
    if lang == "mr":  # एकशे, दोनशे … are single words in the lexicon
        head = inv[hundreds * 100]
    else:
        head = f"{number_words(hundreds, lang)} {words['hundred']}"
    return head if rest == 0 else f"{head} {number_words(rest, lang)}"


def _digits_spelled(digits: str, lang: str) -> str:
    return " ".join(number_words(int(d), lang) for d in digits)


def _decimal(text: str, lang: str) -> str:
    whole, _, frac = text.partition(".")
    w = number_words(int(whole), lang)
    if w is None:
        return text
    if not frac:
        return w
    return f"{w} {_readback_data()['spoken_words'][lang]['point']} {_digits_spelled(frac, lang)}"


def _clock(h: int, m: int, lang: str, ampm: str | None = None) -> str:
    words = _readback_data()["spoken_words"][lang]
    hour = number_words(h, lang)
    if m == 0:
        spoken = f"{hour} {words['oclock']}"
    else:
        minute = number_words(m, lang)
        if lang == "en":
            spoken = f"{hour} {minute if m >= 10 else 'oh ' + minute}"
        else:
            spoken = f"{hour} {words['hour_marker']} {minute} {words['minutes']}"
    return f"{spoken} {words[ampm.lower()]}" if ampm else spoken  # "P M" / "पी एम": said as letters


def to_spoken(text: str, lang: str) -> str:
    """lang: 'mr' | 'hi' | 'en'."""
    data = _readback_data()

    def letter(c: str) -> str:
        return c if lang == "en" else data["letters"]["devanagari"].get(c, c)

    def asset_id(m: re.Match) -> str:
        digits = m.group(2)
        num = _digits_spelled(digits, lang) if digits.startswith("0") else number_words(int(digits), lang)
        return f"{letter(m.group(1))} {num}"

    text = _ID.sub(asset_id, text)
    text = _CLOCK.sub(lambda m: _clock(int(m.group(1)), int(m.group(2)), lang, m.group(3)), text)
    text = _NUM.sub(lambda m: _decimal(m.group(0), lang), text)
    units = data["spoken_units"][lang]
    return _UNIT.sub(lambda m: units.get(m.group(0), m.group(0)), text)
