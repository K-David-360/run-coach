"""
bodycomp/flags.py — Read-only hooks from the weekly check into the daily output.

S1_NOTE is the one body-comp sentence allowed in the daily session JSON (David,
2026-10-16): fixed text, no numbers, never in plan_state.json or the calendar.
OPTIONAL_RUN_NOTE is a training note driven by HRV only.
"""

from datetime import date, timedelta

S1_NOTE = "Sleep was short last week: REDUCE volume (same weight, ~80% of sets), skip jumps."
OPTIONAL_RUN_NOTE = " Optional today: sleep or HRV is down, an easy walk is fine."


def s1_active(report, today: date = None) -> bool:
    """True from the Sunday after an S1-AMBER week through the following Saturday."""
    if today is None:
        today = date.today()
    if not report:
        return False
    if not any(r.get("id") == "S1" and r.get("severity") == "AMBER" for r in report.get("results", [])):
        return False
    week_ending = date.fromisoformat(report["week_ending"])
    return week_ending + timedelta(days=1) <= today <= week_ending + timedelta(days=7)
