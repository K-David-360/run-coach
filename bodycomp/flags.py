"""
bodycomp/flags.py — Read-only hooks from the weekly check into the daily output.

The sentences here are generic and number-free: they may appear in the daily
session JSON, but no body-comp values ever do.
"""

from datetime import date, timedelta

S1_NOTE = "Sleep was short last week: same weight, ~80% of sets, no jumps."
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
