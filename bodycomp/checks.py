"""
bodycomp/checks.py — Pure functions: Shortcut samples → weekly metrics → rule results.

The weekly window is Sunday..Saturday ending on `week_ending` (a Saturday), so
food logs are complete when the Sunday-morning Shortcut posts.
"""

from datetime import date, timedelta

from cycle import is_deload_week, week_in_cycle


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


# ── Rules ─────────────────────────────────────────────────────────────────────

SEVERITY_ORDER = ["RED", "AMBER", "INFO", "OK"]

RULE_LABELS = {
    "W": "weight data", "P": "protein data", "E": "calorie data",
    "W1": "weight hold", "W2": "fast loss", "W3": "still dropping", "W4": "flat",
    "P1": "protein", "P2": "protein low", "P3": "protein per kg", "E1": "calories",
    "S1": "sleep", "S2": "steps", "L1": "lift stall", "L2": "sessions", "D1": "deload next week",
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


def _baseline(config: dict, past: list):
    if config["baseline_weight_lb"] is not None:
        return config["baseline_weight_lb"]
    for r in past:
        avg = r.get("metrics", {}).get("avg_weight_lb")
        if r.get("bc_phase") == "BC-1" and avg is not None:
            return avg
    return None


def _banner(m: dict, results: list, weight_ok: bool, protein_ok: bool) -> str:
    if weight_ok:
        delta = "new" if m["delta_lb"] is None else f"{m['delta_lb']:+.1f}"
        weight = f"weight {m['avg_weight_lb']:.1f} ({delta})"
    else:
        weight = "weight n/a"
    fired = {r["id"]: r["severity"] for r in results if r["severity"] != "OK"}
    pstatus = next((fired[i].lower() for i in ("P2", "P1") if i in fired), "OK")
    protein = f"protein {m['avg_protein_g']:.0f} g {pstatus}" if protein_ok else "protein n/a"
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


def weekly_check(payload: dict, history: list, past_reports: list, config: dict, cycle_start: str) -> dict:
    m = summarize_week(payload, history)
    week_ending = m["week_ending"]
    phase = config["bc_phase"]
    past = sorted((r for r in past_reports if r.get("week_ending") != week_ending),
                  key=lambda r: r["week_ending"])
    bc_week = _bc_week(config["bc_phase_start_date"], week_ending)
    results = []

    def add(rule_id, severity, message):
        results.append({"id": rule_id, "severity": severity, "message": message})

    # ── Weight ────────────────────────────────────────────────────────────────
    avg = m["avg_weight_lb"]
    weight_ok = m["weight_days"] >= config["min_weight_days"]
    prev_avg = next((r["metrics"].get("avg_weight_lb") for r in reversed(past)
                     if r.get("metrics", {}).get("avg_weight_lb") is not None), None)
    m["delta_lb"] = round(avg - prev_avg, 1) if weight_ok and prev_avg is not None else None
    if not weight_ok:
        add("W", "INFO", "insufficient data")
    else:
        delta = m["delta_lb"]
        baseline = _baseline(config, past)
        if phase == "BC-1" and baseline is not None and (bc_week is None or bc_week <= config["w1_max_bc_week"]):
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
        if floor is not None and m["avg_kcal"] < floor:
            add("E1", "AMBER", "Calories under floor")

    # ── Sleep, steps, lifts, deload ───────────────────────────────────────────
    nights = sleep_nights(history, week_days(week_ending))
    m["short_sleep_nights"] = sum(1 for h in nights if h < config["sleep_short_hrs"])
    if m["short_sleep_nights"] >= config["sleep_short_nights"]:
        add("S1", "AMBER", "Sleep short: REDUCE lift volume next week, skip jumps, eat at maintenance")
    if m["avg_steps"] is not None and m["avg_steps"] < config["steps_min_avg"]:
        add("S2", "INFO", "Steps low")
    if m["lift_stalled"] is True:
        add("L1", "INFO", "Lift stalled: check sleep and protein, then deload")
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
