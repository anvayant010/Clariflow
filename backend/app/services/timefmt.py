"""Times for people: "14:00" -> "2:00 PM". The stored/normalised value stays 24-hour (unambiguous for software);
only what a person reads or hears uses the 12-hour clock."""
import re

_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")


def clock12(value) -> str:
    """"14:00" -> "2:00 PM", "00:30" -> "12:30 AM", "12:00" -> "12:00 PM". Anything else is returned unchanged."""
    m = _HHMM.match(str(value or "").strip())
    if not m:
        return "" if value is None else str(value)
    h, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= minute <= 59):
        return str(value)
    return f"{(h % 12) or 12}:{minute:02d} {'AM' if h < 12 else 'PM'}"
