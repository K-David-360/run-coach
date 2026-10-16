"""
cycle.py — Single source of truth for training-week math.

The plan runs in 6-week cycles: 5 build weeks + 1 deload week. Everything
(rule engine deload, run plan week, calendar, jump progression) derives from
plan_state["cycle_start_date"] through these functions.
"""

from datetime import date, timedelta

DELOAD_EVERY_N_WEEKS = 6

_JUMP_REPS = 10
_LIFT_DAYS_PER_WEEK = 3


def _parse(cycle_start: str):
    """Cycle start as a Monday: a mid-week date counts from its own week's Monday."""
    try:
        start = date.fromisoformat(cycle_start)
    except (ValueError, TypeError):
        return None
    return start - timedelta(days=start.weekday())


def block_week(cycle_start: str, today: date = None) -> int:
    """Absolute week number since cycle_start (1 on the start week); 0 before start."""
    if today is None:
        today = date.today()
    start = _parse(cycle_start)
    if start is None:
        return 1
    if today < start:
        return 0
    return (today - start).days // 7 + 1


def week_in_cycle(cycle_start: str, today: date = None) -> int:
    """Week within the current cycle, 1..DELOAD_EVERY_N_WEEKS. Before start reads as deload."""
    bw = block_week(cycle_start, today)
    if bw == 0:
        return DELOAD_EVERY_N_WEEKS
    return (bw - 1) % DELOAD_EVERY_N_WEEKS + 1


def is_deload_week(week: int) -> bool:
    return week == DELOAD_EVERY_N_WEEKS


def jump_prescription(cycle_start: str, today: date = None) -> dict:
    """Jump sets per lift day and weekly contact target; none in deload/pre-block weeks."""
    bw = block_week(cycle_start, today)
    if bw == 0 or is_deload_week(week_in_cycle(cycle_start, today)):
        return {"sets": 0, "reps": _JUMP_REPS, "weekly_target": 0}
    # Deload weeks before this one don't advance the progression.
    progression_week = bw - (bw - 1) // DELOAD_EVERY_N_WEEKS
    sets = 2 if progression_week <= 4 else 3
    return {"sets": sets, "reps": _JUMP_REPS, "weekly_target": sets * _JUMP_REPS * _LIFT_DAYS_PER_WEEK}
