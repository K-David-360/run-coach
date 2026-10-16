"""
plan_generator.py — Builds a concrete training session from a rule decision.

The plan cycles every 6 weeks: 5 build weeks + 1 deload (see cycle.py).
Run plan tables hold build weeks 1–5 only; week 6 reuses week 5 as its base
and the DELOAD decision cuts it to ~70% (deload_work_min).

  Phase 1: both runs Zone 2 easy.
  Phase 2: Run B becomes a progression run (Zone 2 → Zone 3 finish).
  Phase 3: Run B becomes intervals; Run A holds at 33 min work for weeks 3–5.

Phase advances manually in plan_state.json after the LTHR field test.

Rule overrides:
  SUPPRESS  → easy, duration capped below base
  DELOAD    → zone 2 easy blocks, ~70% duration (Galpin protocol)
  REDUCE    → keep type, work block trimmed ~15%
  HOLD      → base plan as-is
  BUILD     → easy +10% (Phase 1); session upgrade in Phase 2+
"""

import json
import os
import uuid
from datetime import date
from math import ceil

from cycle import jump_prescription

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")

# ── Phase 1 plan — all Zone 2 easy (no intensity) ────────────────────────────
# work_min is the main work block only; warmup (5) + cooldown (5) add 10 min.
_PLAN_PHASE1 = {
    1: {"A": {"type": "easy", "work_min": 18},   # 28 min total
        "B": {"type": "easy", "work_min": 20}},  # 30 min total
    2: {"A": {"type": "easy", "work_min": 20},
        "B": {"type": "easy", "work_min": 23}},
    3: {"A": {"type": "easy", "work_min": 23},
        "B": {"type": "easy", "work_min": 25}},
    4: {"A": {"type": "easy", "work_min": 24},
        "B": {"type": "easy", "work_min": 26}},
    5: {"A": {"type": "easy", "work_min": 25},
        "B": {"type": "easy", "work_min": 27}},
}

# ── Phase 2 plan — Run B becomes a progression run ───────────────────────────
_PLAN_PHASE2 = {
    1: {"A": {"type": "easy",        "work_min": 25},
        "B": {"type": "progression", "work_min": 25}},
    2: {"A": {"type": "easy",        "work_min": 27},
        "B": {"type": "progression", "work_min": 27}},
    3: {"A": {"type": "easy",        "work_min": 30},
        "B": {"type": "progression", "work_min": 30}},
    4: {"A": {"type": "easy",        "work_min": 32},
        "B": {"type": "progression", "work_min": 32}},
    5: {"A": {"type": "easy",        "work_min": 33},
        "B": {"type": "progression", "work_min": 33}},
}

# ── Phase 3 plan — Run B becomes intervals; Run A holds (intervals every week) ─
_PLAN_PHASE3 = {
    1: {"A": {"type": "easy",      "work_min": 28},
        "B": {"type": "intervals", "work_min": None}},
    2: {"A": {"type": "easy",      "work_min": 30},
        "B": {"type": "intervals", "work_min": None}},
    3: {"A": {"type": "easy",      "work_min": 33},
        "B": {"type": "intervals", "work_min": None}},
    4: {"A": {"type": "easy",      "work_min": 33},
        "B": {"type": "intervals", "work_min": None}},
    5: {"A": {"type": "easy",      "work_min": 33},
        "B": {"type": "intervals", "work_min": None}},
}

_PLAN_BY_PHASE = {1: _PLAN_PHASE1, 2: _PLAN_PHASE2, 3: _PLAN_PHASE3}

_BUILD_WEEKS = 5


def plan_week_for(week_in_cycle: int) -> int:
    """Plan-table row for a cycle week; the deload week uses the last build week as its base."""
    return min(week_in_cycle, _BUILD_WEEKS)


def deload_work_min(base_work_min) -> int:
    """Deload work block: ~70% of the base week's work, Zone 2 (Galpin protocol)."""
    return max(8, ceil((base_work_min or 18) * 0.70))

_WARMUP_MIN = 5
_COOLDOWN_MIN = 5


# ── Block builders ────────────────────────────────────────────────────────────

def _easy_blocks(work_min: int) -> list:
    return [
        {"name": "Warmup",   "duration_min": _WARMUP_MIN,  "zone": "zone1",
         "notes": "Easy walk or very light jog — just get the blood moving."},
        {"name": "Work",     "duration_min": work_min,      "zone": "zone2",
         "notes": "Conversational pace, HR 125–140. Slow down or walk if HR climbs above 145."},
        {"name": "Cooldown", "duration_min": _COOLDOWN_MIN, "zone": "zone1",
         "notes": "Slow to a walk, let heart rate drop naturally."},
    ]


def _progression_blocks(work_min: int) -> list:
    easy_min = max(8, work_min - 8)
    quality_min = work_min - easy_min
    return [
        {"name": "Warmup",     "duration_min": _WARMUP_MIN,  "zone": "zone1",
         "notes": "Easy walk or very light jog."},
        {"name": "Easy",       "duration_min": easy_min,     "zone": "zone2",
         "notes": "Conversational pace, HR 125–140."},
        {"name": "Progression","duration_min": quality_min,  "zone": "zone3",
         "notes": "Comfortably hard — short sentences. HR 145–155. Do not go above 155."},
        {"name": "Cooldown",   "duration_min": _COOLDOWN_MIN,"zone": "zone1",
         "notes": "Easy jog then walk. Let HR come down before stopping."},
    ]


def _tempo_blocks(work_min: int) -> list:
    return [
        {"name": "Warmup",   "duration_min": _WARMUP_MIN,  "zone": "zone1",
         "notes": "Easy jog, build to a comfortable stride."},
        {"name": "Work",     "duration_min": work_min,      "zone": "zone3",
         "notes": "Comfortably hard — controlled breathing, sustainable effort. HR 145–155."},
        {"name": "Cooldown", "duration_min": _COOLDOWN_MIN, "zone": "zone1",
         "notes": "Slow jog then walk. Let HR come down before stopping."},
    ]


def _intervals_blocks() -> list:
    return [
        {"name": "Warmup",     "duration_min": _WARMUP_MIN, "zone": "zone1",
         "notes": "Easy jog to loosen up."},
        {"name": "Interval 1", "distance_m": 800,            "zone": "zone4",
         "notes": "Hard but controlled — finish feeling like you have one more in you."},
        {"name": "Rest",       "duration_min": 0.5,          "zone": "rest",
         "notes": "30 seconds — walk or stand, shake it out."},
        {"name": "Interval 2", "distance_m": 800,            "zone": "zone4",
         "notes": "Match the effort of interval 1."},
        {"name": "Cooldown",   "duration_min": _COOLDOWN_MIN,"zone": "zone1",
         "notes": "Easy jog then walk until fully recovered."},
    ]


_STRENGTH_PREFIX = {
    "BUILD":    "⬆️ ",
    "REDUCE":   "⬇️ ",
    "SUPPRESS": "⛔️ ",
    "DELOAD":   "⛔️ ",
    "HOLD":     "",
}

_STRENGTH_PHRASE = {
    "BUILD":    "Push it today.",
    "HOLD":     "Follow the plan.",
    "REDUCE":   "Pull back — same weight, drop to ~80% of your sets.",
    "DELOAD":   "Deload week — same weight, half the sets.",
    "SUPPRESS": "No lifting — walk only.",
}

_STRENGTH_NOTES = {
    "BUILD":    "Recovery looks strong — lift at full planned load.",
    "HOLD":     "Follow planned load.",
    "REDUCE":   "Back off on volume — keep the same weight as planned. Drop to roughly 80% of your normal sets.",
    "DELOAD":   "Deload week — keep the same weight as planned. Cut your sets to 50% of normal.",
    "SUPPRESS": "Rest day — no lifting today. Walk only.",
}

_DAY_LABEL = {
    "mon": "Push",
    "wed": "Pull",
    "fri": "Full",
}

# From health-bootcamp/01-protocol.md "Lift menu" (3 working sets, 1–3 reps in reserve).
_LIFT_MENU = {
    "mon": (
        "Squat 3 x 5–8\n"
        "Incline dumbbell press 3–4 x 8–10\n"
        "Superset: chest-supported row 3 x 8–10 + lateral raise 3 x 10–15\n"
        "Triceps pushdown 2 x 10–12"
    ),
    "wed": (
        "Trap-bar deadlift 3 x 5\n"
        "Pulldown or pull-up 3 x 8–10\n"
        "Superset: overhead press 3 x 8–10 + face pull 3 x 12–15\n"
        "Incline dumbbell curl 2–3 x 10–12"
    ),
    "fri": (
        "Leg press or split squat 3 x 8\n"
        "Bench 3 x 8–10\n"
        "Superset: single-arm row 3 x 8–10 + lateral raise 3 x 10–15\n"
        "Superset: hammer curl + overhead triceps extension 2 x 10–12\n"
        "Farmer carries 2 x 30–40 m if time allows"
    ),
}


def jump_line(rx: dict) -> str:
    """One-line jump prescription for session notes and calendar descriptions."""
    if rx["sets"] == 0:
        return "Jumps: none this week (deload)."
    return (
        f"Jumps: {rx['sets']} x {rx['reps']} countermovement jumps "
        f"(weekly target {rx['weekly_target']}). Land softly, rest 30-60 s."
    )


def generate_strength_session(decision: str, day: str, today: date = None, skip_jumps: bool = False) -> dict:
    if today is None:
        today = date.today()
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    label = _DAY_LABEL.get(day, "Strength")
    summary = (
        f"{_STRENGTH_PREFIX.get(decision, '')}\U0001f3cb️ {label} "
        f"— {_STRENGTH_PHRASE.get(decision, 'Follow the plan.')}"
    )
    blocks = []
    rx = jump_prescription(plan_state.get("cycle_start_date", ""), today)
    if not skip_jumps and decision not in ("DELOAD", "SUPPRESS") and rx["sets"] > 0:
        blocks.append({"name": "Jumps", "sets": rx["sets"], "reps": rx["reps"], "notes": jump_line(rx)})
    notes = _STRENGTH_NOTES.get(decision, "Follow planned load.")
    if day in _LIFT_MENU and decision != "SUPPRESS":
        notes += "\n" + _LIFT_MENU[day]
    blocks.append({"name": label, "notes": notes})
    return {
        "session_id": str(uuid.uuid4()),
        "date": today.isoformat(),
        "type": f"strength_{day}",
        "rule_fired": decision,
        "flag": "none",
        "summary": summary,
        "blocks": blocks,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _total_min(blocks: list) -> int:
    return sum(int(b.get("duration_min", 0)) for b in blocks)


def _blocks_for_type(session_type: str, work_min: int) -> list:
    if session_type == "easy":
        return _easy_blocks(work_min)
    elif session_type == "progression":
        return _progression_blocks(work_min)
    elif session_type == "tempo":
        return _tempo_blocks(work_min)
    elif session_type == "intervals":
        return _intervals_blocks()
    return _easy_blocks(work_min)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_session(decision: str, data: dict, today: date = None) -> dict:
    """
    Build a session dict from the rule decision and current plan state.

    Args:
        decision: SUPPRESS | DELOAD | REDUCE | HOLD | BUILD
        data:     The full normalised HealthKit JSON body.

    Returns:
        Session dict with session_id, date, type, rule_fired, flag, summary, blocks.
    """
    if today is None:
        today = date.today()
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    current_week = plan_state.get("current_week", 1)
    phase = plan_state.get("phase", 1)

    # Slot is fixed by calendar day: Tuesday (weekday 1) = A, Saturday (weekday 5) = B
    slot = "A" if today.weekday() == 1 else "B"

    plan_table = _PLAN_BY_PHASE.get(phase, _PLAN_PHASE1)
    week_plan = plan_table[plan_week_for(current_week)]
    base = week_plan[slot]
    base_type = base["type"]
    base_work_min = base["work_min"]  # None for intervals

    session_type = base_type
    blocks = []
    summary = ""

    # ── SUPPRESS ─────────────────────────────────────────────────────────────
    if decision == "SUPPRESS":
        session_type = "easy"
        work_min = max(8, (base_work_min or 18) - 5)
        blocks = _easy_blocks(work_min)
        summary = (
            f"Easy run — {_total_min(blocks)} min total. "
            "Recovery is genuinely poor — stay in Zone 1 only, no surges. "
            "Consider skipping entirely if you feel rough."
        )

    # ── DELOAD ───────────────────────────────────────────────────────────────
    elif decision == "DELOAD":
        session_type = "easy"
        # Interval slots have no work_min; deload them from the same week's easy run.
        work_min = deload_work_min(base_work_min or week_plan["A"]["work_min"])
        blocks = _easy_blocks(work_min)
        summary = (
            f"Deload run — {_total_min(blocks)} min total (~70% of planned). "
            "Zone 2 at your normal easy pace — same effort, less time."
        )

    # ── REDUCE ───────────────────────────────────────────────────────────────
    elif decision == "REDUCE":
        if base_type == "intervals":
            # Can't meaningfully cut intervals — swap to easy.
            session_type = "easy"
            work_min = max(10, round((base_work_min or 20) * 0.85))
            blocks = _easy_blocks(work_min)
            summary = (
                f"Easy run — {_total_min(blocks)} min total. "
                "Intervals swapped for easy today — HRV or sleep is off."
            )
        else:
            work_min = max(8, ceil((base_work_min or 18) * 0.85))
            blocks = _blocks_for_type(base_type, work_min)
            summary = (
                f"{base_type.capitalize()} run — {_total_min(blocks)} min total "
                "(trimmed ~15% from plan). Keep the effort controlled."
            )

    # ── HOLD ──────────────────────────────────────────────────────────────────
    elif decision in ("HOLD", ""):
        blocks = _blocks_for_type(base_type, base_work_min or 18)
        total = _total_min(blocks)
        if base_type == "easy":
            summary = f"Easy run — {total} min total. Follow the plan — steady Zone 2 effort."
        elif base_type == "progression":
            summary = f"Progression run — {total} min total. Easy start, Zone 3 finish."
        elif base_type == "tempo":
            summary = f"Tempo run — {total} min total. Comfortably hard pace for the work block."
        elif base_type == "intervals":
            session_type = "intervals"
            summary = "Interval session — 2×800 m. Warm up, two quality 800 m efforts, cool down."

    # ── BUILD ─────────────────────────────────────────────────────────────────
    elif decision == "BUILD":
        if base_type == "easy":
            work_min = ceil((base_work_min or 18) * 1.10)
            blocks = _easy_blocks(work_min)
            summary = (
                f"Easy run — {_total_min(blocks)} min total (+10%). "
                "Recovery looks strong — a bit of extra volume is warranted."
            )
        elif base_type == "progression":
            work_min = ceil((base_work_min or 20) * 1.10)
            blocks = _progression_blocks(work_min)
            summary = (
                f"Progression run — {_total_min(blocks)} min total (+10%). "
                "Strong recovery — push the Zone 3 finish a little further."
            )
        elif base_type == "intervals":
            session_type = "intervals"
            blocks = _intervals_blocks()
            summary = (
                "Interval session — 2×800 m. "
                "Strong recovery — push the pace on both reps."
            )
        else:
            work_min = ceil((base_work_min or 18) * 1.10)
            blocks = _easy_blocks(work_min)
            summary = f"Easy run — {_total_min(blocks)} min total (+10%)."

    # ── Fallback ──────────────────────────────────────────────────────────────
    else:
        work_min = base_work_min or 18
        blocks = _easy_blocks(work_min)
        summary = f"Easy run — {_total_min(blocks)} min total."

    return {
        "session_id": str(uuid.uuid4()),
        "date": today.isoformat(),
        "type": session_type,
        "rule_fired": decision,
        "flag": "none",
        "week": current_week,
        "slot": slot,
        "phase": phase,
        "summary": summary,
        "blocks": blocks,
    }
