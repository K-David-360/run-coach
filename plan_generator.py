"""
plan_generator.py — Builds a concrete training session from a rule decision.

Phase 1 (weeks 1–6, current): both runs Zone 2 easy only.
  The plan cycles every 4 weeks with a deload on week 4.

  Week 1:  Run A = easy 28 min  |  Run B = easy 30 min
  Week 2:  Run A = easy 30 min  |  Run B = easy 33 min
  Week 3:  Run A = easy 33 min  |  Run B = easy 35 min
  Week 4:  Run A = easy 20 min  |  Run B = easy 20 min  (deload)

Phase 2 / Phase 3 plan tables are defined but not yet active. Phase advances
manually in plan_state.json after the LTHR field test at week 6–8.

Rule overrides:
  SUPPRESS  → easy, duration capped below base
  DELOAD    → zone 1 easy blocks, deload durations
  REDUCE    → keep type, work block trimmed ~15%
  HOLD      → base plan as-is
  BUILD     → easy +10% (Phase 1); session upgrade in Phase 2+
"""

import json
import os
import uuid
from datetime import date
from math import ceil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")

# ── Phase 1 plan — all Zone 2 easy (no intensity) ────────────────────────────
# work_min is the main work block only; warmup (5) + cooldown (5) add 10 min.
_PLAN_PHASE1 = {
    1: {"A": {"type": "easy", "work_min": 18},   # 28 min total
        "B": {"type": "easy", "work_min": 20}},  # 30 min total
    2: {"A": {"type": "easy", "work_min": 20},   # 30 min total
        "B": {"type": "easy", "work_min": 23}},  # 33 min total
    3: {"A": {"type": "easy", "work_min": 23},   # 33 min total
        "B": {"type": "easy", "work_min": 25}},  # 35 min total
    4: {"A": {"type": "easy", "work_min": 10},   # 20 min total (deload)
        "B": {"type": "easy", "work_min": 10}},  # 20 min total (deload)
}

# ── Phase 2 plan — Run B becomes a progression run ───────────────────────────
_PLAN_PHASE2 = {
    1: {"A": {"type": "easy",        "work_min": 25},
        "B": {"type": "progression", "work_min": 25}},
    2: {"A": {"type": "easy",        "work_min": 27},
        "B": {"type": "progression", "work_min": 27}},
    3: {"A": {"type": "easy",        "work_min": 30},
        "B": {"type": "progression", "work_min": 30}},
    4: {"A": {"type": "easy",        "work_min": 15},
        "B": {"type": "easy",        "work_min": 15}},
}

# ── Phase 3 plan — Run B becomes intervals ────────────────────────────────────
_PLAN_PHASE3 = {
    1: {"A": {"type": "easy",      "work_min": 28},
        "B": {"type": "intervals", "work_min": None}},
    2: {"A": {"type": "easy",      "work_min": 30},
        "B": {"type": "intervals", "work_min": None}},
    3: {"A": {"type": "easy",      "work_min": 33},
        "B": {"type": "intervals", "work_min": None}},
    4: {"A": {"type": "easy",      "work_min": 15},
        "B": {"type": "easy",      "work_min": 15}},
}

_PLAN_BY_PHASE = {1: _PLAN_PHASE1, 2: _PLAN_PHASE2, 3: _PLAN_PHASE3}

# Expose current phase 1 plan as _PLAN for calendar_generator import
_PLAN = _PLAN_PHASE1

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


def _deload_blocks() -> list:
    return [
        {"name": "Warmup",   "duration_min": _WARMUP_MIN,  "zone": "zone1",
         "notes": "Slow walk or very light jog."},
        {"name": "Work",     "duration_min": 10,            "zone": "zone1",
         "notes": "Very easy — this is active recovery, not a workout. Stay well below 130 bpm."},
        {"name": "Cooldown", "duration_min": _COOLDOWN_MIN, "zone": "zone1",
         "notes": "Easy walk to finish."},
    ]


# ── KB Breathing Ladder ───────────────────────────────────────────────────────

def kb_peak_from_weeks(weeks_elapsed: int) -> int:
    if weeks_elapsed < 3:
        return 10
    elif weeks_elapsed < 6:
        return 15
    return 20


def _kb_ladder_blocks(peak_rung: int, decision: str, bell_reset: bool = False) -> list:
    if decision in ("DELOAD", "SUPPRESS"):
        return []
    effective = max(5, peak_rung - 2) if decision == "REDUCE" else peak_rung
    label = f"Peak {effective}"
    if decision == "REDUCE":
        label += f" (reduced from {peak_rung})"
    notes = (
        f"{label} — ladder 1→{effective}→1. "
        f"1 breath per swing as rest. Fixed bell weight. {effective ** 2} total swings."
    )
    if bell_reset:
        notes += " Time to move up a bell weight for this new cycle."
    return [{"name": "KB Breathing Ladder", "duration_min": 15, "notes": notes}]


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
    "REDUCE":   "Pull back — 80% of planned load.",
    "DELOAD":   "Easy load only — deload week.",
    "SUPPRESS": "Easy load only.",
}

_STRENGTH_NOTES = {
    "BUILD":    "Recovery looks strong — lift at full planned load.",
    "HOLD":     "Follow planned load.",
    "REDUCE":   "Back off — work at roughly 80% of planned load.",
    "DELOAD":   "Deload week — keep loads light, cut sets if needed.",
    "SUPPRESS": "Skip if feeling rough. If you lift, keep it very easy.",
}

_DAY_LABEL = {
    "mon": "Lower Body",
    "wed": "Upper Body + KB Ladder",
    "fri": "Full Body",
}


def generate_strength_session(decision: str, day: str, bell_reset: bool = False) -> dict:
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    label = _DAY_LABEL.get(day, "Strength")
    summary = (
        f"{_STRENGTH_PREFIX.get(decision, '')}\U0001f3cb️ {label} "
        f"— {_STRENGTH_PHRASE.get(decision, 'Follow the plan.')}"
    )
    strength_name = label.split(" + ")[0]
    blocks = [{"name": strength_name, "notes": _STRENGTH_NOTES.get(decision, "Follow planned load.")}]
    if day == "wed":
        peak = kb_peak_from_weeks(plan_state.get("kb_weeks_elapsed", 0))
        blocks += _kb_ladder_blocks(peak, decision, bell_reset=bell_reset)
    return {
        "session_id": str(uuid.uuid4()),
        "date": date.today().isoformat(),
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
    elif session_type == "deload":
        return _deload_blocks()
    return _easy_blocks(work_min)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_session(decision: str, data: dict) -> dict:
    """
    Build a session dict from the rule decision and current plan state.

    Args:
        decision: SUPPRESS | DELOAD | REDUCE | HOLD | BUILD
        data:     The full normalised HealthKit JSON body.

    Returns:
        Session dict with session_id, date, type, rule_fired, flag, summary, blocks.
    """
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    current_week = plan_state.get("current_week", 1)
    phase = plan_state.get("phase", 1)

    # Slot is fixed by calendar day: Tuesday (weekday 1) = A, Saturday (weekday 5) = B
    slot = "A" if date.today().weekday() == 1 else "B"

    plan_table = _PLAN_BY_PHASE.get(phase, _PLAN_PHASE1)
    week_plan = plan_table.get(current_week, plan_table[1])
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
        session_type = "deload"
        blocks = _deload_blocks()
        summary = (
            f"Deload run — {_total_min(blocks)} min total. "
            "Zone 1 only. Let the training from the past three weeks settle in."
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
        "date": date.today().isoformat(),
        "type": session_type,
        "rule_fired": decision,
        "flag": "none",
        "week": current_week,
        "slot": slot,
        "phase": phase,
        "summary": summary,
        "blocks": blocks,
    }
