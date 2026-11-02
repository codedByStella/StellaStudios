import time
import json
import subprocess
from datetime import datetime, timezone

import sys
sys.path.append("REDACTED — production engine path")

# ---------------------------------------------------
# CONFIG & PATHS
# ---------------------------------------------------

ENGINE_ROOT = "REDACTED — production engine path"
CONFIG_PATH = "REDACTED — production configuration path"

# ---------------------------------------------------
# CONFIG LOADER
# ---------------------------------------------------

def load_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)
    return cfg["times"], cfg["mode"]

# ---------------------------------------------------
# PIPELINE RUNNER
# ---------------------------------------------------

def run_pipeline(mode: str):
    try:
        result = subprocess.check_output(
            ["python3", "-m", "engine.parts.wiring.pipeline", mode],
            stderr=subprocess.STDOUT,
            cwd="REDACTED — production working directory"
        )

        # REDACTED — raw pipeline output may contain private metadata,
        # generated content, filesystem paths, or service information.

    except subprocess.CalledProcessError as e:
        # REDACTED — subprocess output may expose private runtime details.
        print("[PIPELINE ERROR] Subprocess returned a nonzero exit status.")

    except Exception as e:
        print(f"[PIPELINE ERROR] {type(e).__name__}")

# ---------------------------------------------------
# MAIN LOOP
# ---------------------------------------------------

def main():
    print("[SCHEDULER] Started.")

    last_triggered = None
    last_date = None

    while True:
        utc_now = datetime.now(timezone.utc)
        now = utc_now.strftime("%H:%M")
        current_date = utc_now.date()

        # Reset the trigger at midnight (new UTC day)
        if last_date != current_date:
            print("[SCHEDULER] New day detected — Resetting last_triggered")
            last_triggered = None
            last_date = current_date

        # Load config safely
        try:
            times, mode = load_config()
        except Exception as e:
            print(f"[SCHEDULER] CONFIG ERROR: {type(e).__name__}")
            time.sleep(5)
            continue

        # REDACTED — configured schedule values and runtime state
        # are not exposed in diagnostic output.

        # Trigger pipeline on schedule
        if now in times and last_triggered != now:
            print(f"[SCHEDULER] MATCH ({now}) — Running pipeline")
            run_pipeline(mode)
            last_triggered = now

        time.sleep(1)

if __name__ == "__main__":
    main()
