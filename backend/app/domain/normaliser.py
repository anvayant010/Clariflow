"""Deterministic Marathi/Hindi/English number, time, unit and correction normaliser.

Nothing here branches on language: all words come from the merged lexicon. Every result keeps
the raw text span so evidence receipts can quote exactly what was said. The normaliser never
invents information: no AM/PM without an explicit AM/PM or day-part word, no unit unless one
was spoken, and "degree" stays ambiguous (°C vs °F) rather than being resolved.

Known limits (see tests): "a.m." with dots only works as the pair "a m"; a corrected time
does NOT inherit AM/PM from the time it replaces; bare number words such as "one" are reported
as numbers, so callers must decide which are relevant; a number spelled in a way the lexicon does
not know is not read (orphan_units() flags a unit that has no readable number before it).
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.domain.lexicon import Lexicon, load_lexicon, norm

# ---------------------------------------------------------------- output models


class NumberMatch(BaseModel):
    value: int | float
    raw: str
    start: int
    end: int
    how: Literal["digits", "words"]


class UnitMatch(BaseModel):
    raw: str
    canonical: str
    kind: str
    ambiguous: bool = False  # e.g. "degree": cannot tell °C from °F
    start: int
    end: int


class Quantity(BaseModel):
    number: NumberMatch
    unit: UnitMatch | None = None  # None means no unit was spoken; never inferred


class TimeMatch(BaseModel):
    raw: str
    start: int
    end: int
    hour_spoken: int  # as stated, after "quarter to"-style shifts (0-23)
    minute: int
    am_pm: Literal["am", "pm"] | None = None
    am_pm_source: Literal["explicit", "daypart"] | None = None
    daypart_raw: str | None = None
    hour24: int | None = None  # None while AM/PM is unresolved
    status: Literal["resolved", "needs_clarification"]
    note: str | None = None

    @property
    def hhmm(self) -> str | None:
        return None if self.hour24 is None else f"{self.hour24:02d}:{self.minute:02d}"


class CorrectionMatch(BaseModel):
    old: Quantity
    new: Quantity
    marker: str
    start: int
    end: int


class TimeCorrection(BaseModel):
    old: TimeMatch
    new: TimeMatch
    marker: str


class LoneCorrection(BaseModel):
    """A correction marker directly before a quantity, with no quantity before the marker:
    the earlier value was probably said but not transcribed."""

    new: Quantity
    marker: str


class Analysis(BaseModel):
    times: list[TimeMatch] = Field(default_factory=list)
    quantities: list[Quantity] = Field(default_factory=list)
    corrections: list[CorrectionMatch] = Field(default_factory=list)
    time_corrections: list[TimeCorrection] = Field(default_factory=list)
    lone_corrections: list[LoneCorrection] = Field(default_factory=list)


# ---------------------------------------------------------------- tokenising

_TOKEN_RE = re.compile(
    r"(?P<id>\b[A-Za-z]{1,3}-\d{1,4}\b|\b[A-Za-z]{1,2}\d{1,4}\b)"
    r"|(?P<clock>\b\d{1,2}:\d{2}\b)"
    r"|(?P<digits>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"|(?P<sym>°[CcFf]?|%)"
    r"|(?P<word>[A-Za-zऀ-ॣ॰-ॿ‌‍'’]+)"
)
_WS_GAP = re.compile(r"[\s\-]*")
_PUNCT_GAP = re.compile(r"[\s.,…;:!?\-।]*")
_SENTENCE_END = re.compile(r"[.!?।]")
# words that legitimately sit before a unit without being an unread number
_FUNCTION_WORDS = frozenset(
    "in of the an is was are at per for to and or on with by about around approx approximately from than "
    "above below over under into reading level value unit units measured showing shows high low "
    "मध्ये साठी चा ची चे का की के में से को ने है हैं आहे होता था थी हो पर".split())


@dataclass
class Item:
    kind: str  # num | word | clock | id
    start: int
    end: int
    norm: str
    value: int | float | None = None
    how: str = ""


@dataclass
class _NS:
    """Number-word accumulation state."""

    total: int = 0
    group: int = 0
    last_big: int | None = None
    tens_last: bool = False
    count: int = 0


def _room(cur: int, tens_last: bool) -> int:
    """Exclusive upper bound for a number that may be appended to `cur`."""
    if cur == 0:
        return 0
    if cur % 1000 == 0:
        return 1000
    if cur % 100 == 0:
        return 100
    return 10 if tens_last else 0


def _extend(ns: _NS, word: str, lex: Lexicon) -> _NS | None:
    cur = ns.total + ns.group
    if word in lex.multipliers:
        m = lex.multipliers[word]
        if m == 100:
            if ns.count == 0:
                g = 100
            elif 1 <= ns.group <= 99:
                g = ns.group * 100
            elif ns.group == 0 and _room(cur, ns.tens_last) > 100:
                g = 100
            else:
                return None
            return _NS(ns.total, g, ns.last_big, False, ns.count + 1)
        if ns.last_big is not None and m >= ns.last_big:
            return None
        if ns.count == 0:
            g = 1
        elif ns.group > 0:
            g = ns.group
        else:
            return None
        return _NS(ns.total + g * m, 0, m, False, ns.count + 1)

    n = lex.numbers[word]
    is_tens = word in lex.tens_compound_words
    if ns.count == 0:
        return _NS(0, n, None, is_tens, 1)
    if n == 0 or n >= _room(cur, ns.tens_last):
        return None
    return _NS(ns.total, ns.group + n, ns.last_big, is_tens, ns.count + 1)


def _is_number_word(word: str, lex: Lexicon) -> bool:
    return word in lex.numbers or word in lex.multipliers


# ---------------------------------------------------------------- analyser


class Analyser:
    def __init__(self, text: str, lex: Lexicon):
        self.text = text
        self.lex = lex
        self.items = self._group_numbers(self._tokens())
        self.items = self._merge_decimals(self.items)
        self.used: set[int] = set()
        self.time_corrections: list[TimeCorrection] = []

    # ---- tokens and number grouping

    def _tokens(self) -> list[Item]:
        toks: list[Item] = []
        for m in _TOKEN_RE.finditer(self.text):
            kind, s, e = m.lastgroup, m.start(), m.end()
            raw = m.group()
            if kind == "digits":
                value = float(raw.replace(",", "")) if "." in raw else int(raw.replace(",", ""))
                toks.append(Item("num", s, e, "", value, "digits"))
            elif kind == "clock":
                toks.append(Item("clock", s, e, raw))  # int() also reads Devanagari digits
            elif kind == "id":
                toks.append(Item("id", s, e, norm(raw)))
            else:  # word or sym
                split = self._split_attached(s, e)
                if split:
                    toks.append(Item("word", s, s + split, norm(raw[:split])))
                    toks.append(Item("word", s + split, e, norm(raw[split:])))
                else:
                    toks.append(Item("word", s, e, norm(raw)))
        return toks

    def _split_attached(self, s: int, e: int) -> int | None:
        """'साडेदहा' -> 'साडे' + 'दहा'. Returns split offset within the word, or None."""
        word = self.text[s:e]
        nw = norm(word)
        if _is_number_word(nw, self.lex):
            return None
        for prefix in self.lex.attach_prefixes:
            if nw.startswith(prefix) and nw[len(prefix):] in self.lex.numbers:
                for k in range(1, len(word)):
                    if norm(word[:k]) == prefix:
                        return k
        return None

    def _gap_ok(self, a: Item, b: Item, pattern: re.Pattern = _WS_GAP) -> bool:
        return bool(pattern.fullmatch(self.text[a.end:b.start]))

    def _group_numbers(self, toks: list[Item]) -> list[Item]:
        out: list[Item] = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t.kind == "word" and _is_number_word(t.norm, self.lex):
                ns = _extend(_NS(), t.norm, self.lex)
                j = i + 1
                while (
                    j < len(toks)
                    and toks[j].kind == "word"
                    and _is_number_word(toks[j].norm, self.lex)
                    and self._gap_ok(toks[j - 1], toks[j])
                ):
                    nxt = _extend(ns, toks[j].norm, self.lex)
                    if nxt is None:
                        break
                    ns, j = nxt, j + 1
                out.append(Item("num", t.start, toks[j - 1].end, "", ns.total + ns.group, "words"))
                i = j
            else:
                out.append(t)
                i += 1
        return out

    def _merge_decimals(self, items: list[Item]) -> list[Item]:
        """Spoken decimals become one number item: 'साडे तीन' 3.5, 'डेढ' 1.5, 'पावणे चार' 3.75,
        'two point five' 2.5, 'three and a half' 3.5. A fraction word followed by a clock marker
        ('साडे दहा वाजता') is a time and is left alone for the time finder."""
        lex = self.lex
        single = {e["words"][0]: e for e in lex.time_fractions if len(e["words"]) == 1}
        clock = lex.clock_plain | lex.clock_with_minutes
        out: list[Item] = []
        i = 0
        while i < len(items):
            it = items[i]
            e = single.get(it.norm) if it.kind == "word" else None
            if e:
                j, hour = i + 1, None
                nxt = items[j] if j < len(items) else None
                mult = 1
                big = (nxt is not None and nxt.kind == "num" and isinstance(nxt.value, int) and nxt.value >= 100
                       and nxt.value % 100 == 0 and self._gap_ok(it, nxt))
                if big and "hour" in e and nxt.value in (100, 1000):  # "डेढ़ सौ" = 150
                    hour, mult, j = e["hour"], nxt.value, j + 1
                elif big and e["takes_hour"]:  # "साढ़े तीन सौ" = 350
                    mult = 1000 if nxt.value % 1000 == 0 else 100
                    hour, j = nxt.value // mult, j + 1
                    if not 1 <= hour <= 99:
                        hour = None
                elif (e["takes_hour"] and nxt and nxt.kind == "num" and isinstance(nxt.value, int)
                        and 1 <= nxt.value <= 99 and self._gap_ok(it, nxt)):
                    hour, j = nxt.value, j + 1
                elif "hour" in e:
                    hour = e["hour"]
                after = items[j] if j < len(items) else None
                if hour is not None and not (after and after.kind == "word" and after.norm in clock):
                    value = (hour + e["shift"] + e["minute"] / 60) * mult
                    out.append(Item("num", it.start, items[j - 1].end, "", int(value) if value == int(value) else value, "words"))
                    i = j
                    continue
            if it.kind == "num" and isinstance(it.value, int) and i + 1 < len(items):
                nxt = items[i + 1]
                if nxt.kind == "word" and nxt.norm in lex.decimal_points and self._gap_ok(it, nxt):
                    j, frac = i + 2, ""
                    while (j < len(items) and items[j].kind == "num" and isinstance(items[j].value, int)
                           and 0 <= items[j].value <= 9 and self._gap_ok(items[j - 1], items[j])):
                        frac += str(items[j].value)
                        j += 1
                    if frac:
                        out.append(Item("num", it.start, items[j - 1].end, "", float(f"{it.value}.{frac}"), "words"))
                        i = j
                        continue
                n = next((len(seq) for seq in lex.plus_half
                          if self._seq_at_in(items, i + 1, seq) and self._gap_ok(it, items[i + 1])), 0)
                if n:
                    out.append(Item("num", it.start, items[i + n].end, "", it.value + 0.5, "words"))
                    i += n + 1
                    continue
            out.append(it)
            i += 1
        return out

    def _seq_at_in(self, items: list[Item], idx: int, seq: list[str]) -> bool:
        if idx + len(seq) > len(items):
            return False
        for k, w in enumerate(seq):
            it = items[idx + k]
            if it.kind != "word" or it.norm != w or (k and not self._gap_ok(items[idx + k - 1], it)):
                return False
        return True

    # ---- helpers

    def _word_in(self, idx: int, words: set[str]) -> bool:
        return 0 <= idx < len(self.items) and self.items[idx].kind == "word" and self.items[idx].norm in words

    def _int_num(self, idx: int, lo: int, hi: int) -> int | None:
        if 0 <= idx < len(self.items):
            it = self.items[idx]
            if it.kind == "num" and isinstance(it.value, int) and lo <= it.value <= hi:
                return it.value
        return None

    def _seq_at(self, idx: int, seq: list[str], pattern: re.Pattern) -> int:
        """Number of items matched if words `seq` start at idx, else 0."""
        items = self.items
        if idx + len(seq) > len(items):
            return 0
        for k, w in enumerate(seq):
            it = items[idx + k]
            if it.kind != "word" or it.norm != w:
                return 0
            if k and not self._gap_ok(items[idx + k - 1], it, pattern):
                return 0
        return len(seq)

    def _ampm_at(self, idx: int) -> tuple[str, int] | None:
        if idx >= len(self.items):
            return None
        for label, seqs in (("am", self.lex.am), ("pm", self.lex.pm)):
            for seq in seqs:
                n = self._seq_at(idx, seq, re.compile(r"[\s.]*"))
                if n and self._gap_ok(self.items[idx - 1], self.items[idx], re.compile(r"[\s.]*")):
                    return label, n
        return None

    # ---- times

    def _time_at(self, i: int, relaxed: bool = False):
        """Return (hour, minute, last_item_index) for a time expression starting at i.
        relaxed: right after a time + correction marker, a bare 'ten forty' is accepted without a cue."""
        items, lex = self.items, self.lex
        n = len(items)
        it = items[i]

        if it.kind == "clock":
            h, m = (int(x) for x in it.norm.split(":"))
            if h <= 23 and m <= 59:
                return h, m, i
            return None

        if it.kind == "word":
            for e in lex.time_fractions:
                k = len(e["words"])
                if not self._seq_at(i, e["words"], _WS_GAP):
                    continue
                j = i + k
                hour = self._int_num(j, 1, 12) if e["takes_hour"] else None
                if hour is not None and self._gap_ok(items[j - 1], items[j]):
                    last = j
                elif "hour" in e:
                    hour, last = e["hour"], j - 1
                else:
                    continue
                if self._word_in(last + 1, lex.clock_plain):
                    last += 1
                elif e["requires_clock_marker"]:
                    continue
                hour += e["shift"]
                if hour <= 0:
                    hour += 12
                return hour, e["minute"], last
            return None

        if it.kind == "num" and isinstance(it.value, int):
            # number + clock marker: "दस बजे", "दहा वाजता", "दस बजकर तीस मिनट"
            if 0 <= it.value <= 23 and i + 1 < n and self._gap_ok(it, items[i + 1]):
                nxt = items[i + 1]
                if nxt.kind == "word" and nxt.norm in lex.clock_plain:
                    return it.value, 0, i + 1
                if nxt.kind == "word" and nxt.norm in lex.clock_with_minutes:
                    last, minute = i + 1, 0
                    mv = self._int_num(i + 2, 0, 59)
                    if mv is not None and self._gap_ok(nxt, items[i + 2]):
                        minute, last = mv, i + 2
                        if self._word_in(last + 1, lex.minute_markers):
                            last += 1
                    return it.value, minute, last
            # bare "ten thirty": only with a cue, so "pressure fifteen fifty" is not a time
            h, m = self._int_num(i, 1, 23), self._int_num(i + 1, 1, 59)
            if h is not None and m is not None and self._gap_ok(items[i], items[i + 1]):
                cue_before = i > 0 and self._word_in(i - 1, lex.cues_before | set(lex.dayparts))
                cue_after = self._word_in(i + 2, lex.cues_after | set(lex.dayparts)) or bool(self._ampm_at(i + 2))
                if cue_before or cue_after or relaxed:
                    return h, m, i + 1
            # a lone hour ("3 pm", "at 3 in the afternoon"): a time only with an explicit AM/PM right after it, or with a
            # cue word before it AND a part of the day nearby. "pressure 3" or "stopped 3 times" are not times.
            hour = self._int_num(i, 1, 12)
            if (hour is not None and not (i > 0 and self._word_in(i - 1, set(lex.measure_nouns)))
                    and not (i + 1 < n and self._unit_at(i + 1, number_idx=i))):
                if self._ampm_at(i + 1):
                    return hour, 0, i
                if i > 0 and self._word_in(i - 1, lex.cues_before) and self._daypart(i, i):
                    return hour, 0, i
        return None

    def _daypart(self, start_i: int, last: int) -> tuple[str, str] | None:
        """Nearest day-part word within 3 items, not across a sentence end. Returns (kind, raw)."""
        items = self.items
        first, final = items[start_i], items[last]
        best = None
        for d in (1, 2, 3):  # before wins ties
            idx = start_i - d
            if idx >= 0 and self._word_in(idx, set(self.lex.dayparts)):
                if not _SENTENCE_END.search(self.text[items[idx].end:first.start]):
                    best = (d, idx)
                    break
            idx = last + d
            if idx < len(items) and self._word_in(idx, set(self.lex.dayparts)):
                follows_new_time = idx + 1 < len(items) and items[idx + 1].kind in ("num", "clock")
                if not follows_new_time and not _SENTENCE_END.search(self.text[final.end:items[idx].start]):
                    best = (d, idx)
                    break
        if not best:
            return None
        it = items[best[1]]
        return self.lex.dayparts[it.norm], self.text[it.start:it.end]

    def _build_time(self, start_i: int, last: int, hour: int, minute: int) -> tuple[TimeMatch, int]:
        items = self.items
        am_pm, source, daypart_raw, note = None, None, None, None

        explicit = self._ampm_at(last + 1)
        if explicit:
            am_pm, count = explicit
            source, last = "explicit", last + count
        else:
            dp = self._daypart(start_i, last)
            if dp:
                kind, daypart_raw = dp
                if hour <= 12:
                    am_pm = _daypart_to_ampm(kind, hour)
                    source = "daypart" if am_pm else None

        hour24: int | None
        if hour == 0 or hour >= 13:
            hour24 = hour
            if am_pm and hour >= 13:
                note = "24-hour time with AM/PM word; AM/PM ignored"
                am_pm, source = None, None
        elif am_pm:
            hour24 = hour % 12 + (12 if am_pm == "pm" else 0)
        else:
            hour24 = None

        start, end = items[start_i].start, items[last].end
        tm = TimeMatch(
            raw=self.text[start:end], start=start, end=end, hour_spoken=hour, minute=minute,
            am_pm=am_pm, am_pm_source=source, daypart_raw=daypart_raw, hour24=hour24,
            status="resolved" if hour24 is not None else "needs_clarification", note=note,
        )
        return tm, last

    def _find_times(self) -> list[TimeMatch]:
        times, i = [], 0
        while i < len(self.items):
            found = self._time_at(i)
            if not found:
                i += 1
                continue
            hour, minute, end_i = found
            tm, last = self._build_time(i, end_i, hour, minute)
            times.append(tm)
            self.used.update(range(i, last + 1))
            # "ten thirty, no, ten forty": a marker followed directly by another time replaces it
            while True:
                j, markers = last + 1, []
                while j < len(self.items) and (n := self._marker_at(j)):
                    markers.append(self.text[self.items[j].start:self.items[j + n - 1].end])
                    j += n
                nxt = self._time_at(j, relaxed=True) if markers and j < len(self.items) else None
                if not nxt:
                    break
                tm2, last2 = self._build_time(j, nxt[2], nxt[0], nxt[1])
                self.time_corrections.append(TimeCorrection(old=tm, new=tm2, marker=" ".join(markers)))
                times.append(tm2)
                self.used.update(range(j, last2 + 1))
                tm, last = tm2, last2
            i = last + 1
        return times

    # ---- quantities and corrections

    def _number(self, it: Item) -> NumberMatch:
        return NumberMatch(value=it.value, raw=self.text[it.start:it.end], start=it.start, end=it.end, how=it.how)

    def _find_quantities(self) -> dict[int, tuple[Quantity, int]]:
        """idx of number item -> (Quantity, idx of its last item)."""
        found: dict[int, tuple[Quantity, int]] = {}
        for idx, it in enumerate(self.items):
            if it.kind != "num" or idx in self.used:
                continue
            unit, last = None, idx
            nxt = idx + 1
            hit = self._unit_at(nxt, number_idx=idx) if nxt < len(self.items) and self._gap_ok(it, self.items[nxt]) else None
            if hit:
                spec, count = hit
                u = Item("word", self.items[nxt].start, self.items[nxt + count - 1].end, "")
                last = nxt + count - 1
                # "डिग्री सेल्सियस" / "degrees celsius": the specific word resolves the ambiguous one
                follow = self._unit_at(last + 1, number_idx=idx) if last + 1 < len(self.items) else None
                if (spec["ambiguous"] and follow and not follow[0]["ambiguous"] and follow[0]["kind"] == spec["kind"]
                        and self._gap_ok(self.items[last], self.items[last + 1])):
                    spec = follow[0]
                    last += follow[1]
                    u = Item("word", u.start, self.items[last].end, "")
                unit = UnitMatch(raw=self.text[u.start:u.end], canonical=spec["canonical"], kind=spec["kind"],
                                 ambiguous=spec["ambiguous"], start=u.start, end=u.end)
            found[idx] = (Quantity(number=self._number(it), unit=unit), last)
        return found

    def _noun_before(self, idx: int, kind: str) -> bool:
        """A measure noun of this kind ("प्रेशर", "pressure") within 3 items before item idx, in the same sentence."""
        for k in range(1, 4):
            if idx - k < 0 or self.sentence_break(self.items[idx - k], self.items[idx]):
                return False
            it = self.items[idx - k]
            if it.kind == "word" and self.lex.measure_nouns.get(it.norm) == kind:
                return True
        return False

    def _unit_at(self, idx: int, bare: bool = False, number_idx: int | None = None) -> tuple[dict, int] | None:
        """Unit spec and number of items it spans (multi-word phrases first, e.g. 'पी एस आय').
        A unit marked needs_noun ("बार": also "times") is accepted only after a measure noun of its kind, unless
        `bare` (the unit is the whole answer to a unit question)."""
        hit = None
        for phrase in self.lex.unit_phrases:
            if self._seq_at(idx, phrase, _WS_GAP):
                hit = self.lex.units[" ".join(phrase)], len(phrase)
                break
        if hit is None and idx < len(self.items) and self.items[idx].kind == "word" and self.items[idx].norm in self.lex.units:
            hit = self.lex.units[self.items[idx].norm], 1
        if hit and hit[0].get("needs_noun") and not bare:
            if not self._noun_before(idx if number_idx is None else number_idx, hit[0]["kind"]):
                return None
        return hit

    def _marker_at(self, idx: int) -> int:
        for seq in self.lex.correction_markers:
            n = self._seq_at(idx, seq, _PUNCT_GAP)
            if n:
                return n
        return 0

    def _find_corrections(self, quantities: dict[int, tuple[Quantity, int]]) -> list[CorrectionMatch]:
        out = []
        for idx, (q1, last) in quantities.items():
            j, markers = last + 1, []
            while j < len(self.items) and (n := self._marker_at(j)):
                markers.append(self.text[self.items[j].start:self.items[j + n - 1].end])
                j += n
            if markers and j in quantities:
                q2 = quantities[j][0]
                end = q2.unit.end if q2.unit else q2.number.end
                out.append(CorrectionMatch(old=q1, new=q2, marker=" ".join(markers),
                                           start=q1.number.start, end=end))
        return out

    def unread_prefix(self, num_start: int) -> Item | None:
        """A word glued before a number that looks like part of it but is not in the lexicon
        (Marathi '…शे'): the number would otherwise be silently read too small."""
        idx = next((i for i, it in enumerate(self.items) if it.start == num_start), None)
        if not idx:
            return None
        prev, here = self.items[idx - 1], self.items[idx]
        if (prev.kind == "word" and len(prev.norm) >= 3 and self._gap_ok(prev, here)
                and not self.sentence_break(prev, here)
                and prev.norm not in self.lex.numbers and prev.norm not in self.lex.multipliers
                and any(prev.norm.endswith(h) for h in self.lex.number_suffix_hints)):
            return prev
        return None

    def _find_lone_corrections(self, quantities: dict[int, tuple[Quantity, int]],
                               corrections: list[CorrectionMatch]) -> list[LoneCorrection]:
        paired = {c.new.number.start for c in corrections}
        out = []
        for idx, (q, _) in quantities.items():
            if q.number.start in paired:
                continue
            for n in (3, 2, 1):
                s0 = idx - n
                if s0 < 1 or self._marker_at(s0) != n:
                    continue
                before, marker, here = self.items[s0 - 1], self.items[s0], self.items[idx]
                if (before.kind in ("num", "clock") or self.sentence_break(before, marker)
                        or not _PUNCT_GAP.fullmatch(self.text[self.items[idx - 1].end:here.start])):
                    continue
                out.append(LoneCorrection(new=q, marker=self.text[marker.start:self.items[idx - 1].end]))
                break
        return out

    def orphan_units(self) -> list[tuple[int, int, int, dict]]:
        """(previous item idx, unit item idx, unit item count, unit spec) where a unit word follows an
        unreadable word instead of a number: 'पंचाऐंशी डिग्री' when the lexicon lacks that spelling.
        Never guesses the number; callers must ask."""
        out = []
        for i, it in enumerate(self.items):
            hit = self._unit_at(i, number_idx=i - 1) if it.kind == "word" else None
            if not hit or i == 0 or i in self.used:
                continue
            prev = self.items[i - 1]
            if (prev.kind != "word" or (i - 1) in self.used or not self._gap_ok(prev, it)
                    or self.sentence_break(prev, it) or len(prev.norm) < 3 or prev.norm in _FUNCTION_WORDS
                    or prev.norm in self.lex.measure_nouns or prev.norm in self.lex.units
                    or prev.norm in self.lex.negators or any(prev.norm == m[0] for m in self.lex.correction_markers)):
                continue
            out.append((i - 1, i, hit[1], hit[0]))
        return out

    def phrase_hits(self, concept_ids: list[str] | None = None) -> list[tuple[str, int, int]]:
        """(concept id, first item idx, last item idx) for lexicon phrases; longest match wins per start."""
        hits, taken = [], set()
        phrases = [
            (cid, ph) for cid, lst in self.lex.concepts.items() if concept_ids is None or cid in concept_ids
            for ph in lst
        ]
        phrases.sort(key=lambda x: len(x[1]), reverse=True)
        for i in range(len(self.items)):
            for cid, ph in phrases:
                n = self._seq_at(i, ph, _WS_GAP)
                if n and not taken & set(range(i, i + n)):
                    hits.append((cid, i, i + n - 1))
                    taken |= set(range(i, i + n))
                    break
        return hits

    def sentence_break(self, a: Item, b: Item) -> bool:
        """True if a sentence end lies between item a and item b (a before b)."""
        return bool(_SENTENCE_END.search(self.text[a.end:b.start]))

    def clause_break(self, a: Item, b: Item) -> bool:
        """True if a new clause starts between item a and item b (a before b): a sentence end, a comma/semicolon/colon,
        or a clause word ("and", "but", ...). "not working, smoke is coming": the "not" must not reach the smoke."""
        gap = self.text[a.end:b.start]
        if _SENTENCE_END.search(gap) or re.search(r"[,;:\u060c]", gap):
            return True
        return any(it.kind == "word" and it.norm in self.lex.clause_breaks
                   for it in self.items if it.start >= a.end and it.end <= b.start)

    def run(self) -> Analysis:
        times = self._find_times()
        quantities = self._find_quantities()
        corrections = self._find_corrections(quantities)
        return Analysis(
            times=times,
            quantities=[q for q, _ in quantities.values()],
            corrections=corrections,
            time_corrections=self.time_corrections,
            lone_corrections=self._find_lone_corrections(quantities, corrections),
        )


def _daypart_to_ampm(kind: str, hour: int) -> Literal["am", "pm"] | None:
    if kind == "morning":
        return None if hour == 12 else "am"
    if kind == "afternoon":
        return "pm" if hour == 12 or 1 <= hour <= 6 else None
    if kind == "evening":
        return "pm" if 4 <= hour <= 11 else None
    if kind == "night":
        if 6 <= hour <= 11:
            return "pm"
        if hour == 12 or 1 <= hour <= 5:
            return "am"
    return None


@lru_cache(maxsize=1)
def default_lexicon() -> Lexicon:
    return load_lexicon()


def analyse(text: str, lexicon: Lexicon | None = None) -> Analysis:
    return Analyser(text, lexicon or default_lexicon()).run()


def parse_number(text: str, lexicon: Lexicon | None = None) -> int | float | None:
    """Value if `text` is exactly one number (digits or words), else None."""
    a = Analyser(text.strip(), lexicon or default_lexicon())
    if len(a.items) == 1 and a.items[0].kind == "num":
        return a.items[0].value
    return None
