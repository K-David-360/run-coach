"""
bodycomp/checks.py — Pure functions: weekly payload → metrics → rule results → report.

The payload carries 7 daily values per metric for the Sunday..Saturday window
ending on `week_ending` (a Saturday), grouped by day in the Shortcut, so food
logs are complete when the Sunday-morning Shortcut posts.
"""

import math
import re
from datetime import date, timedelta

from cycle import is_deload_week, week_in_cycle

ARRAY_FIELDS = ["weights_lb", "protein_g_daily", "energy_kcal_daily", "steps_daily", "sleep_hrs_daily"]

_NUMBER = re.compile(r"[-+]?[\d.,]+")
_DECIMAL_COMMA = re.compile(r"\d+,\d{1,2}")


def week_days(week_ending: str) -> list:
    end = date.fromisoformat(week_ending)
    if end.weekday() != 5:
        raise ValueError("week_ending must be a Saturday")
    return [(end - timedelta(days=6 - i)).isoformat() for i in range(7)]


def coerce_value(value, allow_zero: bool = False):
    """Float for a usable value, else None. Shortcuts may send '', null, units or separators."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = _NUMBER.search(str(value))
        if not match:
            return None
        text = match.group()
        text = text.replace(",", ".") if _DECIMAL_COMMA.fullmatch(text) else text.replace(",", "")
        try:
            number = float(text)
        except ValueError:
            return None
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        return None
    return number


def validate_payload(payload: dict):
    """Readable error message for a malformed payload, or None when it is usable."""
    try:
        week_days(str(payload.get("week_ending", "")))
    except ValueError:
        return "week_ending must be a Saturday (YYYY-MM-DD)"
    for field in ARRAY_FIELDS:
        values = payload.get(field)
        if not isinstance(values, list) or len(values) != 7:
            return f"{field} must be a list of 7 daily values (Sunday to Saturday)"
    return None


def _avg(values: list, digits: int = 1):
    present = [v for v in values if v is not None]
    if not present:
        return None, 0
    return round(sum(present) / len(present), digits), len(present)


def summarize_week(payload: dict) -> dict:
    weights = [coerce_value(v) for v in payload["weights_lb"]]
    protein = [coerce_value(v) for v in payload["protein_g_daily"]]
    kcal = [coerce_value(v) for v in payload["energy_kcal_daily"]]
    steps = [coerce_value(v, allow_zero=True) for v in payload["steps_daily"]]
    sleep = [coerce_value(v) for v in payload["sleep_hrs_daily"]]
    avg_weight, weight_days = _avg(weights)
    avg_protein, protein_days = _avg(protein)
    avg_kcal, kcal_days = _avg(kcal)
    avg_steps, steps_days = _avg(steps, 0)
    avg_sleep, sleep_nights = _avg(sleep)
    sessions = coerce_value(payload.get("lift_sessions_done"), allow_zero=True)
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
        "avg_sleep_hrs": avg_sleep,
        "sleep_nights": sleep_nights,
        "sleep_hrs": [h for h in sleep if h is not None],
        "short_sleep_nights": None,
        "lift_sessions_done": int(sessions) if sessions is not None else None,
    }


# ── Rules ─────────────────────────────────────────────────────────────────────

SEVERITY_ORDER = ["RED", "AMBER", "INFO", "OK"]

RULE_LABELS = {
    "W": "weight data", "P": "protein data", "E": "calorie data",
    "W1": "weight hold", "W2": "fast loss", "W3": "still dropping", "W4": "flat",
    "P1": "protein", "P2": "protein low", "P3": "protein per kg", "E1": "calories",
    "S1": "sleep", "S2": "steps", "L2": "sessions", "D1": "deload next week",
}

_LB_PER_KG = 2.2046


def _bc_week(start: str, week_ending: str):
    try:
        days = (date.fromisoformat(week_ending) - date.fromisoformat(start)).days
    except (ValueError, TypeError):
        return None
    return days // 7 + 1


def _recent_deltas(delta, past: list, n: int) -> list:
    """This week's delta followed by the previous n-1 stored deltas (newest first)."""
    deltas = [delta] + [r.get("metrics", {}).get("delta_lb") for r in reversed(past)]
    return deltas[:n] if len(deltas) >= n else []


def _banner(m: dict, results: list, weight_ok: bool, protein_ok: bool) -> str:
    if weight_ok:
        delta = "new" if m["delta_lb"] is None else f"{m['delta_lb']:+.1f}"
        weight = f"weight {m['avg_weight_lb']:.1f} ({delta})"
    else:
        weight = "weight n/a"
    fired = {r["id"]: r["severity"] for r in results if r["severity"] != "OK"}
    pstatus = next((fired[i].lower() for i in ("P2", "P1") if i in fired), "OK")
    protein = f"protein {pstatus}" if protein_ok else "protein n/a"
    steps = f"steps {m['avg_steps'] / 1000:.1f}k" if m["avg_steps"] is not None else "steps n/a"
    text = f"Weekly: {weight}, {protein}, {steps}"
    counts = []
    for sev in SEVERITY_ORDER[:-1]:
        labels = [RULE_LABELS[r["id"]] for r in results if r["severity"] == sev]
        if labels:
            counts.append(f"{len(labels)} {sev.lower()} ({', '.join(labels)})")
    if counts:
        text += ", " + ", ".join(counts)
    return text + "."


def weekly_check(payload: dict, past_reports: list, config: dict, cycle_start: str) -> dict:
    """Run every rule for one week. past_reports: stored reports; only earlier weeks are used."""
    m = summarize_week(payload)
    week_ending = m["week_ending"]
    phase = config["bc_phase"]
    past = sorted((r for r in past_reports if r.get("week_ending", "") < week_ending),
                  key=lambda r: r["week_ending"])
    bc_week = _bc_week(config["bc_phase_start_date"], week_ending)
    results = []

    def add(rule_id, severity, message):
        results.append({"id": rule_id, "severity": severity, "message": message})

    # ── Weight ────────────────────────────────────────────────────────────────
    avg = m["avg_weight_lb"]
    weight_ok = m["weight_days"] >= config["min_weight_days"]
    # Only weeks with enough weigh-ins anchor the delta.
    prev_avg = next((r["metrics"]["avg_weight_lb"] for r in reversed(past)
                     if r.get("metrics", {}).get("avg_weight_lb") is not None
                     and r["metrics"].get("weight_days", 0) >= config["min_weight_days"]), None)
    m["delta_lb"] = round(avg - prev_avg, 1) if weight_ok and prev_avg is not None else None
    if not weight_ok:
        add("W", "INFO", "insufficient data")
    else:
        delta = m["delta_lb"]
        baseline = config["baseline_weight_lb"]
        if phase == "BC-1" and baseline is None:
            add("W1", "OK", "not configured")
        elif phase == "BC-1" and (bc_week is None or bc_week <= config["w1_max_bc_week"]):
            if abs(avg - baseline) > config["w1_hold_band_lb"]:
                add("W1", "INFO", "Weight drifting from baseline")
            else:
                add("W1", "OK", "Weight holding")
        if delta is not None:
            recent = _recent_deltas(delta, past, config["w2_weeks"])
            if recent and all(d is not None and d < -config["w2_fast_loss_lb"] for d in recent):
                add("W2", "AMBER", "Falling too fast: add 150-200 kcal/day")
            if (phase == "BC-1" and (bc_week is None or bc_week > config["w3_early_rise_weeks"])
                    and delta < -config["w3_loss_lb"]):
                add("W3", "AMBER", "Still dropping: add 150-200 kcal/week until it holds")
            recent = _recent_deltas(delta, past, config["w4_weeks"])
            if phase == "BC-2" and recent and all(d is not None and abs(d) < config["w4_flat_lb"] for d in recent):
                add("W4", "INFO", "Flat: cut about 150 kcal or add 2,000 steps")

    # ── Nutrition ─────────────────────────────────────────────────────────────
    protein_ok = m["protein_days"] >= config["min_nutrition_days"]
    m["protein_g_per_kg"] = None
    if not protein_ok:
        add("P", "INFO", "insufficient data")
    else:
        p = m["avg_protein_g"]
        if config["protein_low_g"] is None:
            add("P2", "OK", "not configured")
        if config["protein_avg_min_g"] is None:
            add("P1", "OK", "not configured")
        if config["protein_low_g"] is not None and p < config["protein_low_g"]:
            add("P2", "RED", "Protein low: fix before touching calories")
        elif config["protein_avg_min_g"] is not None and p < config["protein_avg_min_g"]:
            add("P1", "AMBER", "Protein under target")
        if avg is not None:
            m["protein_g_per_kg"] = round(p / (avg / _LB_PER_KG), 2)
            if m["protein_g_per_kg"] < config["protein_min_g_per_kg"]:
                add("P3", "INFO", f"Protein {m['protein_g_per_kg']:.2f} g/kg")
    if m["kcal_days"] < config["min_nutrition_days"]:
        add("E", "INFO", "insufficient data")
    else:
        floor = config["kcal_floor_bc1"] if phase == "BC-1" else config["kcal_floor_bc2"]
        if floor is None:
            add("E1", "OK", "not configured")
        elif m["avg_kcal"] < floor:
            add("E1", "AMBER", "Calories under floor")

    # ── Sleep, steps, lifts, deload ───────────────────────────────────────────
    m["short_sleep_nights"] = sum(1 for h in m.pop("sleep_hrs") if h < config["sleep_short_hrs"])
    if m["short_sleep_nights"] >= config["sleep_short_nights"]:
        add("S1", "AMBER", "Sleep short: REDUCE lift volume next week, skip jumps, eat at maintenance")
    if m["avg_steps"] is not None and m["avg_steps"] < config["steps_min_avg"]:
        add("S2", "INFO", "Steps low")
    if m["lift_sessions_done"] is not None and m["lift_sessions_done"] < config["lift_sessions_min"]:
        add("L2", "INFO", "Fewer than 3 lift sessions")
    next_monday = date.fromisoformat(week_ending) + timedelta(days=2)
    if is_deload_week(week_in_cycle(cycle_start, next_monday)):
        add("D1", "INFO", "Deload week next week")

    results.sort(key=lambda r: SEVERITY_ORDER.index(r["severity"]))
    highest = results[0]["severity"] if results else "OK"
    return {
        "week_ending": week_ending,
        "bc_phase": phase,
        "bc_week": bc_week,
        "metrics": m,
        "results": results,
        "highest": highest,
        "banner": _banner(m, results, weight_ok, protein_ok),
    }
