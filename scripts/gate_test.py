"""Day-1 gate test: send recorded clips through Prisma under several language settings,
compare with what was said, and run the normaliser on each transcript.

  python -m scripts.gate_test                 # every clip in fixtures/audio/ (4 STT calls per clip)
  python -m scripts.gate_test --ids ME1 HE1   # only these
  python -m scripts.gate_test --settings mr-IN indic-auto

Clip names: ME1.m4a, ME1_fan.m4a, ME1_t.m4a all use the ME1 script. If you said something
different from the draft script, add a line "ME1_fan: what I said" to fixtures/audio/NOTES.txt.

Results are cached by file hash + setting in evaluation/results/gate_cache.json so re-running
never spends credits twice. Output: console + evaluation/results/gate_<date>.md.
"""
import argparse
import difflib
import hashlib
import json
import mimetypes
import re
import sys
from datetime import date
from pathlib import Path

from backend.app.adapters.gnani_common import GnaniError
from backend.app.adapters.gnani_stt import transcribe
from backend.app.domain.lexicon import norm
from backend.app.domain.normaliser import analyse

ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "fixtures" / "audio"
MANIFEST = ROOT / "fixtures" / "cases" / "gate_clips.json"
RESULTS_DIR = ROOT / "evaluation" / "results"
CACHE = RESULTS_DIR / "gate_cache.json"
CLIP_EXTS = {".wav", ".m4a", ".mp3", ".ogg", ".flac", ".aac"}
DEFAULT_SETTINGS = ["mr-IN", "hi-IN", "mr-IN,hi-IN,en-IN", "indic-auto"]
ASSETS = ROOT / "fixtures" / "assets.json"
DOMAIN_WORDS = ["pump", "compressor", "motor", "fan", "pressure", "PSI", "temperature", "vibration", "leakage"]


def context_fields() -> dict[str, str]:
    """Prisma v3.0 context: asset IDs as keyterms + a short topic. No secrets, no real data."""
    ids = [a["id"] for a in json.loads(ASSETS.read_text(encoding="utf-8"))["assets"]]
    return {
        "keyterms": json.dumps(ids + DOMAIN_WORDS, ensure_ascii=False),
        "topic": "Industrial maintenance incident report: pumps, compressors, motors and fans, pressure in PSI, temperature",
    }


# name -> (format, send context?)
VARIANTS = {
    "verbatim": ("verbatim", False),
    "codemix": ("codemix", False),
    "keyterms": ("verbatim", True),
    "codemix+keyterms": ("codemix", True),
}


def load_notes() -> dict[str, str]:
    notes = {}
    path = AUDIO_DIR / "NOTES.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith("#"):
                key, text = line.split(":", 1)
                notes[key.strip()] = text.strip()
    return notes


def similarity(said: str, heard: str) -> float:
    """Rough character-level match after dropping punctuation/case. Not an error rate."""
    clean = lambda s: re.sub(r"[\s\W_]+", " ", norm(s)).strip()
    return difflib.SequenceMatcher(None, clean(said), clean(heard)).ratio()


def check(expect: dict, transcript: str) -> list[tuple[str, bool, str]]:
    """Run the normaliser on the transcript and compare with `expect`."""
    a = analyse(transcript)
    out = []
    if "corrections" in expect:
        got = sorted((c.old.number.value, c.new.number.value) for c in a.corrections)
        want = sorted(tuple(x) for x in expect["corrections"])
        out.append(("correction", got == want, f"got {got}"))
        if "correction_unit" in expect and a.corrections:
            unit = a.corrections[0].new.unit
            got_unit = unit.canonical if unit else None
            out.append(("correction unit", got_unit == expect["correction_unit"], f"got {got_unit}"))
    if "time" in expect:
        want = expect["time"]
        t = a.times[0] if a.times else None
        ok = bool(t) and (t.hour_spoken, t.minute) == (want["hour"], want["minute"]) \
            and (t.status == "resolved") == want["resolved"]
        out.append(("time", ok, f"got {(t.hour_spoken, t.minute, t.status) if t else None}"))
    if "quantity" in expect:
        want = expect["quantity"]
        match = [q for q in a.quantities if q.number.value == want["value"]]
        unit = (match[0].unit.canonical if match and match[0].unit else None) if match else "-"
        out.append(("quantity", bool(match) and unit == want["unit"], f"got {[(q.number.value, q.unit and q.unit.canonical) for q in a.quantities]}"))
    return out


def stt_cached(cache: dict, path: Path, setting: str, variant: str = "verbatim") -> dict:
    audio = path.read_bytes()
    key = f"{hashlib.sha256(audio).hexdigest()[:16]}|{setting}"
    if variant != "verbatim":
        key += f"|{variant}"  # plain verbatim keeps the original key so earlier cache entries stay valid
    if key not in cache:
        ctype = mimetypes.guess_type(path.name)[0] or "audio/wav"
        fmt, with_context = VARIANTS[variant]
        try:
            r = transcribe(audio, path.name, setting, content_type=ctype, fmt=fmt,
                           context=context_fields() if with_context else None)
            cache[key] = {"ok": True, "transcript": r.transcript, "detected": r.detected_language_code,
                          "model": r.model, "latency": r.end_to_end_latency, "date": str(date.today())}
        except GnaniError as e:
            return {"ok": False, "error": str(e)}  # errors are not cached
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache[key]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--settings", nargs="*", default=DEFAULT_SETTINGS)
    ap.add_argument("--variants", nargs="*", default=["verbatim"], choices=list(VARIANTS))
    ap.add_argument("--simulated", action="store_true", help="use fixtures/audio/simulated/ (synthetic noise) instead of the recordings")
    ap.add_argument("--tag", default="", help="suffix for the report file name")
    args = ap.parse_args()

    clips = json.loads(MANIFEST.read_text(encoding="utf-8"))["clips"]
    notes = load_notes()
    src_dir = AUDIO_DIR / "simulated" if args.simulated else AUDIO_DIR
    files = [p for p in sorted(src_dir.glob("*")) if p.suffix.lower() in CLIP_EXTS]
    files = [p for p in files if p.stem.split("_")[0].upper() in clips]
    if args.ids:
        files = [p for p in files if p.stem.split("_")[0].upper() in {i.upper() for i in args.ids}]
    if not files:
        print(f"No matching clips in {AUDIO_DIR}. Name them like ME1.m4a / HE1.wav.")
        return 1

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    lines = [f"# Gate test {date.today()}", "",
             "Clips through Prisma (files with _sim- are synthetic-noise variants of the human recordings). 'sim' = rough text similarity to what was said (1.00 = identical), not WER.", ""]
    configs = [(v, s) for v in args.variants for s in args.settings]
    label = lambda v, s: s if args.variants == ["verbatim"] else f"{v} / {s}"
    totals: dict[str, list[int]] = {label(v, s): [0, 0] for v, s in configs}

    for path in files:
        cid = path.stem.split("_")[0].upper()
        said = notes.get(path.stem) or notes.get(cid) or clips[cid]["script"]
        sim_tag = "  **SIMULATED NOISE (synthetic, not a real phone/factory recording)**" if "_sim-" in path.stem else ""
        lines += [f"## {path.name}  ({clips[cid]['mix']}){sim_tag}", f"said: {said}", ""]
        lines += ["| setting | detected | sim | transcript | checks |", "|---|---|---|---|---|"]
        for variant, setting in configs:
            name = label(variant, setting)
            res = stt_cached(cache, path, setting, variant)
            if not res["ok"]:
                lines.append(f"| {name} | - | - | ERROR {res['error']} | - |")
                continue
            checks = check(clips[cid]["expect"], res["transcript"])
            for _, ok, _ in checks:
                totals[name][1] += 1
                totals[name][0] += ok
            shown = "; ".join(f"{'PASS' if ok else 'FAIL'} {name} ({detail})" for name, ok, detail in checks) or "-"
            sim = similarity(said, res["transcript"])
            lines.append(f"| {name} | {res['detected']} | {sim:.2f} | {res['transcript']} | {shown} |")
        lines.append("")

    lines += ["## Normaliser checks passed per setting", "", "| config | passed / checked |", "|---|---|"]
    lines += [f"| {s} | {p} / {n} |" for s, (p, n) in totals.items()]
    lines += ["", f"Clips: {len(files)}. Model: prisma-v3.0. Variants: " + ", ".join(args.variants) + ". Small sample; read transcripts yourself before deciding."]
    report = "\n".join(lines)
    print(report)
    (RESULTS_DIR / f"gate_{date.today()}{args.tag}.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
