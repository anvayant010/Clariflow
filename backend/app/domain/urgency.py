"""How urgent a report is, AS STATED BY THE PERSON. Never inferred from symptoms: smoke does not make something an
emergency, and a missing answer is not "can wait". The allowed answers are these four plus an explicit "unknown"."""

LEVELS = ["can_wait", "today", "stop_work", "emergency"]  # least to most urgent
ANSWERS = LEVELS + ["unknown"]
LABEL_EN = {"can_wait": "Can wait", "today": "Needs attention today", "stop_work": "Stop work now", "emergency": "Emergency"}
