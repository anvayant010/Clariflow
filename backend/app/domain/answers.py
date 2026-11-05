"""Interpret a spoken/typed answer to the CURRENT question as one allowed choice.

Returns (choice, evidence) or None when the answer cannot be understood; callers then repeat the
question instead of guessing. The answer text is data, like any transcript.
"""
import re

from backend.app.domain.extractor import extract, find_asset_mentions, urgency_hits
from backend.app.domain.issues import active
from backend.app.domain.lexicon import Lexicon
from backend.app.domain.normaliser import Analyser, _daypart_to_ampm, default_lexicon
from backend.app.domain.schemas import Asset, Draft, EvidenceRef, Issue, IssueType, TranscriptSegment


def _ev(seg: TranscriptSegment, start: int, end: int) -> EvidenceRef:
    return EvidenceRef(segment_id=seg.id, quote=seg.text[start:end], start_char=start, end_char=end)


def interpret_answer(issue: Issue, draft: Draft, seg: TranscriptSegment, catalogue: list[Asset],
                     lexicon: Lexicon | None = None) -> tuple[str, EvidenceRef] | None:
    lex = lexicon or default_lexicon()
    an = Analyser(seg.text, lex)
    hits = an.phrase_hits()
    unknown = next(((a, b) for c, a, b in hits if c == "unknown_phrase"), None)
    t = issue.type

    def unknown_ev():
        return _ev(seg, an.items[unknown[0]].start, an.items[unknown[1]].end)

    if t in (IssueType.AMBIGUOUS_ASSET, IssueType.UNKNOWN_ASSET):
        allowed = set(issue.options) if t == IssueType.AMBIGUOUS_ASSET else {a.id for a in catalogue}
        mentions = find_asset_mentions(an, catalogue)
        ids = set().union(*(m[2] for m in mentions)) & allowed if mentions else set()
        if len(ids) == 1:
            s, e, _ = next(m for m in mentions if m[2] & ids)
            return next(iter(ids)), _ev(seg, s, e)
        if t == IssueType.AMBIGUOUS_ASSET and not ids:
            # "twenty-one" (or "Pump इक्कीस") when the choice is P-12 or P-21: one number that fits exactly ONE of the offered assets
            nums = [it for it in an.items if it.kind == "num" and isinstance(it.value, int)]
            fits = [o for o in issue.options if len(nums) == 1 and nums[0].value in {int(d) for d in re.findall(r"\d+", o)}]
            if len(fits) == 1:
                return fits[0], _ev(seg, nums[0].start, nums[0].end)
        return None

    if t == IssueType.MISSING_URGENCY:
        found = urgency_hits(an, hits, lex, loose=True)
        if len(found) == 1:
            (a, b) = next(iter(found.values()))
            return next(iter(found)), _ev(seg, an.items[a].start, an.items[b].end)
        if not found and unknown:
            return "unknown", unknown_ev()
        return None  # nothing, or two different levels: ask again, never guess

    if t == IssueType.MISSING_VALUE:
        q = next(iter(an.run().quantities), None)
        if q is not None:
            n = q.number.value
            return (str(int(n)) if n == int(n) else str(n)), _ev(seg, q.number.start, q.number.end)
        return ("unknown", unknown_ev()) if unknown else None

    if t in (IssueType.MISSING_UNIT, IssueType.AMBIGUOUS_UNIT):
        cand = next((c for c in draft.candidates if issue.key.endswith(c.id)), None)
        kind = cand.meta.get("kind") if cand else None
        for i in range(len(an.items)):
            hit = an._unit_at(i, bare=True)
            if hit and not hit[0]["ambiguous"] and hit[0]["kind"] == kind:  # "bar" does not answer a temperature question
                if t == IssueType.AMBIGUOUS_UNIT and hit[0]["canonical"] not in issue.options:
                    continue
                return hit[0]["canonical"], _ev(seg, an.items[i].start, an.items[i + hit[1] - 1].end)
        return ("unknown", unknown_ev()) if unknown else None

    if t == IssueType.AMBIGUOUS_TIME:
        tc = next(iter(active(draft, "time")), None)
        hour = tc.meta.get("hour_spoken") if tc else None
        for i in range(len(an.items)):
            explicit = an._ampm_at(i)
            if explicit:
                return explicit[0], _ev(seg, an.items[i].start, an.items[i + explicit[1] - 1].end)
        for it in an.items:
            kind = lex.dayparts.get(it.norm) if it.kind == "word" else None
            if kind and hour is not None:
                ampm = _daypart_to_ampm(kind, hour)
                if ampm:
                    return ampm, _ev(seg, it.start, it.end)
        return ("unknown", unknown_ev()) if unknown else None

    if t == IssueType.CONFLICTING_OBSERVATION:
        if "source_unknown" in issue.options:
            if unknown:
                return "source_unknown", unknown_ev()
            leak = next((c for c in extract(seg, catalogue, lex)
                         if c.field_path == "symptom.leakage" and c.normalised_value == "present"), None)
            return ("leakage_confirmed", leak.evidence[0]) if leak else None
        for c in extract(seg, catalogue, lex):
            option = f"{c.field_path}={c.normalised_value}"
            if option in issue.options and c.evidence:
                return option, c.evidence[0]
    return None
