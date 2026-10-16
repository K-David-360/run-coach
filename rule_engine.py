"""
rule_engine.py — Priority-based decision engine for the running coach.

Decisions (in priority order):
  SUPPRESS — HRV crashed hard AND sleep bombed: skip the run entirely
  DELOAD   — Scheduled week 6, repeated suppresses, or repeated terrible sleep
  REDUCE   — HRV trending down, sleep short, or load elevated: pull back volume
  BUILD    — HRV elevated, good sleep, low load: push a little further
  HOLD     — Default: follow the base plan exactly

Modifiers only make decisions MORE conservative, never less. The most
conservative signal wins. This matches the training structure doc.
"""

import json
import os
from datetime import date, timedelta

from cycle import is_deload_week

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

_DEFAULT_PLAN_STATE = {
    "current_week": 1,
    "run_in_week": 0,
    "consecutive_suppress": 0,
    "total_runs": 0,
    "phase": 1,
}


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _get_consecutive_suppress() -> int:
    """Count the most recent unbroken run of SUPPRESS decisions in history."""
    history = _load_json(HISTORY_FILE, default=[])
    count = 0
    for entry in reversed(history):
        if entry.get("decision", {}).get("decision") == "SUPPRESS":
            count += 1
        else:
            break
    return count


def _count_nights_below(threshold_hrs: float, days: int = 7, today: date = None) -> int:
    """Count history entries in the last `days` calendar days where total sleep < threshold."""
    if today is None:
        today = date.today()
    history = _load_json(HISTORY_FILE, default=[])
    cutoff = (today - timedelta(days=days)).isoformat()
    count = 0
    for entry in history:
        entry_date = entry.get("session", {}).get("date") or entry.get("run_data", {}).get("last_workout_date", "")
        if entry_date < cutoff:
            continue
        total = entry.get("run_data", {}).get("sleep", {}).get("total_hrs", 0)
        if 0 < total < threshold_hrs:
            count += 1
    return count


def _resting_hr_elevated_days(n: int = 7) -> int:
    """
    Count entries in the last n history records where resting HR exceeded
    the personal baseline by 5+ bpm.

    Baseline = mean of all available resting_hr values in history.
    Returns 0 if fewer than 3 data points (can't establish a reliable baseline).
    """
    history = _load_json(HISTORY_FILE, default=[])
    all_rhr = [
        e["run_data"]["recovery"]["resting_hr"]
        for e in history
        if e.get("run_data", {}).get("recovery", {}).get("resting_hr")
    ]
    if len(all_rhr) < 3:
        return 0
    baseline = sum(all_rhr) / len(all_rhr)
    count = 0
    for entry in history[-n:]:
        rhr = entry.get("run_data", {}).get("recovery", {}).get("resting_hr")
        if rhr and rhr >= baseline + 5:
            count += 1
    return count


def rule_engine(data: dict, hrv_ratio: float, today: date = None) -> dict:
    """
    Evaluate rules in priority order and return the first match.

    Args:
        data:      The full HealthKit JSON body (normalised by server.py).
        hrv_ratio: hrv_last_night / hrv_7d_avg

    Returns:
        {"decision": str, "reason": str, "trigger": str, "action": str}
    """
    plan_state = _load_json(PLAN_STATE_FILE, default=_DEFAULT_PLAN_STATE)
    current_week = plan_state.get("current_week", 1)
    consecutive_suppress = _get_consecutive_suppress()

    sleep = data.get("sleep", {})
    sleep_total_hrs = float(sleep.get("total_hrs", 0))
    sleep_deep_hrs = float(sleep.get("deep_hrs", 0))

    load = data.get("load", {})
    load_classification = load.get("classification", "steady")

    _deload_action = (
        "Deload week. Runs: same zone, ~70% duration. "
        "Strength: same weight, half the sets. No jumps."
    )

    # ── P1 SUPPRESS ──────────────────────────────────────────────────────────
    if hrv_ratio < 0.70 and (sleep_total_hrs < 5.0 or sleep_deep_hrs < 0.75):
        parts = [f"HRV ratio {round(hrv_ratio, 2)}"]
        if sleep_total_hrs < 5.0:
            parts.append(f"sleep {sleep_total_hrs:.1f}h")
        elif sleep_deep_hrs < 0.75:
            parts.append(f"deep sleep {sleep_deep_hrs:.1f}h")
        return {
            "decision": "SUPPRESS",
            "reason": " + ".join(parts),
            "trigger": "suppress",
            "action": (
                "Skip today's run — HRV and sleep are both in poor shape. "
                "Rest is the workout. Light walk only if you want to move."
            ),
        }

    # ── P2 DELOAD ────────────────────────────────────────────────────────────
    nights_below_5 = _count_nights_below(5.0, days=7, today=today)
    if is_deload_week(current_week):
        return {"decision": "DELOAD", "reason": "Scheduled deload (week 6)",
                "trigger": "deload_week", "action": _deload_action}
    if consecutive_suppress >= 2:
        return {"decision": "DELOAD", "reason": "2+ consecutive suppress days",
                "trigger": "suppress_streak", "action": _deload_action}
    if nights_below_5 >= 2:
        return {"decision": "DELOAD", "reason": "2+ nights < 5h sleep (last 7)",
                "trigger": "short_sleep_nights", "action": _deload_action}
    if load_classification == "well_above":
        return {"decision": "DELOAD", "reason": "Training load well above baseline",
                "trigger": "load", "action": _deload_action}

    # ── Base signal from load (proxy for ACWR) ────────────────────────────
    _load_base = {
        "above":      ("REDUCE", "Training load above baseline"),
        "steady":     ("HOLD",   "Training load steady"),
        "below":      ("BUILD",  "Training load below baseline"),
        "well_below": ("BUILD",  "Training load below baseline"),
    }
    base, reason = _load_base.get(load_classification, ("HOLD", "Training load steady"))
    trigger = "load"

    # ── HRV modifier (caps only — never upgrades) ─────────────────────────
    if hrv_ratio < 0.70:
        if base in ("BUILD", "HOLD"):
            base = "REDUCE"
            reason = f"HRV ratio {round(hrv_ratio, 2)}"
            trigger = "hrv"
    elif hrv_ratio < 0.90 and base == "BUILD":
        base = "HOLD"
        reason = f"HRV ratio {round(hrv_ratio, 2)} (suppressed BUILD)"
        trigger = "hrv"

    # ── Sleep modifiers ───────────────────────────────────────────────────
    if sleep_total_hrs < 6.0:
        before = base
        if base == "BUILD":
            base = "HOLD"
        elif base == "HOLD":
            base = "REDUCE"
        if base != before:
            reason = f"Sleep {sleep_total_hrs:.1f}h < 6h"
            trigger = "sleep"
    elif sleep_total_hrs < 7.5:
        if base == "BUILD":
            base = "HOLD"
            reason = f"Sleep {sleep_total_hrs:.1f}h < 7.5h (capped BUILD)"
            trigger = "sleep"

    # ── Resting HR modifier ───────────────────────────────────────────────
    if _resting_hr_elevated_days() >= 2 and base == "BUILD":
        resting_hr_val = data.get("recovery", {}).get("resting_hr", 0)
        base = "HOLD"
        reason = f"Resting HR elevated ({int(resting_hr_val)} bpm)"
        trigger = "rhr"

    # ── Return final decision ─────────────────────────────────────────────
    _actions = {
        "REDUCE": (
            "Keep session type, reduce duration ~15%. "
            "Strength: same weight, ~80% of sets."
        ),
        "BUILD": (
            "Extend easy run duration by 10%, or upgrade session type if Phase 2+. "
            "Strength: proceed as planned."
        ),
        "HOLD": "Follow the base plan exactly.",
    }
    return {
        "decision": base,
        "reason": reason,
        "trigger": trigger,
        # Poor recovery even when load already set REDUCE (used to skip jumps).
        "recovery_low": hrv_ratio < 0.70 or sleep_total_hrs < 6.0,
        "action": _actions.get(base, "Follow the base plan exactly."),
    }
