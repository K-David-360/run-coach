"""
reset.py — Reset plan state and history for a fresh start.

Run this before going live on the Pi, or any time you want to
start the 4-week plan from scratch.

Usage:
    python3 reset.py
"""

import json
import os
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")
HISTORY_FILE    = os.path.join(DATA_DIR, "history.json")


def _most_recent_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def reset():
    os.makedirs(DATA_DIR, exist_ok=True)

    cycle_start = _most_recent_monday().isoformat()
    default_state = {
        "current_week": 1,
        "cycle_start_date": cycle_start,
        "consecutive_suppress": 0,
        "total_runs": 0,
        "phase": 1,
        "last_processed_workout_date": "",
        "last_execution_date": "",
        "last_execution_type": "",
        "last_execution_decision": "",
        "kb_weeks_elapsed": 0,
        "kb_peak_rung": 10,
    }

    with open(PLAN_STATE_FILE, "w") as f:
        json.dump(default_state, f, indent=2)
    print(f"✓ plan_state.json reset — cycle_start_date = {cycle_start}, week 1")

    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)
    print("✓ history.json cleared")

    print("\nReady. Next POST to /healthkit will be run 1, week 1, slot A (if Tuesday).")


if __name__ == "__main__":
    reset()
