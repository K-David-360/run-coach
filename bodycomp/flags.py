"""
bodycomp/flags.py — Read-only hooks from the weekly check into the daily output.

S1_NOTE is the one body-comp sentence allowed in the daily session JSON (David,
2026-10-16): fixed text, no numbers, never in plan_state.json or the calendar.
On an S1 week the calendar gets only the generic "Jumps: skip this week." line, and
Saturday's run becomes optional (OPTIONAL_RUN_NOTE), as it also does on low HRV
(David, 2026-10-16).
"""

from datetime import date, timedelta

S1_NOTE = "Sleep was short last week: REDUCE volume (same weight, ~80% of sets), skip jumps."
# Fixed variant for DELOAD/SUPPRESS days, whose own volume cut is already larger.
S1_NOTE_LOW_DAY = "Sleep was short last week: skip jumps."
OPTIONAL_RUN_NOTE = " Optional today: recovery is down, an easy walk is fine."


def s1_week_dates(report) -> set:
    """Dates (Sunday after an S1-AMBER week through the following Saturday); empty if no S1."""
    if not report:
        return set()
    if not any(r.get("id") == "S1" and r.get("severity") == "AMBER" for r in report.get("results", [])):
        return set()
    week_ending = date.fromisoformat(report["week_ending"])
    return {week_ending + timedelta(days=n) for n in range(1, 8)}


def s1_active(report, today: date = None) -> bool:
    """True from the Sunday after an S1-AMBER week through the following Saturday."""
    if today is None:
        today = date.today()
    return today in s1_week_dates(report)
