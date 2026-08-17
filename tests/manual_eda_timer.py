"""
Phase 9: a simple wall-clock timer for measuring how long manual EDA
actually takes you -- a real, honest number instead of a guess.

This deliberately measures REAL elapsed time, including thinking and
typing, not just code execution -- because that's what "time saved"
actually has to mean when comparing against a human doing this for the
first time on an unfamiliar dataset.

Usage:
    python tests/manual_eda_timer.py start
    ... now go actually do your manual EDA, following the checklist in
        tests/manual_eda_checklist.md, in a fresh notebook or script ...
    python tests/manual_eda_timer.py stop
"""

import json
import sys
import time

TIMER_FILE = "tests/.manual_eda_timer.json"

if len(sys.argv) != 2 or sys.argv[1] not in ("start", "stop"):
    print("Usage: python tests/manual_eda_timer.py [start|stop]")
    sys.exit(1)

if sys.argv[1] == "start":
    with open(TIMER_FILE, "w") as f:
        json.dump({"start": time.time()}, f)
    print("Timer started. Go do your manual EDA now -- see tests/manual_eda_checklist.md")
else:
    try:
        with open(TIMER_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        print("No timer was started. Run 'python tests/manual_eda_timer.py start' first.")
        sys.exit(1)

    elapsed = time.time() - data["start"]
    minutes = elapsed / 60
    print(f"Manual EDA took {minutes:.1f} minutes ({elapsed:.0f} seconds).")
