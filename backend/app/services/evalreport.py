"""Turn evaluation results into a versioned JSON document, a Markdown report and an SVG chart."""
from datetime import date
from html import escape

from backend.app.domain.assets import load_catalogue
from backend.app.services import evaluation as ev

STT_NOTE = ("Transcripts are RECORDED Prisma v3.0 output from 2026-11-04 (cache in evaluation/results/gate_cache.json); "
            "this report made no API calls. 'Naive' audio rows use plain verbatim STT; Clariflow rows use "
            "format=codemix + keyterms (decision D12; the keyterms are our own asset IDs).")
CAVEATS = [
    "Truth records were written by Claude, the same author as the extractor, from the scripts the speaker was asked to read; "
    "no second person has checked them against the audio.",
    "Audio set: 9 clips, one speaker (Anvay), quiet room, Marathi/Hindi/English mixes. Not real factory or telephone audio.",
    "The 57 written transcripts were used while fixing the extractor, so they measure regression, not unseen-data accuracy. "
    "The only first-run unseen figure is 15 of 18 (see docs/PROGRESS.md).",
    "The naive baseline is one we wrote (see its definition above); a real summariser or LLM pipeline could do better or worse.",
    "Clariflow's numbers are its draft BEFORE a human answers. It cannot save until questions are resolved and the user confirms.",
    "Counts are checked items against truth, not a probability of correctness, and no confidence interval is claimed.",
]


def build(catalogue=None) -> dict:
    cat = catalogue or load_catalogue()
    datasets = {
        "clips": {"title": "9 real recordings (recorded transcripts)", **ev.run_cases(ev.clip_cases(), cat)},
        "phrasings": {"title": "57 written transcripts (same text to both systems)", **ev.run_cases(ev.load_phrasings(), cat)},
    }
    return {"generated": str(date.today()), "mode": "recorded transcripts, no live API calls", "stt_note": STT_NOTE,
            "naive_definition": ev.NAIVE_DEFINITION, "caveats": CAVEATS,
            "break": ev.run_all_break(cat), "datasets": datasets}


def _t(d: dict, system: str, key: str) -> int:
    return d["totals"][system][key]


def markdown(r: dict) -> str:
    L = [f"# Evaluation: naive baseline vs Clariflow ({r['generated']})", "",
         f"**Mode:** {r['mode']}. {r['stt_note']}", "", f"**What 'naive' means:** {r['naive_definition']}", "",
         "## Risky fields saved without a question", "",
         "Risky = a saved value that is wrong, a value assumed where the speech was genuinely ambiguous, or an ambiguity saved with no question.", "",
         "| Dataset | System | Checked items | Wrong | Assumed | Unresolved, unflagged | **Risky total** | Facts not saved | Questions raised (inherent) | Extra questions | Corrections kept |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in r["datasets"].values():
        for system, label in (("naive", "Naive"), ("clariflow", "Clariflow (before answers)")):
            t = d["totals"][system]
            L.append(f"| {d['title']} (n={d['n_cases']}) | {label} | {t['slots']} | {t['wrong']} | {t['assumed']} | "
                     f"{t['unresolved']} | **{t['risky']}** | {t['missing']} | {t['handled']} | {t['unnecessary_questions']} | "
                     f"{t['corrections_kept']} of {t['corrections_total']} |")
    L += ["", "## Break mode (6 scenarios through the production pipeline)", "",
          "| Scenario | Source | Clariflow | Checks passed | Naive risky saves |", "|---|---|---|---|---|"]
    for b in r["break"]:
        ok = sum(c["passed"] for c in b["checks"])
        L.append(f"| {b['title']} | {b['provenance']} | {'PASS' if b['passed'] else 'FAIL'} | {ok}/{len(b['checks'])} | {b['naive']['risky']} |")
    L += ["", "### Break mode details", ""]
    for b in r["break"]:
        L += [f"**{b['title']}** ({b['id']}): {b['what_it_tests']}", f"- transcript: `{b['transcript']}`"]
        L += [f"- {'OK ' if c['passed'] else 'FAIL'} {c['name']}: expected `{c['expected']}`, got `{c['actual']}`" for c in b["checks"]]
        L += [f"- naive: {f}" for f in b["naive"]["flaws"]] or ["- naive: no flaw found in this scenario"]
        L.append("")
    L += ["## Known failures and costs (Clariflow rows)", ""]
    found = False
    for key, d in r["datasets"].items():
        for row in d["rows"]:
            for n in row["clariflow"]["score"]["notes"]:
                L.append(f"- [{key}/{row['id']}] {n}")
                found = True
    if not found:
        L.append("- none recorded")
    L += ["", "## Caveats", ""] + [f"- {c}" for c in r["caveats"]]
    return "\n".join(L) + "\n"


def chart_svg(r: dict) -> str:
    rows = []
    for d in r["datasets"].values():
        for system, label in (("naive", "Naive baseline"), ("clariflow", "Clariflow")):
            t = d["totals"][system]
            rows.append((d["title"], label, t["wrong"] + t["assumed"], t["unresolved"], t["slots"]))
    longest = max(1, max(a + b for _, _, a, b, _ in rows))
    left, bar_w, h, top = 250, 330, 28, 110
    height = top + len(rows) * (h + 22) + 90
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {height}" role="img" '
           f'aria-label="Risky fields saved without a question: naive baseline versus Clariflow">',
           "<style>text{font:14px system-ui,sans-serif;fill:#1f2937}.s{font-size:12px;fill:#4b5563}.t{font-size:18px;font-weight:600}"
           "@media (prefers-color-scheme:dark){text{fill:#e5e7eb}.s{fill:#9ca3af}}</style>",
           '<text class="t" x="20" y="30">Risky fields saved without a question</text>',
           '<text class="s" x="20" y="52">Wrong or assumed values, plus ambiguities saved with no question. Fewer is better.</text>',
           '<rect x="20" y="66" width="12" height="12" fill="#9a3412"/><text class="s" x="38" y="77">wrong or assumed value</text>',
           '<rect x="200" y="66" width="12" height="12" fill="#fb923c"/><text class="s" x="218" y="77">ambiguity saved, no question</text>']
    y, last_title = top, None
    for title, label, a, b, slots in rows:
        if title != last_title:
            out.append(f'<text class="s" x="20" y="{y - 6}">{escape(title)}</text>')
            last_title = title
        out.append(f'<text x="{left - 10}" y="{y + 19}" text-anchor="end">{escape(label)}</text>')
        wa, wb = bar_w * a / longest, bar_w * b / longest
        if a:
            out.append(f'<rect x="{left}" y="{y}" width="{wa:.1f}" height="{h}" fill="#9a3412"/>')
        if b:
            out.append(f'<rect x="{left + wa:.1f}" y="{y}" width="{wb:.1f}" height="{h}" fill="#fb923c"/>')
        out.append(f'<text x="{left + wa + wb + 8:.1f}" y="{y + 19}">{a + b} of {slots} checked items</text>')
        y += h + 22
    out.append(f'<text class="s" x="20" y="{y + 14}">Recorded Prisma v3.0 transcripts, {escape(r["generated"])}. Naive = a baseline we wrote, not a real product.</text>')
    out.append(f'<text class="s" x="20" y="{y + 32}">Clariflow counts are its draft before any human answer; it cannot save until questions are resolved.</text>')
    out.append(f'<text class="s" x="20" y="{y + 50}">Truth written by the code author; one speaker, quiet room; the written set was tuned against. Not a general accuracy claim.</text>')
    out.append("</svg>")
    return "\n".join(out)
