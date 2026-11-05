"""Run the evaluation and write evaluation/results/eval_<date>.{json,md,svg}.

  python -m scripts.run_eval

Uses recorded transcripts only: no Gnani calls, no credits. Re-run after any change to the
extractor, lexicons or rules; commit the new files so results stay versioned by date.
"""
import json
import sys
from pathlib import Path

from backend.app.services.evalreport import build, chart_svg, markdown

OUT = Path(__file__).resolve().parents[1] / "evaluation" / "results"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    r = build()
    stem = f"eval_{r['generated']}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{stem}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / f"{stem}.md").write_text(markdown(r), encoding="utf-8")
    (OUT / f"{stem}.svg").write_text(chart_svg(r), encoding="utf-8")
    for d in r["datasets"].values():
        n, c = d["totals"]["naive"], d["totals"]["clariflow"]
        print(f"{d['title']}: risky saves naive {n['risky']} vs Clariflow {c['risky']} of {n['slots']} checked items")
    print("Break mode:", sum(b["passed"] for b in r["break"]), "of", len(r["break"]), "scenarios pass")
    print("wrote", OUT / stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
