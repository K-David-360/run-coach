# Calendar-Week Anchored Training Cycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace run-count-based week advancement with calendar-week anchoring, so the 4-week training cycle always aligns with Mon–Sun calendar weeks instead of drifting when runs are skipped or the cycle boundary falls mid-week.

**Architecture:** Add `cycle_start_date` (ISO date string of the Monday that started the current 4-week cycle) to plan_state.json. A helper in server.py computes `current_week` (1–4) from `(today - cycle_start_date).days // 7 % 4 + 1` and writes it to plan_state on every `/healthkit` request before anything else reads it. Remove the `run_in_week` counter and the run-count week-advancement block. Slot (A/B) is derived from the day of week (Tuesday=A, Saturday=B) rather than from `run_in_week`.

**Tech Stack:** Python 3, Flask, pytest (added for tests)

---

## Predicted output after deploy (current Pi state: week 4, deployed Mon Jun 8 2026)

Migration sets `cycle_start_date = "2026-06-09"` (next Monday, since today IS Monday — see Task 2 for migration detail).

Wait — if deploying TODAY (Jun 8, Monday), `_most_recent_monday()` = Jun 8, and `_week_from_cycle_start("2026-06-08")` = `(0 days) // 7 % 4 + 1 = 1`. Week 1 immediately.

| Date | Day | Old behaviour | New behaviour |
|------|-----|--------------|---------------|
| Jun 8 (Mon) | Lower Body | ⛔️ DELOAD (week 4) | Week 1 — no deload |
| Jun 10 (Tue) | Run A | DELOAD, slot A, 20 min | Week 1, slot A, 28 min easy |
| Jun 11 (Wed) | Upper + KB | DELOAD | Week 1 — normal |
| Jun 13 (Fri) | Full Body | DELOAD | Week 1 — normal |
| Jun 14 (Sat) | Run B | DELOAD, 20 min | Week 1, slot B, 30 min easy |
| Jun 16 (Mon) | Lower Body | (would have been week 1) | Week 2 |
| Jun 23 (Mon) | Lower Body | Week 2 | Week 3 |
| Jun 30 (Mon) | Lower Body | Week 3 | Week 4 — DELOAD |
| Jul 7 (Mon)  | Lower Body | Week 4 — DELOAD | Week 1 new cycle |

If a run is skipped (say Jun 10 Tue), the calendar still advances. Jun 16 (Mon) is week 2 regardless. The missed run is just missed — no cycle drift.

---

## File map

| File | Change |
|------|--------|
| `server.py` | Add `_most_recent_monday()` and `_week_from_cycle_start()` helpers; add migration block; compute + write `current_week` on every request; remove week-advancement block from run handler; remove `run_in_week` from state writes |
| `plan_generator.py` | Replace `run_in_week`-based slot with `date.today().weekday() == 1` |
| `reset.py` | Add `cycle_start_date` to defaults; remove `run_in_week` |
| `tests/test_week_logic.py` | New — tests for `_week_from_cycle_start` |

`rule_engine.py`, `calendar_generator.py` — **no changes needed** (they read `current_week` from plan_state, which server.py now keeps fresh).

---

## Task 1: Tests for week-computation helper

**Files:**
- Create: `tests/test_week_logic.py`

The helper we're about to write has the signature:

```python
def _week_from_cycle_start(cycle_start_str: str, today: date = None) -> int:
    ...
```

Write the tests first so we can run them against the implementation in Task 2.

- [ ] **Step 1: Create the test file**

```python
# tests/test_week_logic.py
from datetime import date
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import _week_from_cycle_start, _most_recent_monday


# ── _week_from_cycle_start ────────────────────────────────────────────────────

def test_week1_on_cycle_start_day():
    start = date(2026, 6, 9)  # Monday
    assert _week_from_cycle_start("2026-06-09", today=start) == 1

def test_week1_last_day():
    start = date(2026, 6, 9)
    sunday = date(2026, 6, 15)  # 6 days after Monday = Sunday
    assert _week_from_cycle_start("2026-06-09", today=sunday) == 1

def test_week2_starts_on_second_monday():
    start = date(2026, 6, 9)
    second_monday = date(2026, 6, 16)
    assert _week_from_cycle_start("2026-06-09", today=second_monday) == 2

def test_week3():
    start = date(2026, 6, 9)
    third_monday = date(2026, 6, 23)
    assert _week_from_cycle_start("2026-06-09", today=third_monday) == 3

def test_week4():
    start = date(2026, 6, 9)
    fourth_monday = date(2026, 6, 30)
    assert _week_from_cycle_start("2026-06-09", today=fourth_monday) == 4

def test_cycle_rolls_to_week1_after_four_weeks():
    start = date(2026, 6, 9)
    fifth_monday = date(2026, 7, 7)  # 28 days later
    assert _week_from_cycle_start("2026-06-09", today=fifth_monday) == 1

def test_cycle_rolls_correctly_week2_of_new_cycle():
    start = date(2026, 6, 9)
    sixth_monday = date(2026, 7, 14)  # 35 days later
    assert _week_from_cycle_start("2026-06-09", today=sixth_monday) == 2

def test_invalid_cycle_start_returns_1():
    assert _week_from_cycle_start("", today=date(2026, 6, 9)) == 1
    assert _week_from_cycle_start("not-a-date", today=date(2026, 6, 9)) == 1

def test_tuesday_of_week1_is_still_week1():
    start = date(2026, 6, 9)
    tuesday = date(2026, 6, 10)
    assert _week_from_cycle_start("2026-06-09", today=tuesday) == 1

def test_saturday_of_week4_is_still_week4():
    start = date(2026, 6, 9)
    week4_saturday = date(2026, 7, 4)
    assert _week_from_cycle_start("2026-06-09", today=week4_saturday) == 4


# ── _most_recent_monday ───────────────────────────────────────────────────────

def test_most_recent_monday_when_today_is_monday():
    monday = date(2026, 6, 9)
    assert _most_recent_monday(monday) == monday

def test_most_recent_monday_when_today_is_wednesday():
    wednesday = date(2026, 6, 11)
    assert _most_recent_monday(wednesday) == date(2026, 6, 9)

def test_most_recent_monday_when_today_is_sunday():
    sunday = date(2026, 6, 15)
    assert _most_recent_monday(sunday) == date(2026, 6, 9)
```

- [ ] **Step 2: Run tests to confirm they fail (server.py doesn't have these functions yet)**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -m pytest tests/test_week_logic.py -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` — functions not yet defined in server.py.

---

## Task 2: Add helpers + migration to server.py

**Files:**
- Modify: `server.py`

Add two helper functions and a migration block. The `today` parameter on both helpers exists solely for testability — production callers omit it.

- [ ] **Step 1: Add helpers after the `_safe_float` function (around line 108)**

Find the block:
```python
def _safe_float(value, default=0.0):
    """Convert value to float, returning default for None, '', or unconvertible values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
```

Add immediately after it:

```python
def _most_recent_monday(today: date = None) -> date:
    if today is None:
        today = date.today()
    return today - timedelta(days=today.weekday())


def _week_from_cycle_start(cycle_start_str: str, today: date = None) -> int:
    """Return training week (1–4) given the ISO date of the cycle's first Monday."""
    if today is None:
        today = date.today()
    try:
        start = date.fromisoformat(cycle_start_str)
    except (ValueError, TypeError):
        return 1
    if today < start:
        return 1
    weeks_elapsed = (today - start).days // 7
    return weeks_elapsed % 4 + 1
```

Note: `timedelta` is already imported at the top of server.py as part of `from datetime import date`. Add `timedelta` to that import if it isn't already there:

```python
from datetime import date, timedelta
```

- [ ] **Step 2: Run tests — they should now pass for the helper functions**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -m pytest tests/test_week_logic.py -v
```

Expected: all 13 tests pass.

- [ ] **Step 3: Add migration + current_week refresh inside `post_healthkit`, right after plan_state is loaded**

Find this line in `post_healthkit` (around line 387):
```python
    plan_state = _load_json(PLAN_STATE_FILE, default=dict(_DEFAULT_PLAN_STATE))
```

Add immediately after it:

```python
    # ── Calendar-week anchoring: set cycle_start_date if absent (first deploy) ──
    if not plan_state.get("cycle_start_date"):
        plan_state["cycle_start_date"] = _most_recent_monday().isoformat()

    # Recompute current_week from calendar date — this is now the source of truth.
    plan_state["current_week"] = _week_from_cycle_start(plan_state["cycle_start_date"])
    _save_json(PLAN_STATE_FILE, plan_state)
```

- [ ] **Step 4: Commit**

```bash
cd /Users/David/Documents/Claude/run-coach && git add server.py tests/test_week_logic.py && git commit -m "feat: add calendar-week helpers and migration to server.py"
```

---

## Task 3: Remove run_in_week advancement from server.py

The week no longer advances by counting runs. Both the `/healthkit` run-day handler and the legacy `/run` handler contain a block that increments `run_in_week` and advances `current_week`. Remove both.

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Remove the advancement block from the `/healthkit` run-day handler**

Find and remove this block (around lines 540–546):
```python
    run_in_week = plan_state.get("run_in_week", 0) + 1
    if run_in_week >= 2:
        run_in_week  = 0
        current_week = plan_state.get("current_week", 1)
        plan_state["current_week"] = 1 if current_week >= 4 else current_week + 1
    plan_state["run_in_week"] = run_in_week
```

Replace it with nothing — just delete those 6 lines.

- [ ] **Step 2: Remove the advancement block from the legacy `/run` handler**

Find and remove this block (around lines 217–224 in the `post_run` function):
```python
    # Advance run count within week; roll week after 2 runs
    run_in_week = plan_state.get("run_in_week", 0) + 1
    if run_in_week >= 2:
        run_in_week = 0
        current_week = plan_state.get("current_week", 1)
        plan_state["current_week"] = 1 if current_week >= 4 else current_week + 1

    plan_state["run_in_week"] = run_in_week
    _save_json(PLAN_STATE_FILE, plan_state)
```

The `_save_json` call stays. Replace just the `run_in_week` block above it with nothing.

- [ ] **Step 3: Update `_DEFAULT_PLAN_STATE` at the top of server.py**

Find:
```python
_DEFAULT_PLAN_STATE = {
    "current_week": 1,
    "run_in_week": 0,
    "consecutive_suppress": 0,
    "total_runs": 0,
    "phase": 1,
    "last_session_date": "",
    "last_session_type": "",
    "last_session_decision": "",
    "kb_weeks_elapsed": 0,
    "kb_peak_rung": 10,
}
```

Replace with:
```python
_DEFAULT_PLAN_STATE = {
    "current_week": 1,
    "cycle_start_date": "",
    "consecutive_suppress": 0,
    "total_runs": 0,
    "phase": 1,
    "last_session_date": "",
    "last_session_type": "",
    "last_session_decision": "",
    "kb_weeks_elapsed": 0,
    "kb_peak_rung": 10,
}
```

(`cycle_start_date` starts empty; the migration block in `post_healthkit` fills it on first request.)

- [ ] **Step 4: Verify server still imports cleanly**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -c "import server; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/David/Documents/Claude/run-coach && git add server.py && git commit -m "refactor: remove run-count week advancement, week now driven by cycle_start_date"
```

---

## Task 4: Fix slot determination in plan_generator.py

`generate_session` currently reads `run_in_week` from plan_state to determine slot A or B. Slot is now fixed by calendar day: Tuesday = A, Saturday = B.

**Files:**
- Modify: `plan_generator.py`

- [ ] **Step 1: Replace the slot logic in `generate_session`**

Find (around lines 265–273):
```python
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    current_week = plan_state.get("current_week", 1)
    run_in_week = plan_state.get("run_in_week", 0)
    phase = plan_state.get("phase", 1)

    # run_in_week is read BEFORE the server increments it:
    #   0 → this is the first run of the week  (slot A / Tuesday)
    #   1 → this is the second run of the week (slot B / Saturday)
    slot = "A" if run_in_week == 0 else "B"
```

Replace with:
```python
    plan_state = _load_json(PLAN_STATE_FILE, default={})
    current_week = plan_state.get("current_week", 1)
    phase = plan_state.get("phase", 1)

    # Slot is fixed by calendar day: Tuesday (weekday 1) = A, Saturday (weekday 5) = B
    slot = "A" if date.today().weekday() == 1 else "B"
```

- [ ] **Step 2: Verify tests still pass**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -m pytest tests/test_week_logic.py -v
```

Expected: all 13 tests pass.

- [ ] **Step 3: Smoke-test the session generator directly**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -c "
from plan_generator import generate_session
s = generate_session('HOLD', {})
print(s['slot'], s['week'], s['summary'])
"
```

Expected: prints a slot (A or B depending on today's weekday), week number, and a summary string. No error.

- [ ] **Step 4: Commit**

```bash
cd /Users/David/Documents/Claude/run-coach && git add plan_generator.py && git commit -m "refactor: derive run slot from calendar day instead of run_in_week counter"
```

---

## Task 5: Update reset.py

`reset.py` seeds plan_state.json. It should set `cycle_start_date` to the most recent Monday (so a fresh start always begins at week 1 of a clean cycle), and remove `run_in_week`.

**Files:**
- Modify: `reset.py`

- [ ] **Step 1: Update reset.py**

Replace the entire file content with:

```python
"""
reset.py — Reset plan state and history for a fresh start.

Run this before going live on the Pi, or any time you want to
start the 4-week plan from scratch.

Usage:
    python3 reset.py
"""

import json
import os
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")
HISTORY_FILE    = os.path.join(DATA_DIR, "history.json")


def _most_recent_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def reset():
    os.makedirs(DATA_DIR, exist_ok=True)

    cycle_start = _most_recent_monday().isoformat()
    default_state = {
        "current_week": 1,
        "cycle_start_date": cycle_start,
        "consecutive_suppress": 0,
        "total_runs": 0,
        "phase": 1,
        "last_processed_workout_date": "",
        "last_session_date": "",
        "last_session_type": "",
        "last_session_decision": "",
        "kb_weeks_elapsed": 0,
        "kb_peak_rung": 10,
    }

    with open(PLAN_STATE_FILE, "w") as f:
        json.dump(default_state, f, indent=2)
    print(f"✓ plan_state.json reset — cycle_start_date = {cycle_start}, week 1")

    with open(HISTORY_FILE, "w") as f:
        json.dump([], f)
    print("✓ history.json cleared")

    print("\nReady. Next POST to /healthkit will be run 1, week 1, slot A (if Tuesday).")


if __name__ == "__main__":
    reset()
```

- [ ] **Step 2: Run reset.py and inspect output**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 reset.py
```

Expected output:
```
✓ plan_state.json reset — cycle_start_date = 2026-06-08, week 1
✓ history.json cleared

Ready. Next POST to /healthkit will be run 1, week 1, slot A (if Tuesday).
```

- [ ] **Step 3: Verify plan_state.json looks correct**

```bash
cat /Users/David/Documents/Claude/run-coach/data/plan_state.json
```

Expected: `cycle_start_date` is today's Monday, `current_week` is 1, no `run_in_week` key.

- [ ] **Step 4: Commit**

```bash
cd /Users/David/Documents/Claude/run-coach && git add reset.py data/plan_state.json && git commit -m "feat: reset.py sets cycle_start_date to current Monday instead of tracking run_in_week"
```

---

## Task 6: Integration smoke-test (local)

Before deploying to Pi, simulate a full week locally to verify the week advances on Monday.

**Files:** none (test only)

- [ ] **Step 1: Simulate a Monday request**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -c "
import json, os
# Temporarily set cycle_start_date to last Monday
from datetime import date, timedelta
today = date.today()
monday = today - timedelta(days=today.weekday())
state_path = 'data/plan_state.json'
with open(state_path) as f:
    s = json.load(f)
s['cycle_start_date'] = monday.isoformat()
with open(state_path, 'w') as f:
    json.dump(s, f, indent=2)

from server import _week_from_cycle_start
print('Week today:', _week_from_cycle_start(monday.isoformat()))

# Simulate next Monday (7 days later)
next_monday = monday + timedelta(weeks=1)
print('Week next Monday:', _week_from_cycle_start(monday.isoformat(), today=next_monday))

# Simulate 4 weeks forward
for w in range(1, 6):
    d = monday + timedelta(weeks=w-1)
    print(f'  Week {w} starts {d}: computed week = {_week_from_cycle_start(monday.isoformat(), today=d)}')
"
```

Expected output (cycle starting Jun 8):
```
Week today: 1
Week next Monday: 2
  Week 1 starts 2026-06-08: computed week = 1
  Week 2 starts 2026-06-15: computed week = 2
  Week 3 starts 2026-06-22: computed week = 3
  Week 4 starts 2026-06-29: computed week = 4
  Week 5 starts 2026-07-06: computed week = 1
```

- [ ] **Step 2: Run all tests**

```bash
cd /Users/David/Documents/Claude/run-coach && python3 -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit (if any last fixes were needed)**

Only commit if Step 1 or 2 revealed a bug that needed fixing. Otherwise skip.

---

## Task 7: Deploy to Pi

**Files:** none new (deploy existing changes)

- [ ] **Step 1: Copy changed files to Pi**

```bash
scp /Users/David/Documents/Claude/run-coach/server.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/plan_generator.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/reset.py pi@192.168.1.136:~/run-coach/
```

- [ ] **Step 2: On the Pi, run reset.py to set cycle_start_date cleanly (or manually patch plan_state.json)**

If you want a fully clean start (week 1, cleared history):
```bash
ssh pi@192.168.1.136 'cd ~/run-coach && python3 reset.py'
```

If you want to preserve run history but just fix the cycle start (recommended for continuity — keeps total_runs and LTHR scheduling intact):
```bash
ssh pi@192.168.1.136 "python3 -c \"
import json
with open('/home/pi/run-coach/data/plan_state.json') as f:
    s = json.load(f)
s['cycle_start_date'] = '$(date -I -d 'monday')'
del s['run_in_week']
with open('/home/pi/run-coach/data/plan_state.json', 'w') as f:
    json.dump(s, f, indent=2)
print('Done:', s['cycle_start_date'])
\""
```

For the current Pi (today is Jun 8, Monday), you want `cycle_start_date = "2026-06-08"` so today is already week 1.

Simpler — just manually set it:
```bash
ssh pi@192.168.1.136 'python3 -c "
import json
with open(\"/home/pi/run-coach/data/plan_state.json\") as f:
    s = json.load(f)
s[\"cycle_start_date\"] = \"2026-06-08\"
s[\"current_week\"] = 1
s.pop(\"run_in_week\", None)
with open(\"/home/pi/run-coach/data/plan_state.json\", \"w\") as f:
    json.dump(s, f, indent=2)
print(\"OK\", s[\"cycle_start_date\"])
"'
```

- [ ] **Step 3: Restart the service**

```bash
ssh pi@192.168.1.136 'sudo systemctl restart run-coach && sleep 2 && systemctl status run-coach | head -10'
```

Expected: `Active: active (running)`

- [ ] **Step 4: Verify with a test POST**

```bash
curl -s -X POST http://192.168.1.136:5001/healthkit \
  -H "Content-Type: application/json" \
  -d '{"hrv_last_night":65,"sleep_total_hrs":7.5,"sleep_deep_hrs":1.2,"load_pct":0}' \
  | python3 -m json.tool | grep -E '"decision|week|notification|decision_reason"'
```

Expected: `"current_week": 1` in debug, notification should be `✅ On track` (not DELOAD), and the session should be a strength session (today is Monday).

- [ ] **Step 5: Verify plan_state on Pi reflects new schema**

```bash
ssh pi@192.168.1.136 'cat /home/pi/run-coach/data/plan_state.json'
```

Expected: has `cycle_start_date`, `current_week` is 1, no `run_in_week`.

---

## Self-review

**Spec coverage:**
- ✅ Week anchored to Mon–Sun calendar weeks via `cycle_start_date`
- ✅ Week 4 = deload, correctly detected via `current_week % 4 == 0` (unchanged rule)
- ✅ Skipped runs don't freeze the week counter
- ✅ Slot A/B derived from weekday, no longer from run counter
- ✅ `run_in_week` removed from writes
- ✅ Migration handles existing Pi state without requiring history reset
- ✅ `reset.py` produces clean week-1 state
- ✅ `calendar_generator.py` unchanged (reads `current_week` from plan_state which server.py keeps fresh)
- ✅ `rule_engine.py` unchanged (reads `current_week` from plan_state)
- ✅ Tests cover all 4 weeks, cycle rollover, boundary days, invalid input

**No placeholders found.**

**Type consistency:** `_week_from_cycle_start` and `_most_recent_monday` are defined in Task 2 with `today: date = None` signature and called in tests in Task 1 with `today=<date>` keyword arg — consistent throughout.
