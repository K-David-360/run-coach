"""
bodycomp/checks.py — Pure functions: Shortcut samples → weekly metrics → rule results.

The weekly window is Sunday..Saturday ending on `week_ending` (a Saturday), so
food logs are complete when the Sunday-morning Shortcut posts.
"""

from datetime import date, timedelta


def week_days(week_ending: str) -> list:
    end = date.fromisoformat(week_ending)
    if end.weekday() != 5:
        raise ValueError("week_ending must be a Saturday")
    return [(end - timedelta(days=6 - i)).isoformat() for i in range(7)]


def _positive(value):
    """Float for a usable value; None for '', null, 0, negative or junk (Shortcuts sends '')."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def parse_samples(text: str, days: list, how: str) -> list:
    """Group 'YYYY-MM-DD=value' lines into the 7 days; how is 'mean' or 'sum'."""
    by_day = {d: [] for d in days}
    for line in (text or "").splitlines():
        day, sep, raw = line.strip().partition("=")
        value = _positive(raw)
        if sep and day in by_day and value is not None:
            by_day[day].append(value)
    result = []
    for d in days:
        vals = by_day[d]
        if not vals:
            result.append(None)
        elif how == "mean":
            result.append(sum(vals) / len(vals))
        else:
            result.append(sum(vals))
    return result


def sleep_nights(history: list, days: list) -> list:
    """Total sleep hours recorded by the daily Shortcut on days in the window."""
    nights = []
    for entry in history:
        if entry.get("session", {}).get("date") in days:
            hrs = _positive(entry.get("run_data", {}).get("sleep", {}).get("total_hrs"))
            if hrs is not None:
                nights.append(hrs)
    return nights


def _avg(values: list, digits: int = 1):
    present = [v for v in values if v is not None]
    if not present:
        return None, 0
    return round(sum(present) / len(present), digits), len(present)


def _optional_int(value):
    number = _positive(value)
    return int(number) if number is not None else (0 if str(value).strip() == "0" else None)


def _optional_bool(value):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in ("true", "yes"):
        return True
    if text in ("false", "no"):
        return False
    return None


def summarize_week(payload: dict, history: list) -> dict:
    days = week_days(payload["week_ending"])
    avg_weight, weight_days = _avg(parse_samples(payload.get("weight_samples", ""), days, "mean"))
    avg_protein, protein_days = _avg(parse_samples(payload.get("protein_samples", ""), days, "sum"))
    avg_kcal, kcal_days = _avg(parse_samples(payload.get("energy_samples", ""), days, "sum"))
    avg_steps, steps_days = _avg(parse_samples(payload.get("steps_samples", ""), days, "sum"), 0)
    return {
        "week_ending": payload["week_ending"],
        "avg_weight_lb": avg_weight,
        "weight_days": weight_days,
        "avg_protein_g": avg_protein,
        "protein_days": protein_days,
        "avg_kcal": avg_kcal,
        "kcal_days": kcal_days,
        "avg_steps": int(avg_steps) if avg_steps is not None else None,
        "steps_days": steps_days,
        "sleep_nights": len(sleep_nights(history, days)),
        "short_sleep_nights": None,
        "waist_in": _positive(payload.get("waist_in")),
        "lift_sessions_done": _optional_int(payload.get("lift_sessions_done")),
        "lift_stalled": _optional_bool(payload.get("lift_stalled")),
    }
