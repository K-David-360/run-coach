"""
calendar_generator.py — Builds the rolling ICS training calendar.

Fixed weekly schedule (Mon–Sun):
  Mon  🏋️ Push (+ jumps)
  Tue  🏃‍♂️ Run 1 (Slot A)
  Wed  🏋️ Pull (+ jumps)
  Thu  Rest
  Fri  🏋️ Full (+ jumps)
  Sat  🏃‍♂️ Run 2 (Slot B)
  Sun  Rest

The plan runs in 6-week cycles (cycle.py): week 6 is a deload. Deload weeks
keep all three lift days, prefixed ⛔️, at same weight / half the sets, no jumps.
The window always reaches the next deload (minimum 4 weeks).
Decision emoji prefixes: ⬆️ BUILD · ⬇️ REDUCE · ⛔️ SUPPRESS/DELOAD · (none) HOLD

Today's strength event also gets a set/load guidance line appended to its
description (from plan_generator._STRENGTH_NOTES) for every non-HOLD decision,
so the calendar spells out how to adjust volume — not just the flag emoji.
"""

from datetime import date, timedelta
from math import ceil

from cycle import DELOAD_EVERY_N_WEEKS, is_deload_week, is_intro_week, jump_prescription, week_in_cycle
from plan_generator import (
    _DAY_LABEL,
    _LIFT_MENU,
    _PLAN_BY_PHASE,
    _STRENGTH_NOTES,
    _STRENGTH_NOTES_INTRO,
    _blocks_for_type,
    _easy_blocks,
    _walk_blocks,
    _total_min,
    jump_line,
    deload_work_min,
    plan_week_for,
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

def _strength_event(day_key: str, rx: dict, is_deload: bool, intro: bool = False) -> dict:
    """Base strength event for a lift day: label, lift menu, jump line, deload note."""
    summary = f"🏋️ {_DAY_LABEL[day_key]}"
    length = "Shorter session: half the sets." if is_deload else "About 45–55 min."
    parts = [length, _LIFT_MENU[day_key], jump_line(rx, intro=intro)]
    if is_deload:
        summary = "⛔️ " + summary
        parts.append(_STRENGTH_NOTES_INTRO if intro else _STRENGTH_NOTES["DELOAD"])
    return {"summary": summary, "description": "\n\n".join(parts)}


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

# Saturday Run B (health-bootcamp protocol): optional, an incline walk is fine instead.
_RUN_B_NOTE = "Optional: an easy Zone 2 run or a 30–45 min incline walk. Skip it if sleep or HRV is down."


def _run_session(plan: dict, plan_week: int, slot: str, is_deload: bool, intro: bool = False) -> dict:
    """Base-plan (HOLD) run event — shown for all future sessions."""
    row  = plan[plan_week_for(plan_week)]
    base = row[slot]
    if is_deload:
        # Deload: ~70% of the last build week, Zone 2 easy (Galpin protocol);
        # interval slots have no work_min, so use the same week's easy run.
        blocks  = _easy_blocks(deload_work_min(base["work_min"] or row["A"]["work_min"]))
        label   = "Intro Week Run" if intro else "Deload Run"
        summary = f"⛔️ 🏃‍♂️ {label} — {_total_min(blocks)} mins"
    else:
        blocks   = _blocks_for_type(base["type"], base["work_min"] or 18)
        label    = _SESSION_LABEL.get(base["type"], "Easy Run")
        summary  = f"🏃‍♂️ {label} — {_total_min(blocks)} mins"

    return {"summary": summary, "description": _format_run_description(blocks)}


def _run_session_actual(plan: dict, session_type: str, decision: str, plan_week: int, slot: str,
                        intro: bool = False) -> dict:
    """Today's run event — uses the real rule engine decision."""
    prefix = _DECISION_EMOJI.get(decision, "")
    row  = plan[plan_week_for(plan_week)]
    base = row[slot]
    base_work_min = base["work_min"] or 18

    if decision == "SUPPRESS":
        work_min = max(8, base_work_min - 5)
        blocks   = _walk_blocks(work_min)
        summary  = f"{prefix}🚶 Recovery Walk — {_total_min(blocks)} mins"
    elif decision == "DELOAD":
        work_min = deload_work_min(base["work_min"] or row["A"]["work_min"])
        blocks   = _easy_blocks(work_min)
        label    = "Intro Week Run" if intro else "Deload Run"
        summary  = f"{prefix}🏃‍♂️ {label} — {_total_min(blocks)} mins"
    elif decision == "REDUCE" and base["type"] == "intervals":
        # Mirrors generate_session: intervals can't be trimmed, so swap to easy.
        blocks   = _easy_blocks(max(10, round(20 * 0.85)))
        summary  = f"{prefix}🏃‍♂️ Easy Run — {_total_min(blocks)} mins"
    else:
        if decision == "REDUCE":
            work_min = max(8, ceil(base_work_min * 0.85))
        elif decision == "BUILD":
            work_min = ceil(base_work_min * 1.10)
        else:
            work_min = base_work_min
        blocks   = _blocks_for_type(base["type"], work_min)
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


def generate_ics(plan_state: dict, today: date = None, skip_jumps_dates=None) -> str:
    """skip_jumps_dates: lift days whose jump line reads "skip this week" (S1 week; no reason shown)."""
    skip_jumps_dates = skip_jumps_dates or set()
    if today is None:
        today = date.today()
    cycle_start  = plan_state.get("cycle_start_date", "")
    phase        = plan_state.get("phase", 1)
    plan         = _PLAN_BY_PHASE.get(phase, _PLAN_BY_PHASE[1])
    # Always show through the next deload week, minimum 4 weeks.
    this_week     = week_in_cycle(cycle_start, today)
    weeks_to_show = max(4, DELOAD_EVERY_N_WEEKS - this_week + 1)

    last_execution_type     = plan_state.get("last_execution_type", "")
    last_execution_date     = plan_state.get("last_execution_date", "")
    last_execution_decision = plan_state.get("last_execution_decision", "")

    last_run_a_execution_date = plan_state.get("last_run_a_execution_date", "")
    last_run_a_decision       = plan_state.get("last_run_a_decision", "")
    last_run_b_execution_date = plan_state.get("last_run_b_execution_date", "")
    last_run_b_decision       = plan_state.get("last_run_b_decision", "")

    # Anchor to this week's Monday so restarting mid-week doesn't lose current week.
    monday = today - timedelta(days=today.weekday())

    # LTHR field test: date is fixed once by server.py when total_runs first
    # crosses 10 (and bumped once more at 14). Read it as-is — recomputing it
    # relative to "today" here would make it slide forward every calendar
    # push and never arrive.
    lthr_date = None
    lthr_test_date_str = plan_state.get("lthr_test_date", "")
    if phase == 1 and lthr_test_date_str:
        lthr_date = date.fromisoformat(lthr_test_date_str)

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
        plan_week   = week_in_cycle(cycle_start, week_monday)
        is_deload   = is_deload_week(plan_week)
        intro       = is_intro_week(cycle_start, week_monday)
        rx          = jump_prescription(cycle_start, week_monday)

        mon_date = week_monday
        tue_date = week_monday + timedelta(days=1)
        wed_date = week_monday + timedelta(days=2)
        fri_date = week_monday + timedelta(days=4)
        sat_date = week_monday + timedelta(days=5)

        # ── Strength events ───────────────────────────────────────────────────
        for day_key, evt_date in [("mon", mon_date), ("wed", wed_date), ("fri", fri_date)]:
            s   = _strength_event(day_key, rx, is_deload, intro)
            if evt_date in skip_jumps_dates and rx["sets"] > 0:
                s["description"] = s["description"].replace(jump_line(rx), "Jumps: skip this week.")
            guidance = ""
            # Apply live decision emoji + set/load guidance when this event
            # matches the last execution date.
            if evt_date.isoformat() == last_execution_date and last_execution_decision:
                prefix = _DECISION_EMOJI.get(last_execution_decision, "")
                if prefix and not s["summary"].startswith(prefix):
                    s["summary"] = prefix + s["summary"]
                # Spell out how to adjust sets/load for today. HOLD needs no
                # callout; scheduled deload weeks already carry the wording.
                if plan_state.get("last_execution_skip_jumps") and rx["sets"] > 0:
                    s["description"] = s["description"].replace(jump_line(rx), "Jumps: skip today.")
                note = _STRENGTH_NOTES.get(last_execution_decision, "")
                if last_execution_decision == "SUPPRESS":
                    # Matches the session: no lifting, so no lift menu or jumps.
                    s["description"] = f"{prefix}{note}"
                elif note and last_execution_decision != "HOLD" and not is_deload:
                    guidance = f"\n\n{prefix}{note}"
            s["description"] += guidance
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
            else:
                # Pick slot-specific execution date and decision
                if slot == "A":
                    slot_exec_date = last_run_a_execution_date
                    slot_decision  = last_run_a_decision
                else:
                    slot_exec_date = last_run_b_execution_date
                    slot_decision  = last_run_b_decision

                is_today = run_date.isoformat() == slot_exec_date and bool(slot_decision)
                if is_today:
                    session = _run_session_actual(
                        plan, last_execution_type, slot_decision, plan_week, slot, intro
                    )
                else:
                    session = _run_session(plan, plan_week, slot, is_deload, intro)
                # Not on a SUPPRESS day: that's already a walk, and the note offers a run.
                if slot == "B" and not (is_today and slot_decision == "SUPPRESS"):
                    session["description"] += "\n\n" + _RUN_B_NOTE
                for line in _vevent(run_date, session["summary"], session["description"], uid):
                    raw_lines.append(_fold(line))

    raw_lines.append("END:VCALENDAR")
    return "\r\n".join(raw_lines)
