r"""Check that the SECOND Gnani key (GNANI_API_KEY_ID_2 in .env) works.

Makes ONE short Timbre call with only that key (a few credits of the second account) and prints OK or the reason it
failed. The key itself is never printed. Run:  python -m scripts.check_second_key
"""
import dataclasses
import sys

from backend.app.adapters import gnani_common, gnani_tts
from backend.app.config import get_settings

s = get_settings()
if not s.gnani_api_key_id_2:
    print("GNANI_API_KEY_ID_2 is not set in .env (add a line GNANI_API_KEY_ID_2=<the key>, no spaces or quotes).")
    sys.exit(1)
only_second = dataclasses.replace(s, gnani_api_key_id=s.gnani_api_key_id_2, gnani_api_key_id_2="")
try:
    audio = gnani_tts.synthesize("This is a test.", "en-IN", settings=only_second)
except gnani_common.GnaniError as e:
    print(f"FAILED: {e.kind} (HTTP {e.status}): {e.message}")
    sys.exit(2)
print(f"OK: the second key works ({len(audio)} bytes of audio came back). Now compare its credit balance on the dashboard.")
