"""
calendar_generator.py — Builds a rolling 4-week ICS calendar.

Fixed weekly schedule (Mon–Sun):
  Mon  🏋️ Lower Body
  Tue  🏃‍♂️ Run 1 (Slot A)
  Wed  🏋️ Upper Body + Core
  Thu  Rest
  Fri  🏋️ Full Body
  Sat  🏃‍♂️ Run 2 (Slot B)
  Sun  Rest

Week 4 (deload): strength labels change; no lower body, no Friday session.
Decision emoji prefixes: ⬆️ BUILD · ⬇️ REDUCE · ⛔️ SUPPRESS/DELOAD · (none) HOLD
"""

from datetime import date, timedelta
from math import ceil

from plan_generator import (
    _PLAN_PHASE1 as _PLAN,
    _easy_blocks,
    _deload_blocks,
    _total_min,
    kb_peak_from_weeks,
)

# ── Decision emoji prefix ─────────────────────────────────────────────────────

_DECISION_EMOJI = {
    "BUILD":    "⬆️ ",
    "REDUCE":   "⬇️ ",
    "SUPPRESS": "⛔️ ",
    "DELOAD":   "⛔️ ",
    "HOLD":     "",
}

_SESSION_LABEL = {
    "easy":        "Easy Run",
    "progression": "Progression Run",
    "tempo":       "Tempo Run",
    "intervals":   "Interval Session",
    "deload":      "Deload Run",
}

# ── Strength session definitions ──────────────────────────────────────────────

_STRENGTH_NORMAL = {
    "mon": {
        "summary":     "🏋️ Lower Body",
        "description": "Squats, deadlifts, lunges, glutes.\nHeavy lower body — rest or mobility tomorrow.",
    },
    "wed": {
        "summary":     "🏋️ Upper Body + KB Ladder",
        "description": "Upper body and core only.\nNo leg work — protect running legs for Saturday.",
    },
    "fri": {
        "summary":     "🏋️ Full Body",
        "description": "Full body session.\nBalance push/pull and a lower body movement.",
    },
}

_STRENGTH_DELOAD = {
    "mon": {
        "summary":     "⛔️ 🏋️ Full Body",
        "description": "Deload week: full body only, no lower body work.\nShort session, reduced load.",
    },
    "wed": {
        "summary":     "⛔️ 🏋️ Upper Body + KB Ladder",
        "description": "Deload week: upper body at reduced load. Keep it easy.",
    },
    # No Friday session during deload
}


# ── Description formatter ─────────────────────────────────────────────────────

def _format_run_description(blocks: list) -> str:
    """
    Render blocks as natural language mirroring an Apple Watch custom workout.
    Unit follows the session type: time for easy/deload, distance for intervals.
    """
    warmup_lines = []
    work_lines   = []
    cool_lines   = []

    for b in blocks:
        name = b.get("name", "")
        zone = b.get("zone", "")
        dur  = b.get("duration_min")
        dist = b.get("distance_m")

        if name == "Warmup":
            warmup_lines.append(f"{int(dur)} mins walking warm up")

        elif name == "Cooldown":
            cool_lines.append(f"{int(dur)} mins walking cool down")

        elif zone == "rest":
            secs = int(dur * 60)
            work_lines.append(f"{secs} secs walking")

        elif dist:
            mi = round(dist / 1609.34, 2)
            work_lines.append(f"{mi}mi in Zone {zone[-1]}")

        elif dur:
            mins = int(dur)
            if zone == "zone1":
                work_lines.append(f"{mins} mins in Zone 1")
            elif zone == "zone2":
                work_lines.append(f"{mins} mins in Zone 2")
            elif zone == "zone3":
                work_lines.append(f"{mins} mins in Zone 3")
            elif zone == "zone4":
                work_lines.append(f"{mins} mins in Zone 4")

    sections = []
    if warmup_lines:
        sections.append("\n".join(warmup_lines))
    if work_lines:
        sections.append("\n".join(work_lines))
    if cool_lines:
        sections.append("\n".join(cool_lines))

    return "\n\n".join(sections)


# ── Run session builders ──────────────────────────────────────────────────────

def _run_session(plan_week: int, slot: str, is_deload: bool) -> dict:
    """Base-plan (HOLD) run event — shown for all future sessions."""
    if is_deload:
        blocks  = _deload_blocks()
        summary = f"⛔️ 🏃‍♂️ Deload Run — {_total_min(blocks)} mins"
    else:
        base     = _PLAN.get(plan_week, _PLAN[1])[slot]
        blocks   = _easy_blocks(base["work_min"] or 18)
        label    = _SESSION_LABEL.get(base["type"], "Easy Run")
        summary  = f"🏃‍♂️ {label} — {_total_min(blocks)} mins"

    return {"summary": summary, "description": _format_run_description(blocks)}


def _run_session_actual(session_type: str, decision: str, plan_week: int, slot: str) -> dict:
    """Today's run event — uses the real rule engine decision."""
    prefix = _DECISION_EMOJI.get(decision, "")
    base = _PLAN.get(plan_week, _PLAN[1])[slot]
    base_work_min = base["work_min"] or 18

    if decision in ("DELOAD", "SUPPRESS"):
        blocks   = _deload_blocks()
        label    = "Recovery Only" if decision == "SUPPRESS" else "Deload Run"
        summary  = f"{prefix}🏃‍♂️ {label} — {_total_min(blocks)} mins"
    else:
        if decision == "REDUCE":
            work_min = max(8, ceil(base_work_min * 0.85))
        elif decision == "BUILD":
            work_min = ceil(base_work_min * 1.10)
        else:
            work_min = base_work_min
        blocks   = _easy_blocks(work_min)
        label    = _SESSION_LABEL.get(base["type"], "Easy Run")
        summary  = f"{prefix}🏃‍♂️ {label} — {_total_min(blocks)} mins"
    return {"summary": summary, "description": _format_run_description(blocks)}


# ── ICS helpers ───────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold ICS lines longer than 75 octets (RFC 5545 §3.1)."""
    if len(line.encode()) <= 75:
        return line
    result = []
    while len(line.encode()) > 75:
        cut = 75
        while len(line[:cut].encode()) > 75:
            cut -= 1
        result.append(line[:cut])
        line = " " + line[cut:]
    result.append(line)
    return "\r\n".join(result)


def _vevent(evt_date: date, summary: str, description: str, uid: str) -> list:
    dtstart = evt_date.strftime("%Y%m%d")
    dtend   = (evt_date + timedelta(days=1)).strftime("%Y%m%d")
    return [
        "BEGIN:VEVENT",
        f"DTSTART;VALUE=DATE:{dtstart}",
        f"DTEND;VALUE=DATE:{dtend}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"UID:{uid}",
        "END:VEVENT",
    ]


# ── Main generator ────────────────────────────────────────────────────────────

_LTHR_DESCRIPTION = (
    "Replaces today's Run 2.\n\n"
    "10 mins walking warm up\n\n"
    "30 mins all-out sustained effort\n"
    "(hardest pace you can hold for the full 30 mins — not a sprint)\n\n"
    "5 mins walking cool down\n\n"
    "After: note your average HR for the final 20 mins.\n"
    "That number is your LTHR.\n\n"
    "Next steps:\n"
    "1. Recalculate zone boundaries from the new LTHR\n"
    "2. Update Apple Watch custom zone breakpoints\n"
    '3. Set "phase": 2 in data/plan_state.json'
)


def generate_ics(plan_state: dict) -> str:
    today        = date.today()
    current_week = plan_state.get("current_week", 1)
    total_runs   = plan_state.get("total_runs", 0)
    phase        = plan_state.get("phase", 1)
    kb_weeks     = plan_state.get("kb_weeks_elapsed", 0)
    kb_peak      = kb_peak_from_weeks(kb_weeks)
    # Show full KB Phase 1 arc — shrinks as the phase progresses, min 4 weeks
    weeks_to_show = max(4, 9 - kb_weeks)

    last_execution_date     = plan_state.get("last_execution_date", "")
    last_execution_type     = plan_state.get("last_execution_type", "")
    last_execution_decision = plan_state.get("last_execution_decision", "")

    # Anchor to this week's Monday so restarting mid-week doesn't lose current week.
    monday = today - timedelta(days=today.weekday())

    # LTHR field test: show on an upcoming Saturday once 10 runs are done.
    # Urgent (>= 14 runs): next Saturday. Approaching: Saturday after that.
    lthr_date = None
    if phase == 1 and total_runs >= 10:
        lthr_week_offset = 1 if total_runs >= 14 else 2
        lthr_date = monday + timedelta(weeks=lthr_week_offset, days=5)

    raw_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Run Coach//Run Coach//EN",
        "X-WR-CALNAME:Run Coach",
        "X-WR-CALDESC:Your personalised running and strength plan",
        "CALSCALE:GREGORIAN",
    ]

    for week_offset in range(weeks_to_show):
        week_monday = monday + timedelta(weeks=week_offset)
        plan_week   = ((current_week - 1 + week_offset) % 4) + 1
        is_deload   = plan_week == 4

        mon_date = week_monday
        tue_date = week_monday + timedelta(days=1)
        wed_date = week_monday + timedelta(days=2)
        fri_date = week_monday + timedelta(days=4)
        sat_date = week_monday + timedelta(days=5)

        # ── Strength events ───────────────────────────────────────────────────
        strength_schedule = _STRENGTH_DELOAD if is_deload else _STRENGTH_NORMAL
        for day_key, evt_date in [("mon", mon_date), ("wed", wed_date), ("fri", fri_date)]:
            if day_key not in strength_schedule:
                continue
            s   = dict(strength_schedule[day_key])  # shallow copy — don't mutate module dict
            if day_key == "wed":
                if is_deload:
                    s["description"] += "\n\nKB Swings — omitted (deload week)."
                else:
                    s["description"] += (
                        f"\n\nKB Breathing Ladder — Peak {kb_peak}\n"
                        f"1→{kb_peak}→1 swings. 1 breath per swing as rest. Fixed bell weight."
                    )
            uid = f"rc-strength-{evt_date.isoformat()}-{day_key}@runcoach"
            for line in _vevent(evt_date, s["summary"], s["description"], uid):
                raw_lines.append(_fold(line))

        # ── Run events ────────────────────────────────────────────────────────
        for slot, run_date in [("A", tue_date), ("B", sat_date)]:
            uid = f"rc-run-{run_date.isoformat()}-{slot}@runcoach"

            if slot == "B" and lthr_date and run_date == lthr_date:
                uid = f"rc-lthr-{run_date.isoformat()}@runcoach"
                for line in _vevent(run_date, "🔬 LTHR Field Test", _LTHR_DESCRIPTION, uid):
                    raw_lines.append(_fold(line))
            elif run_date.isoformat() == last_execution_date and last_execution_decision:
                session = _run_session_actual(
                    last_execution_type, last_execution_decision, plan_week, slot
                )
                for line in _vevent(run_date, session["summary"], session["description"], uid):
                    raw_lines.append(_fold(line))
            else:
                session = _run_session(plan_week, slot, is_deload)
                for line in _vevent(run_date, session["summary"], session["description"], uid):
                    raw_lines.append(_fold(line))

    raw_lines.append("END:VCALENDAR")
    return "\r\n".join(raw_lines)
