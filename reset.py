"""
reset.py — Reset plan state and history for a fresh start.

Run this before going live on the Pi, or any time you want to
start the 4-week plan from scratch.

Usage:
    python3 reset.py
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")
HISTORY_FILE    = os.path.join(DATA_DIR, "history.json")

DEFAULT_PLAN_STATE = {
    "current_week": 1,
    "run_in_week": 0,
    "consecutive_suppress": 0,
    "total_runs": 0,
    "phase": 1,
    "last_processed_workout_date": "",
    "last_session_date": "",
    "last_session_type": "",
    "last_session_decision": "",
}

def reset():
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(PLAN_STATE_FILE, "w") as f:
        json.dump(DEFAULT_PLAN_STATE, f, indent=2)
    print(f"✓ plan_state.json reset to week 1")

    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)
    print(f"✓ history.json cleared")

    print("\nReady. Next POST to /healthkit will be run 1, week 1, slot A.")

if __name__ == "__main__":
    reset()
