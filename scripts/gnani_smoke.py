"""Manual smoke tests for the Gnani adapters. Spends real credits; keep clips short.

  python -m scripts.gnani_smoke tts "P-12 pump बंद पडला आहे" --lang mr-IN --out tmp/tts_mr.wav
  python -m scripts.gnani_smoke stt path/to/clip.wav --lang mr-IN
  python -m scripts.gnani_smoke stt path/to/clip.wav --lang indic-auto --fmt verbatim

Prints transcript metadata only. Never prints the API key.
"""
import argparse
import mimetypes
import sys
import time
from pathlib import Path

from backend.app.adapters.gnani_common import GnaniError
from backend.app.adapters.gnani_stt import transcribe
from backend.app.adapters.gnani_tts import synthesize
from backend.app.config import get_settings


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tts")
    t.add_argument("text")
    t.add_argument("--lang", default="mr-IN")
    t.add_argument("--voice")
    t.add_argument("--out", default="tmp/tts_out.wav")
    s = sub.add_parser("stt")
    s.add_argument("file")
    s.add_argument("--lang", default="indic-auto")
    s.add_argument("--fmt", default="verbatim")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

    settings = get_settings()
    print(settings)  # key_set only, never the key
    start = time.time()
    try:
        if args.cmd == "tts":
            audio = synthesize(args.text, args.lang, voice=args.voice)
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(audio)
            print(f"OK tts: {len(audio)} bytes -> {out} ({time.time() - start:.2f}s)")
        else:
            path = Path(args.file)
            ctype = mimetypes.guess_type(path.name)[0] or "audio/wav"
            r = transcribe(path.read_bytes(), path.name, args.lang, content_type=ctype, fmt=args.fmt)
            print(f"OK stt ({time.time() - start:.2f}s)")
            print(r.model_dump_json(indent=2))
    except GnaniError as e:
        print(f"FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
