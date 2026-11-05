"""Deterministic extractor: one transcript segment in, evidence-backed candidates out.

Proposes only. It has no access to storage and cannot change a draft. Every candidate carries
EvidenceRefs whose quote and offsets point into the segment text. It never invents a cause, unit,
AM/PM, date or measurement: anything not said is simply absent.
"""
import re

from backend.app.domain.assets import alias_index
from backend.app.domain.lexicon import Lexicon, norm
from backend.app.domain.normaliser import Analyser, Item, default_lexicon
from backend.app.domain.schemas import (
    Asset, CandidateStatus, EvidenceRef, FieldCandidate, TranscriptSegment,
)

_SEPARATORS = re.compile(r"[\s\-_./]+")
NEGATOR_WINDOW_BEFORE = 3  # items between a symptom and a following negator ("leakage नाही")
NEGATOR_WINDOW_AFTER = 2  # items between a preceding negator and a symptom ("no leakage")


MAX_CAUSE_CHARS = 300


def urgency_hits(an, hits, lex, loose: bool = False) -> dict[str, tuple[int, int]]:
    """level -> (first item, last item) for urgency phrases. `loose` also accepts the short words that only make sense
    as the ANSWER to "how urgent is this?" ("today", "fire"). A level that is negated ("not an emergency") is dropped:
    that does not say which level it IS, so the question is asked instead. Two different levels = no answer."""
    found: dict[str, tuple[int, int]] = {}
    for cid, a, b in hits:
        family, _, level = cid.partition(":")
        if family != "urgency" and not (loose and family == "urgency_answer"):
            continue
        negated = any(an.items[k].kind == "word" and an.items[k].norm in lex.negators and not an.clause_break(an.items[k], an.items[a])
                      for k in range(max(0, a - 2), a))
        if negated and level != "can_wait":
            continue
        found.setdefault(level, (a, b))
    return found


def cause_candidate(seg: TranscriptSegment, an, lex, first: int, sentence_only: bool = False,
                    other_info: set[int] | None = None) -> FieldCandidate | None:
    """The cause as the person said it: items from `first` to the end of the sentence (or of the turn), leading filler
    words dropped, capped in length. The text is the speaker's own words; nothing is added or rephrased.
    `other_info` = items that belong to other fields (numbers, symptoms): a cause ends at the comma before them, so
    "cause belt slipped, pressure 2.5 bar" does not carry the pressure reading inside the cause."""
    items = an.items
    while first < len(items) and items[first].kind == "word" and items[first].norm in lex.cause_fillers:
        first += 1
    if first >= len(items):
        return None
    last = first
    while last + 1 < len(items) and (not sentence_only or not an.sentence_break(items[last], items[last + 1])):
        last += 1
    if other_info:  # end the cause at the comma nearest BEFORE the first word that belongs to another field
        for j in (i for i in range(first, last + 1) if i in other_info):
            cut = next((k for k in range(j - 1, first - 1, -1)
                        if re.search(r"[,;]", seg.text[items[k].end:items[k + 1].start])), None)
            if cut is not None:
                last = cut
                break
    start, end = items[first].start, min(items[last].end, items[first].start + MAX_CAUSE_CHARS)
    value = seg.text[start:end]
    return FieldCandidate(field_path="cause", raw_value=value, normalised_value=value, status=CandidateStatus.PROPOSED,
                          evidence=[_ev(seg, start, end)], meta={"stated": True})


def cause_from_answer(seg: TranscriptSegment, lexicon=None) -> FieldCandidate | None:
    """A turn whose whole purpose is 'the cause': an explicit unknown ("don't know"), or the words themselves."""
    from backend.app.domain.normaliser import Analyser, default_lexicon

    lex = lexicon or default_lexicon()
    an = Analyser(seg.text, lex)
    hits = an.phrase_hits()
    unknown = next(((a, b) for c, a, b in hits if c == "unknown_phrase"), None)
    if unknown:
        start, end = an.items[unknown[0]].start, an.items[unknown[1]].end
        return FieldCandidate(field_path="cause", raw_value=seg.text[start:end], normalised_value=None,
                              status=CandidateStatus.UNKNOWN, evidence=[_ev(seg, start, end)])
    first = 0
    cue = next((b for c, a, b in hits if c == "cause_cue" and a == 0), None)  # "cause: overload"
    if cue is not None:
        first = cue + 1
    return cause_candidate(seg, an, lex, first)


def _ev(seg: TranscriptSegment, start: int, end: int) -> EvidenceRef:
    return EvidenceRef(segment_id=seg.id, quote=seg.text[start:end], start_char=start, end_char=end)


def _item_key(an: Analyser, items: list[Item]) -> str:
    return _SEPARATORS.sub("", norm(an.text[items[0].start:items[-1].end]))


def find_asset_mentions(an: Analyser, catalogue: list[Asset]) -> list[tuple[int, int, set[str]]]:
    """(start_char, end_char, asset ids) for each non-overlapping catalogue mention, longest first."""
    index = alias_index(catalogue)
    cand = [i for i, it in enumerate(an.items) if it.kind in ("word", "id", "num")]
    spans, used = [], set()
    for length in (4, 3, 2, 1):
        for pos in range(len(cand) - length + 1):
            idxs = cand[pos:pos + length]
            if idxs[-1] - idxs[0] != length - 1 or used & set(idxs):
                continue
            if any(not an._gap_ok(an.items[a], an.items[b]) for a, b in zip(idxs, idxs[1:])):
                continue
            ids = index.get(_item_key(an, [an.items[i] for i in idxs]))
            if ids:
                spans.append((an.items[idxs[0]].start, an.items[idxs[-1]].end, set(ids)))
                used |= set(idxs)
    return sorted(spans)


def extract(segment: TranscriptSegment, catalogue: list[Asset], lexicon: Lexicon | None = None) -> list[FieldCandidate]:
    lex = lexicon or default_lexicon()
    text = segment.text
    an = Analyser(text, lex)
    analysis = an.run()
    out: list[FieldCandidate] = []

    # ---- asset
    mentions = find_asset_mentions(an, catalogue)
    asset_spans = [(s, e) for s, e, _ in mentions]
    if mentions:
        ids = sorted(set().union(*(m[2] for m in mentions)))
        evidence = [_ev(segment, s, e) for s, e, _ in mentions]
        raw = " / ".join(ev.quote for ev in evidence)
        if len(ids) == 1:
            out.append(FieldCandidate(field_path="asset", raw_value=raw, normalised_value=ids[0], evidence=evidence))
        else:
            out.append(FieldCandidate(field_path="asset", raw_value=raw, normalised_value=None, evidence=evidence,
                                      status=CandidateStatus.NEEDS_CLARIFICATION, meta={"options": ids}))

    # ---- time (the first stated time; a spoken correction replaces it, the old one is kept as history)
    def time_candidate(t) -> FieldCandidate:
        return FieldCandidate(
            field_path="time", raw_value=t.raw, normalised_value=t.hhmm, evidence=[_ev(segment, t.start, t.end)],
            status=CandidateStatus.PROPOSED if t.hhmm else CandidateStatus.NEEDS_CLARIFICATION,
            meta={"hour_spoken": t.hour_spoken, "minute": t.minute, "am_pm": t.am_pm,
                  "am_pm_source": t.am_pm_source, "daypart": t.daypart_raw},
        )

    if analysis.times:
        chain = [analysis.times[0]]
        while True:
            fix = next((c for c in analysis.time_corrections if c.old.start == chain[-1].start), None)
            if fix is None:
                break
            chain.append(fix.new)
        cands = [time_candidate(t) for t in chain]
        for prev, cur, fix_marker in zip(cands, cands[1:],
                                         [c.marker for c in analysis.time_corrections if c.old.start >= chain[0].start]):
            prev.status = CandidateStatus.SUPERSEDED
            cur.replaces_candidate_id = prev.id
            cur.meta["corrected_from_id"] = prev.id
            cur.meta["correction_marker"] = fix_marker
        out += cands
    time_spans = [(t.start, t.end) for t in analysis.times]

    # ---- measurements (a number counts only with a measurement noun nearby or a unit; never inferred)
    def overlaps(q, spans):
        return any(q.number.start < e and s < q.number.end for s, e in spans)

    def item_index(char_start: int) -> int:
        return next(i for i, it in enumerate(an.items) if it.start == char_start)

    def noun_kind(q) -> str | None:
        i = item_index(q.number.start)
        for k in range(1, 4):
            if i - k < 0 or an.items[i - k].kind == "num" or an.sentence_break(an.items[i - k], an.items[i]):
                break
            kind = lex.measure_nouns.get(an.items[i - k].norm)
            if kind:
                return kind
        return None

    def measurement(q, status, kind, replaces=None):
        end = q.unit.end if q.unit else q.number.end
        # "temperature eighty PSI": the unit does not belong to that kind of reading. Never keep it (that would save a
        # wrong value); keep what was heard and ask for the unit.
        mismatch = bool(q.unit and q.unit.kind != kind)
        unit = None if mismatch else q.unit
        ambiguous = bool(unit and unit.ambiguous)
        extra = {"unit_mismatch": True} if mismatch else {}
        prefix = an.unread_prefix(q.number.start) if status != CandidateStatus.SUPERSEDED else None
        if prefix is not None:  # e.g. an unknown "…शे" hundreds word: do not save a too-small number
            return FieldCandidate(
                field_path=f"measurement.{kind}", raw_value=text[prefix.start:end], normalised_value=None,
                unit=unit.canonical if unit and not unit.ambiguous else None,
                evidence=[_ev(segment, prefix.start, end)], status=CandidateStatus.NEEDS_CLARIFICATION,
                replaces_candidate_id=replaces,
                meta={"kind": kind, "value_missing": True, "unit_ambiguous": ambiguous,
                      "raw_unit": q.unit.raw if q.unit else None, **extra})
        return FieldCandidate(
            field_path=f"measurement.{kind}", raw_value=text[q.number.start:end], normalised_value=q.number.value,
            unit=unit.canonical if unit else None, evidence=[_ev(segment, q.number.start, end)], status=status,
            replaces_candidate_id=replaces,
            meta={"kind": kind, "unit_ambiguous": ambiguous, "raw_unit": q.unit.raw if q.unit else None, **extra},
        )

    lone_starts = {lc.new.number.start for lc in analysis.lone_corrections}
    consumed_q: set[int] = set()
    correction_spans: list[tuple[int, int]] = []
    skip = asset_spans + time_spans
    for c in analysis.corrections:
        kind = (noun_kind(c.old) or noun_kind(c.new) or (c.new.unit and c.new.unit.kind)
                or (c.old.unit and c.old.unit.kind))
        if not kind or overlaps(c.old, skip) or overlaps(c.new, skip):
            continue
        old = measurement(c.old, CandidateStatus.SUPERSEDED, kind)
        new = measurement(c.new, CandidateStatus.PROPOSED, kind, replaces=old.id)
        new.meta["correction_marker"] = c.marker
        new.meta["corrected_from_id"] = old.id
        out += [old, new]
        consumed_q |= {c.old.number.start, c.new.number.start}
        correction_spans.append((c.start, c.end))
    for q in analysis.quantities:
        if q.number.start in consumed_q or overlaps(q, skip):
            continue
        kind = noun_kind(q) or (q.unit.kind if q.unit else None)
        if kind:
            m = measurement(q, CandidateStatus.PROPOSED, kind)
            if q.number.start in lone_starts:  # "… नाही, पन्नास": a correction whose earlier value was not heard
                m.meta["old_value_missing"] = True
            out.append(m)

    # a unit with no readable number before it ("पंचाऐंशी डिग्री"): record that a value is missing, never guess it
    for prev_i, unit_i, count, spec in an.orphan_units():
        s0, e0 = an.items[prev_i].start, an.items[unit_i + count - 1].end
        if any(s0 < b and a < e0 for a, b in skip):
            continue
        out.append(FieldCandidate(
            field_path=f"measurement.{spec['kind']}", raw_value=text[s0:e0], normalised_value=None,
            unit=None if spec["ambiguous"] else spec["canonical"], evidence=[_ev(segment, s0, e0)],
            status=CandidateStatus.NEEDS_CLARIFICATION,
            meta={"kind": spec["kind"], "value_missing": True, "unit_ambiguous": spec["ambiguous"],
                  "raw_unit": text[an.items[unit_i].start:an.items[unit_i + count - 1].end]}))

    # ---- concept phrases: symptoms, actions, cause
    hits = an.phrase_hits()
    unknown = [h for h in hits if h[0] == "unknown_phrase"]
    cues = [h for h in hits if h[0] == "cause_cue"]
    in_unknown = {i for _, a, b in unknown for i in range(a, b + 1)}
    for _, a, b in unknown:  # "कारण ... माहीत नाही" in one sentence = cause explicitly unknown
        cue = next((c for c in cues if c[1] < a and not an.sentence_break(an.items[c[1]], an.items[a])), None)
        if cue:
            start, end = an.items[cue[1]].start, an.items[b].end
            out.append(FieldCandidate(field_path="cause", raw_value=text[start:end], normalised_value=None,
                                      status=CandidateStatus.UNKNOWN, evidence=[_ev(segment, start, end)]))

    used_cues = {c[1] for _, a, b in unknown for c in cues[:] if c[1] < a and not an.sentence_break(an.items[c[1]], an.items[a])}
    other_info = {i for i, it in enumerate(an.items)  # numbers, units and measure words belong to other fields
                  if it.kind == "num" or (it.kind == "word" and (it.norm in lex.units or it.norm in lex.measure_nouns))}
    other_info |= {i for cid, a, b in hits if cid.startswith(("symptom:", "action:")) for i in range(a, b + 1)}
    covered = -1  # end of the last captured cause: a cue INSIDE it ("cause is X due to Y") adds nothing new
    for _, a, b in cues:  # "cause overload", "because the belt slipped": the words after the cue, verbatim
        if a in used_cues or an.items[a].start < covered:
            continue
        stated = cause_candidate(segment, an, lex, b + 1, sentence_only=True, other_info=other_info)
        if stated is not None:
            out.append(stated)
            covered = stated.evidence[0].end_char

    stated = urgency_hits(an, hits, lex)
    if len(stated) == 1:  # exactly one level, in unmistakable words; two different levels are left for the question
        level, (a, b) = next(iter(stated.items()))
        start, end = an.items[a].start, an.items[b].end
        out.append(FieldCandidate(field_path="urgency", raw_value=text[start:end], normalised_value=level,
                                  status=CandidateStatus.PROPOSED, evidence=[_ev(segment, start, end)]))

    symptoms = [h for h in hits if h[0].startswith("symptom:")]
    negated: dict[int, int] = {}  # symptom hit index -> negator item idx
    for ni, it in enumerate(an.items):
        if it.kind != "word" or it.norm not in lex.negators or ni in in_unknown:
            continue
        if any(s <= it.start < e for s, e in correction_spans):
            continue  # "पंधरा… नाही, पन्नास": a correction marker, not a negation
        if any(a <= ni <= b for _, a, b in symptoms):
            continue  # "not working" is itself the stopped symptom: that "not" does not negate anything else
        if any(a <= ni <= b for cid, a, b in hits if cid.startswith("urgency")):
            continue  # "not urgent" / "घाई नाही": that negator belongs to the urgency phrase
        best = None
        for hi, (_, a, b) in enumerate(symptoms):
            if b < ni and ni - b <= NEGATOR_WINDOW_BEFORE and not an.clause_break(an.items[b], it):
                dist = ni - b
            elif a > ni and a - ni <= NEGATOR_WINDOW_AFTER and not an.clause_break(it, an.items[a]):
                dist = a - ni
            else:
                continue
            if best is None or dist < best[0] or (dist == best[0] and b < ni):
                best = (dist, hi)
        if best and best[1] not in negated:
            negated[best[1]] = ni

    cause_spans = [(e.start_char, e.end_char) for c in out if c.field_path == "cause" and c.meta.get("stated")
                   for e in c.evidence]
    seen = set()
    for hi, (cid, a, b) in enumerate(symptoms):
        name = cid.split(":", 1)[1]
        start, end = an.items[a].start, an.items[b].end
        if name not in ("smoke", "fire") and any(s <= start and end <= e for s, e in cause_spans):
            continue
        value = "present"
        if hi in negated:
            n = an.items[negated[hi]]
            start, end, value = min(start, n.start), max(end, n.end), "absent"
        if (name, value) in seen:
            continue
        seen.add((name, value))
        out.append(FieldCandidate(
            field_path=f"symptom.{name}", raw_value=text[start:end], normalised_value=value,
            evidence=[_ev(segment, start, end)], meta={"temporal": _temporal_near(an, lex, a, b)}))

    for cid, a, b in hits:
        if cid.startswith("action:"):
            start, end = an.items[a].start, an.items[b].end
            out.append(FieldCandidate(field_path="immediate_action", raw_value=text[start:end],
                                      normalised_value=cid.split(":", 1)[1], evidence=[_ev(segment, start, end)]))
    return out


def _temporal_near(an: Analyser, lex: Lexicon, a: int, b: int) -> bool:
    """True if a temporal word (पहले/अब/now/then…) sits within 3 items of the phrase, same sentence."""
    for k in list(range(a - 3, a)) + list(range(b + 1, b + 4)):
        if 0 <= k < len(an.items) and an.items[k].kind == "word" and an.items[k].norm in lex.temporal_markers:
            lo, hi = sorted((k, a if k < a else b))
            if not an.sentence_break(an.items[lo], an.items[hi]):
                return True
    return False
