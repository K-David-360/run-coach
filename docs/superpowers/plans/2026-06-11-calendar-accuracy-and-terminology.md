# Calendar Accuracy & Terminology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix calendar events reflecting wrong decisions, add sleep diagnostics for Shortcut debugging, and rename variables to match the "execution vs. running workout" terminology convention.

**Architecture:** Three independent but overlapping changes to `server.py` and `calendar_generator.py`: (1) add sleep values to the debug response for Phase 1 instrumentation, (2) store per-slot run execution decisions separately in `plan_state.json` so Tuesday's decision survives Wednesday's execution, (3) apply the live decision to strength calendar events (not just run events). All variable renames happen in the same pass to avoid touching files twice.

**Tech Stack:** Python 3, Flask, pytest. No new dependencies.

---

## Terminology Convention (READ FIRST)

This codebase distinguishes two concepts that must never be conflated:

| Concept | Term to use | Examples |
|---------|-------------|---------|
| A Zone 2 / interval / deload run that the user physically does | **running workout** | "today's running workout", "Run A slot" |
| Tuesday or Saturday calendar slot (regardless of whether a running workout happened) | **run day** | "run day", "run day execution" |
| The Shortcut firing and the server processing it | **execution** or **daily execution** | "last execution", "execution date" |
| Date/decision stored from the last execution | **last execution date/decision** | `last_execution_date`, `last_execution_decision` |
| `total_runs` counter | **run day execution count** | tracks how many times the server fired on a Tue/Sat, NOT running workouts done |

Apply these names to all new variables and all renamed variables below.

---

## Files Modified

| File | Change |
|------|--------|
| `server.py` | Add sleep to debug; rename `last_session_*` → `last_execution_*`; add `last_run_a/b_execution_date/decision` fields; set them on Tue/Sat |
| `calendar_generator.py` | Use per-slot fields for run events; apply live decision to strength events |
| `data/plan_state.json` | Add new fields (manual migration — no migration script needed, fields default to `""`) |
| `reset.py` | Add new fields to `_DEFAULT_PLAN_STATE` |
| `tests/test_calendar_accuracy.py` | New test file |
| Memory file | New terminology memory |

---

## Task 1: Add Sleep Values to Debug Response (Diagnostic Instrumentation)

**Purpose:** Phase 1 of systematic debugging — confirm exactly what values the server received from the Shortcut. This is NOT a fix; it's evidence gathering.

**Files:**
- Modify: `server.py` (both `/healthkit` strength-day and run-day response blocks)

- [ ] **Step 1: Add `sleep_total_hrs` and `sleep_deep_hrs` to every debug dict in `/healthkit`**

In `server.py`, there are three places that return a debug dict. Add the two sleep fields to all three.

Strength-day response (around line 512):
```python
"debug": {
    "rest_day":            False,
    "hrv_ratio":           round(hrv_ratio, 3),
    "hrv_7d_avg":          round(hrv_7d_avg, 1),
    "resting_hr":          resting_hr,
    "sleep_total_hrs":     sleep_total_hrs,   # ADD
    "sleep_deep_hrs":      sleep_deep_hrs,    # ADD
    "load_classification": load_classification,
    "decision":            decision["decision"],
},
```

Rest-day run response (around line 540):
```python
"debug": {
    "rest_day":            True,
    "hrv_ratio":           round(hrv_ratio, 3),
    "hrv_7d_avg":          round(hrv_7d_avg, 1),
    "resting_hr":          resting_hr,
    "sleep_total_hrs":     sleep_total_hrs,   # ADD
    "sleep_deep_hrs":      sleep_deep_hrs,    # ADD
    "load_classification": load_classification,
    "decision":            decision["decision"],
    "last_workout_date":   last_workout_date,
},
```

New-workout run response (around line 574):
```python
"debug": {
    "rest_day":            False,
    "hrv_ratio":           round(hrv_ratio, 3),
    "hrv_7d_avg":          round(hrv_7d_avg, 1),
    "resting_hr":          resting_hr,
    "sleep_total_hrs":     sleep_total_hrs,   # ADD
    "sleep_deep_hrs":      sleep_deep_hrs,    # ADD
    "load_classification": load_classification,
    "decision":            decision["decision"],
    "last_workout_date":   last_workout_date,
},
```

- [ ] **Step 2: Verify server starts without error**

```bash
cd /Users/David/Documents/Claude/run-coach
python3 -c "from server import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Smoke-test the debug fields appear**

```bash
curl -s -X POST http://localhost:5001/healthkit \
  -H "Content-Type: application/json" \
  -d '{"hrv_last_night":60,"sleep_total_hrs":7.5,"sleep_deep_hrs":1.2,"load_pct":0}' \
  | python3 -m json.tool | grep -A2 '"sleep'
```
Expected output contains:
```
"sleep_total_hrs": 7.5,
"sleep_deep_hrs": 1.2,
```

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat: add sleep_total_hrs and sleep_deep_hrs to debug response

Diagnostic instrumentation to verify what values the server receives
from the Shortcut — needed to root-cause incorrect sleep readings."
```

---

## Task 2: Rename Variables to Match Terminology Convention

**Purpose:** Rename `last_session_*` to `last_execution_*` throughout. `total_runs` is left as-is (it's persisted in Pi's plan_state.json and is a minor rename with high migration risk) but its meaning is documented.

**Files:**
- Modify: `server.py`
- Modify: `calendar_generator.py`
- Modify: `reset.py`

- [ ] **Step 1: Rename in `server.py` — `_DEFAULT_PLAN_STATE` dict**

```python
_DEFAULT_PLAN_STATE = {
    "current_week":                1,
    "cycle_start_date":            "",
    "consecutive_suppress":        0,
    "total_runs":                  0,   # count of run-day executions (Tue/Sat), NOT running workouts done
    "phase":                       1,
    "last_processed_workout_date": "",
    "last_execution_date":         "",  # renamed from last_session_date
    "last_execution_type":         "",  # renamed from last_session_type
    "last_execution_decision":     "",  # renamed from last_session_decision
    "kb_weeks_elapsed":            0,
    "kb_peak_rung":                10,
}
```

- [ ] **Step 2: Rename all usages in `server.py`**

Replace every occurrence:
- `last_session_date` → `last_execution_date`
- `last_session_type` → `last_execution_type`
- `last_session_decision` → `last_execution_decision`

There are approximately 10 occurrences spread across the strength-day block, rest-day run block, and new-workout block.

- [ ] **Step 3: Rename in `calendar_generator.py`**

```python
last_execution_date     = plan_state.get("last_execution_date", "")
last_execution_type     = plan_state.get("last_execution_type", "")
last_execution_decision = plan_state.get("last_execution_decision", "")
```

Replace all references to the old names throughout `generate_ics`.

- [ ] **Step 4: Rename in `reset.py`**

In the `_DEFAULT_PLAN_STATE` dict inside `reset.py`, apply the same renames as Step 1.

- [ ] **Step 5: Run existing tests to confirm no regressions**

```bash
cd /Users/David/Documents/Claude/run-coach
python3 -m pytest tests/test_week_logic.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add server.py calendar_generator.py reset.py
git commit -m "refactor: rename last_session_* to last_execution_* for terminology clarity

Distinguishes Shortcut/script executions from running workouts.
total_runs tracks run-day executions (Tue/Sat fires), not actual
running workouts completed."
```

---

## Task 3: Add Per-Slot Run Execution Tracking to plan_state

**Purpose:** Store Tuesday's decision separately from Saturday's so each survives the other day's execution. Currently a single `last_execution_date` is overwritten daily, erasing yesterday's run-day decision from the calendar.

**Files:**
- Modify: `server.py`
- Modify: `reset.py`
- Modify: `data/plan_state.json` (manual — add fields)
- Create: `tests/test_calendar_accuracy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_calendar_accuracy.py`:

```python
# tests/test_calendar_accuracy.py
"""
Tests for calendar accuracy: per-slot run execution decisions and
strength-day decision display.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from calendar_generator import generate_ics


def _base_plan_state(**overrides):
    state = {
        "current_week":                1,
        "cycle_start_date":            "2026-06-08",   # Monday
        "consecutive_suppress":        0,
        "total_runs":                  0,
        "phase":                       1,
        "last_execution_date":         "",
        "last_execution_type":         "",
        "last_execution_decision":     "",
        "last_run_a_execution_date":   "",
        "last_run_a_decision":         "",
        "last_run_b_execution_date":   "",
        "last_run_b_decision":         "",
        "kb_weeks_elapsed":            0,
        "kb_peak_rung":                10,
    }
    state.update(overrides)
    return state


def _events_on(ics: str, date_str: str) -> list[str]:
    """Return all SUMMARY lines for events on the given date."""
    lines = ics.splitlines()
    summaries = []
    in_event = False
    event_date = None
    summary = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            event_date = None
            summary = None
        elif line == "END:VEVENT":
            if in_event and event_date == date_str and summary:
                summaries.append(summary)
            in_event = False
        elif in_event and line.startswith("DTSTART;VALUE=DATE:"):
            event_date = line.split(":")[1].strip()
        elif in_event and line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):]
    return summaries


def test_run_a_decision_visible_after_tuesday_execution():
    """Tuesday's REDUCE decision should appear in the calendar as ⬇️."""
    state = _base_plan_state(
        last_run_a_execution_date="2026-06-09",  # Tuesday
        last_run_a_decision="REDUCE",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, "20260609")
    assert any("⬇️" in s for s in summaries), f"Expected ⬇️ in Tue summary, got: {summaries}"


def test_run_b_decision_visible_after_saturday_execution():
    """Saturday's BUILD decision should appear in the calendar as ⬆️."""
    state = _base_plan_state(
        last_run_b_execution_date="2026-06-13",  # Saturday
        last_run_b_decision="BUILD",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, "20260613")
    assert any("⬆️" in s for s in summaries), f"Expected ⬆️ in Sat summary, got: {summaries}"


def test_tuesday_decision_survives_wednesday_execution():
    """After Wednesday fires, Tuesday's run decision must still show in calendar."""
    state = _base_plan_state(
        last_run_a_execution_date="2026-06-09",  # Tuesday
        last_run_a_decision="REDUCE",
        last_execution_date="2026-06-10",        # Wednesday overwrote last_execution_date
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    tue_summaries = _events_on(ics, "20260609")
    assert any("⬇️" in s for s in tue_summaries), (
        f"Tuesday decision lost after Wed execution. Got: {tue_summaries}"
    )
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd /Users/David/Documents/Claude/run-coach
python3 -m pytest tests/test_calendar_accuracy.py -v
```
Expected: 3 failures (KeyError or assertion failures — new plan_state fields don't exist yet).

- [ ] **Step 3: Add new fields to `_DEFAULT_PLAN_STATE` in `server.py`**

```python
_DEFAULT_PLAN_STATE = {
    "current_week":                1,
    "cycle_start_date":            "",
    "consecutive_suppress":        0,
    "total_runs":                  0,
    "phase":                       1,
    "last_processed_workout_date": "",
    "last_execution_date":         "",
    "last_execution_type":         "",
    "last_execution_decision":     "",
    "last_run_a_execution_date":   "",   # ADD: date of last Tuesday execution
    "last_run_a_decision":         "",   # ADD: decision from last Tuesday execution
    "last_run_b_execution_date":   "",   # ADD: date of last Saturday execution
    "last_run_b_decision":         "",   # ADD: decision from last Saturday execution
    "kb_weeks_elapsed":            0,
    "kb_peak_rung":                10,
}
```

- [ ] **Step 4: Set per-slot fields when run days execute in `server.py`**

In the run-day section of `/healthkit`, after `session = generate_session(...)`, both the `is_rest_day` path and the new-workout path currently set `last_execution_date`. Add slot-specific assignments.

The run slot is determined by `today_dow`: Tuesday = 1 (slot A), Saturday = 5 (slot B).

In both the `is_rest_day` block and the new-workout block, add:
```python
if today_dow == 1:   # Tuesday → slot A
    plan_state["last_run_a_execution_date"] = today_str
    plan_state["last_run_a_decision"]       = decision["decision"]
elif today_dow == 5:  # Saturday → slot B
    plan_state["last_run_b_execution_date"] = today_str
    plan_state["last_run_b_decision"]       = decision["decision"]
```

- [ ] **Step 5: Add new fields to `reset.py`**

In `reset.py`'s `_DEFAULT_PLAN_STATE` (or wherever plan_state defaults are set), add:
```python
"last_run_a_execution_date": "",
"last_run_a_decision":       "",
"last_run_b_execution_date": "",
"last_run_b_decision":       "",
```

- [ ] **Step 6: Update `data/plan_state.json` manually**

Add the four new fields to the existing JSON (Pi will get these on next deploy):
```json
"last_run_a_execution_date": "",
"last_run_a_decision":       "",
"last_run_b_execution_date": "",
"last_run_b_decision":       ""
```

---

## Task 4: Fix Calendar — Run Events Use Per-Slot Tracking

**Purpose:** `generate_ics` currently uses the single `last_execution_date` for run events. Switch it to use slot-specific fields.

**Files:**
- Modify: `calendar_generator.py`

- [ ] **Step 1: Read new fields from plan_state in `generate_ics`**

Replace:
```python
last_execution_date     = plan_state.get("last_execution_date", "")
last_execution_type     = plan_state.get("last_execution_type", "")
last_execution_decision = plan_state.get("last_execution_decision", "")
```

With:
```python
last_execution_date       = plan_state.get("last_execution_date", "")
last_execution_decision   = plan_state.get("last_execution_decision", "")
last_run_a_execution_date = plan_state.get("last_run_a_execution_date", "")
last_run_a_decision       = plan_state.get("last_run_a_decision", "")
last_run_b_execution_date = plan_state.get("last_run_b_execution_date", "")
last_run_b_decision       = plan_state.get("last_run_b_decision", "")
```

(`last_execution_type` is still used for strength events — keep it.)

- [ ] **Step 2: Use slot-specific dates/decisions for run events**

In the run events loop (around line 288), replace the condition that checks `last_execution_date` with slot-specific checks:

```python
for slot, run_date in [("A", tue_date), ("B", sat_date)]:
    uid = f"rc-run-{run_date.isoformat()}-{slot}@runcoach"

    if slot == "B" and lthr_date and run_date == lthr_date:
        uid = f"rc-lthr-{run_date.isoformat()}@runcoach"
        for line in _vevent(run_date, "🔬 LTHR Field Test", _LTHR_DESCRIPTION, uid):
            raw_lines.append(_fold(line))
    else:
        # Use slot-specific execution decision if available for this date
        if slot == "A":
            slot_date     = last_run_a_execution_date
            slot_decision = last_run_a_decision
        else:
            slot_date     = last_run_b_execution_date
            slot_decision = last_run_b_decision

        if run_date.isoformat() == slot_date and slot_decision:
            session = _run_session_actual(
                "",  # session_type unused in this function
                slot_decision,
                plan_week,
                slot,
            )
            for line in _vevent(run_date, session["summary"], session["description"], uid):
                raw_lines.append(_fold(line))
        else:
            session = _run_session(plan_week, slot, is_deload)
            for line in _vevent(run_date, session["summary"], session["description"], uid):
                raw_lines.append(_fold(line))
```

Note: `_run_session_actual` takes `session_type` as first arg but doesn't use it for phase 1 easy runs. Pass `""` for now — it's unused in the current implementation.

- [ ] **Step 3: Run tests**

```bash
cd /Users/David/Documents/Claude/run-coach
python3 -m pytest tests/test_calendar_accuracy.py -v
```
Expected: `test_run_a_decision_visible_after_tuesday_execution` and `test_run_b_decision_visible_after_saturday_execution` pass. `test_tuesday_decision_survives_wednesday_execution` still fails (strength event fix is Task 5).

---

## Task 5: Fix Calendar — Strength Events Apply Live Decision

**Purpose:** When today is a strength day and the decision is DELOAD/SUPPRESS/REDUCE/BUILD, the calendar event for that day should reflect the decision with the appropriate emoji prefix.

**Files:**
- Modify: `calendar_generator.py`
- Modify: `tests/test_calendar_accuracy.py`

- [ ] **Step 1: Add failing test for strength event decision**

Append to `tests/test_calendar_accuracy.py`:

```python
def test_strength_event_shows_deload_decision():
    """Wednesday strength event should show ⛔️ when DELOAD fired on that day."""
    state = _base_plan_state(
        last_execution_date="2026-06-10",      # Wednesday
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    wed_summaries = _events_on(ics, "20260610")
    assert any("⛔️" in s for s in wed_summaries), (
        f"Expected ⛔️ on Wednesday DELOAD, got: {wed_summaries}"
    )


def test_strength_event_shows_reduce_decision():
    """Monday strength event should show ⬇️ when REDUCE fired on that day."""
    state = _base_plan_state(
        last_execution_date="2026-06-08",      # Monday
        last_execution_decision="REDUCE",
    )
    ics = generate_ics(state)
    mon_summaries = _events_on(ics, "20260608")
    assert any("⬇️" in s for s in mon_summaries), (
        f"Expected ⬇️ on Monday REDUCE, got: {mon_summaries}"
    )


def test_tuesday_decision_survives_wednesday_execution():
    """After Wednesday fires, Tuesday's run decision must still show in calendar."""
    state = _base_plan_state(
        last_run_a_execution_date="2026-06-09",
        last_run_a_decision="REDUCE",
        last_execution_date="2026-06-10",
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    tue_summaries = _events_on(ics, "20260609")
    assert any("⬇️" in s for s in tue_summaries), (
        f"Tuesday decision lost after Wed execution. Got: {tue_summaries}"
    )
```

- [ ] **Step 2: Run tests — confirm new tests fail**

```bash
python3 -m pytest tests/test_calendar_accuracy.py::test_strength_event_shows_deload_decision -v
python3 -m pytest tests/test_calendar_accuracy.py::test_strength_event_shows_reduce_decision -v
```
Expected: FAIL.

- [ ] **Step 3: Apply live decision to strength events in `calendar_generator.py`**

In the strength events loop (around line 271), after `s = dict(strength_schedule[day_key])`, add:

```python
# Apply live decision emoji when this event matches the last execution date
if evt_date.isoformat() == last_execution_date and last_execution_decision:
    prefix = _DECISION_EMOJI.get(last_execution_decision, "")
    if prefix and not s["summary"].startswith(prefix):
        s["summary"] = prefix + s["summary"]
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit Tasks 3–5 together**

```bash
git add server.py calendar_generator.py reset.py \
        data/plan_state.json tests/test_calendar_accuracy.py
git commit -m "fix: persist per-slot run decisions and apply live decision to all calendar events

- Store last_run_a/b_execution_date and last_run_a/b_decision in plan_state
  so Tuesday's decision survives Wednesday's execution
- Calendar run events use slot-specific tracking instead of shared last_execution_date
- Strength events now show decision emoji when that day's execution matches"
```

---

## Task 6: Save Terminology Convention to Memory

**Purpose:** Memorialize the execution vs. running-workout terminology so future sessions use it consistently.

- [ ] **Step 1: Write memory file**

Create `/Users/David/.claude/projects/-Users-David-Documents-Claude-run-coach/memory/feedback_terminology.md`:

```markdown
---
name: feedback-terminology
description: Terminology convention distinguishing Shortcut/script executions from running workouts in run-coach
metadata:
  type: feedback
---

Use precise terms to distinguish script executions from running workouts:

| Concept | Term |
|---------|------|
| A physical Zone 2 / interval / deload run the user does | **running workout** |
| Tuesday or Saturday calendar slot | **run day** |
| The Shortcut firing and server processing it | **execution** or **daily execution** |
| Stored date/decision from most recent execution | **last execution date / last execution decision** |
| `total_runs` counter | tracks **run-day executions** (Tue/Sat fires), NOT running workouts completed |

**Why:** The server has zero knowledge of actual workout completion. Decisions are driven by passive health metrics (HRV, sleep, load%). Using "run" or "session" ambiguously caused confusion about what the system tracks.

**How to apply:** In all variable names, comments, CLAUDE.md, and responses — never use "session" or "run" alone when the distinction matters. Always ask: am I talking about when the script fired, or a physical running workout?
```

- [ ] **Step 2: Add pointer to MEMORY.md**

In `/Users/David/.claude/projects/-Users-David-Documents-Claude-run-coach/memory/MEMORY.md`, add the line:
```
- [Terminology: execution vs running workout](feedback_terminology.md) — never conflate Shortcut executions with physical running workouts; use "execution" for the former
```

- [ ] **Step 3: Update CLAUDE.md to reflect new variable names and terminology**

In `CLAUDE.md`, update the `plan_state.json` schema section to show the new fields and add a terminology note.

---

## Task 7: Deploy to Pi

- [ ] **Step 1: Copy changed files to Pi**

```bash
scp /Users/David/Documents/Claude/run-coach/server.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/calendar_generator.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/reset.py pi@192.168.1.136:~/run-coach/
```

- [ ] **Step 2: Migrate plan_state.json on Pi**

SSH in and add the four new fields without disturbing existing state:
```bash
ssh pi@192.168.1.136 'python3 -c "
import json
with open(\"/home/pi/run-coach/data/plan_state.json\") as f:
    s = json.load(f)
s.setdefault(\"last_run_a_execution_date\", \"\")
s.setdefault(\"last_run_a_decision\", \"\")
s.setdefault(\"last_run_b_execution_date\", \"\")
s.setdefault(\"last_run_b_decision\", \"\")
# rename old keys if present
for old, new in [(\"last_session_date\",\"last_execution_date\"),(\"last_session_type\",\"last_execution_type\"),(\"last_session_decision\",\"last_execution_decision\")]:
    if old in s:
        s[new] = s.pop(old)
with open(\"/home/pi/run-coach/data/plan_state.json\", \"w\") as f:
    json.dump(s, f, indent=2)
print(json.dumps(s, indent=2))
"'
```

- [ ] **Step 3: Restart service and verify**

```bash
ssh pi@192.168.1.136 'sudo systemctl restart run-coach && sleep 2 && systemctl status run-coach'
```
Expected: `active (running)`

- [ ] **Step 4: Push updated calendar**

```bash
curl -X POST http://192.168.1.136:5001/calendar/push
```
Expected: `{"status": "ok", "message": "Calendar pushed to GitHub."}`

---

## Sleep Bug — Remaining Investigation (NOT Implemented Here)

Per systematic-debugging Phase 1, the instrumentation above (Task 1) is the first action. After the next morning execution, check the debug response to confirm what `sleep_total_hrs` and `sleep_deep_hrs` values the server received.

**What to check in the Shortcut (open on iPhone/Mac):**
1. **Which sleep categories are summed?** Should be Core + Deep + REM for total. Deep only for deep_hrs. Using all stages for total would include Awake time; using only Deep for total gives ~1.5–2 hrs.
2. **Time window:** Should be 18 hrs lookback. If 8 hrs, a sleep that crosses midnight may be partially outside the window.
3. **Unit:** HealthKit returns sleep category samples as durations. Confirm the Shortcut divides by 3600 if the result is in seconds, or by 60 if in minutes.

Root cause cannot be confirmed until the debug response shows what the server received after the Shortcut fix.
