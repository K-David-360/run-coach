# Training Rework (Push/Pull/Full, 6-Week Cycle, Jumps) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Lower/Upper/Full + KB-ladder strength week and the 4-week cycle with Push/Pull/Full lift days, a jump block, and a 6-week cycle (5 build + 1 deload) driven by one counter.

**Architecture:** A new `cycle.py` owns all week math (cycle week, block week, deload, jump prescription) and is the only place `DELOAD_EVERY_N_WEEKS` lives; `server.py`, `rule_engine.py`, `plan_generator.py` and `calendar_generator.py` all read it. Run plan tables grow to 5 build weeks and the deload run is computed once from week 5. The KB ladder is deleted everywhere.

**Tech Stack:** Python 3, Flask, pytest. No new dependencies.

**Spec:** `/Users/David/Documents/Claude/health-bootcamp/03-run-coach-handoff.md` (section 6, items 1–5; section 10 step 0 and step 5). Lift menu source: `/Users/David/Documents/Claude/health-bootcamp/01-protocol.md` ("Lift menu", "Session length").

## Global Constraints

- `DELOAD_EVERY_N_WEEKS = 6`, defined once in `cycle.py`; no other file may hardcode 4 or 6 as a cycle length.
- Lift-day labels are exactly `Push` (mon), `Pull` (wed), `Full` (fri). Never "Lift A/B/C", "Lower Body", "Upper Body".
- Galpin wording stays: REDUCE = same weight, ~80% of sets; DELOAD = same weight, 50% of sets. Volume is cut, intensity never is. Keep the existing `_STRENGTH_NOTES` / `_STRENGTH_PHRASE` strings.
- Deload run = `ceil(week-5 work_min * 0.70)`, same zone (Zone 2 easy). Never stack a second reduction on top.
- Jumps: progression weeks 1–4 → 2 x 10 per lift day (weekly target 60); 5+ → 3 x 10 (weekly target 90); deload or pre-block week → none (0).
- Remove all KB ladder code, state keys and text. An existing `plan_state.json` that still has `kb_weeks_elapsed` / `kb_peak_rung` must load without error (keys ignored).
- Date-dependent functions take `today: date = None` defaulting to `date.today()`; tests pass a fixed date.
- No body-composition data, flags or numbers anywhere in this plan's output (calendar, `current_session.json`, `plan_state.json`).
- Run tests with `python3 -m pytest -q` from the repo root. All 28 existing tests (as updated by these tasks) must pass at the end of every task.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- The Pi's real `plan_state.json` (has `kb_*` keys, `current_week: 3`, `cycle_start_date: "2026-09-28"`, `lthr_test_*`) must still load and produce a session: test added in Task 4.
- Deploying before `cycle_start_date` (new code live Oct 19–25, start Oct 26) must read as a deload week with no jumps, not week 1: test added in Task 1.
- An empty or malformed `cycle_start_date` must not crash the server or calendar; it reads as week 1 / block week 1: test added in Task 1.
- An early DELOAD (from sleep, consecutive SUPPRESS or `well_above` load) in a build week must cut that week's own duration by 30%, not week 5's: test added in Task 3.
- A REDUCE whose reason was run load keeps jumps; one caused by HRV or sleep drops them: test added in Task 4.

---

### Task 1: `cycle.py`, the single week counter

**Files:**
- Create: `cycle.py`
- Modify: `server.py:128-139` (`_week_from_cycle_start` delegates to `cycle.week_in_cycle`)
- Test: `tests/test_cycle.py` (new), `tests/test_week_logic.py` (update expectations)

**Interfaces:**
- Produces (all in `cycle.py`):
  - `DELOAD_EVERY_N_WEEKS: int = 6`
  - `block_week(cycle_start: str, today: date = None) -> int`: absolute week number since `cycle_start` (1 on the start week, 7 on the first week of the second cycle). Returns 0 when `today < start`; returns 1 when `cycle_start` is empty or unparseable.
  - `week_in_cycle(cycle_start: str, today: date = None) -> int`: 1..6. `DELOAD_EVERY_N_WEEKS` (deload) when `today < start`; 1 when `cycle_start` is empty or unparseable.
  - `is_deload_week(week: int) -> bool`: `week == DELOAD_EVERY_N_WEEKS`.
  - `jump_prescription(cycle_start: str, today: date = None) -> dict`: `{"sets": int, "reps": 10, "weekly_target": int}`.
- `server._week_from_cycle_start(cycle_start_str, today=None) -> int` keeps its name and signature (tests import it) and returns `cycle.week_in_cycle(...)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_cycle.py`

```python
from datetime import date
from cycle import block_week, week_in_cycle, is_deload_week, jump_prescription, DELOAD_EVERY_N_WEEKS

START = "2026-10-26"  # Monday

def test_week_in_cycle_runs_1_to_6_then_wraps():
    assert week_in_cycle(START, today=date(2026, 10, 26)) == 1
    assert week_in_cycle(START, today=date(2026, 11, 1)) == 1      # Sunday, same week
    assert week_in_cycle(START, today=date(2026, 11, 30)) == 6     # 5 weeks later
    assert week_in_cycle(START, today=date(2026, 12, 7)) == 1      # wraps

def test_before_start_is_deload():
    assert week_in_cycle(START, today=date(2026, 10, 19)) == DELOAD_EVERY_N_WEEKS
    assert block_week(START, today=date(2026, 10, 19)) == 0
    assert jump_prescription(START, today=date(2026, 10, 19)) == {"sets": 0, "reps": 10, "weekly_target": 0}

def test_bad_start_reads_as_week_one():
    for bad in ("", "not-a-date", None):
        assert week_in_cycle(bad, today=date(2026, 10, 26)) == 1
        assert block_week(bad, today=date(2026, 10, 26)) == 1

def test_is_deload_week():
    assert is_deload_week(6) and not is_deload_week(5) and not is_deload_week(1)

def test_jump_progression_skips_deload_weeks():
    # block week -> (sets, weekly_target), per handoff 6.3b mapping table
    expected = {1: (2, 60), 4: (2, 60), 5: (3, 90), 6: (0, 0), 7: (3, 90), 11: (3, 90), 12: (0, 0)}
    for bw, (sets, target) in expected.items():
        monday = date(2026, 10, 26).toordinal() + (bw - 1) * 7
        rx = jump_prescription(START, today=date.fromordinal(monday))
        assert (rx["sets"], rx["weekly_target"]) == (sets, target), bw
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python3 -m pytest tests/test_cycle.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cycle'`

- [ ] **Step 3: Implement `cycle.py`**

Jump-progression week for a build block week `bw` is `bw - (bw - 1) // DELOAD_EVERY_N_WEEKS` (deload weeks before it don't count); sets = 2 if that is ≤ 4 else 3; weekly_target = sets × 10 × 3 lift days.

- [ ] **Step 4: Update `tests/test_week_logic.py` for the 6-week cycle**

Keep the existing tests for weeks 1–4 and `_most_recent_monday`. Replace `test_cycle_rolls_to_week1_after_four_weeks` and `test_cycle_rolls_correctly_week2_of_new_cycle` with:

```python
def test_week6_is_last_week_of_cycle():
    assert _week_from_cycle_start("2026-06-09", today=date(2026, 7, 14)) == 6

def test_cycle_rolls_to_week1_after_six_weeks():
    assert _week_from_cycle_start("2026-06-09", today=date(2026, 7, 21)) == 1

def test_before_cycle_start_is_deload_week():
    assert _week_from_cycle_start("2026-06-09", today=date(2026, 6, 8)) == 6
```

- [ ] **Step 5: Make `server._week_from_cycle_start` delegate to `cycle.week_in_cycle`**, updating its docstring to "1–6".

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add cycle.py server.py tests/test_cycle.py tests/test_week_logic.py
git commit -m "feat: add cycle.py with 6-week cycle, block week and jump prescription"
```

---

### Task 2: Rule engine reads the 6-week cycle and reports its trigger

**Files:**
- Modify: `rule_engine.py:105-201`
- Test: `tests/test_rule_engine.py` (new)

**Interfaces:**
- Consumes: `cycle.is_deload_week(week) -> bool`
- Produces: `rule_engine(data, hrv_ratio)` signature unchanged; the returned dict gains `"trigger": str`, one of `"deload_week" | "suppress_streak" | "short_sleep_nights" | "load" | "hrv" | "sleep" | "rhr" | "suppress"`. The value is whichever rule last set `reason` (so a REDUCE from load `above` is `"load"`, a HOLD→REDUCE from sleep < 6 h is `"sleep"`, from HRV < 0.70 is `"hrv"`). Task 4 uses it.

- [ ] **Step 1: Write the failing tests** in `tests/test_rule_engine.py`

Patch file reads with `unittest.mock.patch("rule_engine._load_json", side_effect=...)` returning a plan state for paths ending in `plan_state.json` and `[]` for history.

```python
def test_week6_is_scheduled_deload():        # current_week=6 -> DELOAD, trigger "deload_week"
def test_week4_is_no_longer_deload():         # current_week=4, steady load, good sleep -> HOLD
def test_reduce_from_load_has_load_trigger(): # load "above", hrv_ratio 1.0, sleep 8 -> REDUCE, trigger "load"
def test_reduce_from_sleep_has_sleep_trigger(): # load "steady", sleep 5.5 -> REDUCE, trigger "sleep"
def test_reduce_from_hrv_has_hrv_trigger():   # load "steady", hrv_ratio 0.65, sleep 8 -> REDUCE, trigger "hrv"
def test_action_text_uses_galpin_wording():
    # for DELOAD and REDUCE results: "lower body" not in action.lower(); "same weight" in action.lower()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_rule_engine.py -q`
Expected: FAIL (`week4` returns DELOAD; `KeyError: 'trigger'`).

- [ ] **Step 3: Implement.** Replace `current_week % 4 == 0` with `is_deload_week(current_week)` and reason `"Scheduled deload (week 6)"`. Add `trigger` alongside every `reason` assignment. Replace the two stale action strings with:
  - DELOAD: `"Deload week. Runs: same zone, ~70% duration. Strength: same weight, half the sets. No jumps."`
  - REDUCE: `"Keep session type, reduce duration ~15%. Strength: same weight, ~80% of sets."`

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add rule_engine.py tests/test_rule_engine.py
git commit -m "feat: rule engine deloads on week 6, reports trigger, Galpin action text"
```

---

### Task 3: Five-week run tables and a single deload calculation

**Files:**
- Modify: `plan_generator.py:1-73` (docstring, tables, delete dead `_PLAN` alias), `plan_generator.py:244-` (`generate_session`)
- Modify: `calendar_generator.py:134-170` (`_run_session`, `_run_session_actual`)
- Test: `tests/test_plan_generator.py`

**Interfaces:**
- Produces in `plan_generator.py`:
  - `_PLAN_PHASE1/2/3` with keys 1–5 only (no deload row). `_BUILD_WEEKS = 5`.
  - `plan_week_for(week_in_cycle: int) -> int`: `min(week_in_cycle, _BUILD_WEEKS)` (week 6 uses week 5 as its base).
  - `deload_work_min(base_work_min: int | None) -> int`: `max(8, ceil((base_work_min or 18) * 0.70))`.
- Calendar consumes both; it must not compute a deload duration any other way.

Table values (work_min; intervals stay `None`), from the handoff:

| Phase | Slot | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 1 | A easy | 18 | 20 | 23 | 24 | 25 |
| 1 | B easy | 20 | 23 | 25 | 26 | 27 |
| 2 | A easy | 25 | 27 | 30 | 32 | 33 |
| 2 | B progression | 25 | 27 | 30 | 32 | 33 |
| 3 | A easy | 28 | 30 | 33 | 33 | 33 |
| 3 | B intervals | None | None | None | None | None |

- [ ] **Step 1: Write the failing tests** in `tests/test_plan_generator.py`

Replace `test_deload_run_is_70pct_of_base` (it hardcodes the old table). Pin the slot by patching `plan_generator.date` or by asserting for both slots via a helper that calls `generate_session` with `current_week` set; the generator picks slot from weekday, so patch `plan_generator.date.today` to a fixed Tuesday (`2026-11-03`) for slot A.

```python
def test_week6_deload_is_70pct_of_week5():      # phase 2, current_week 6, DELOAD, Tuesday -> Work block == ceil(33*0.7) == 24
def test_early_deload_in_build_week_uses_that_week(): # phase 2, current_week 2, DELOAD, Tuesday -> 19 (ceil(27*0.7))
def test_week5_hold_phase2_run_a():             # current_week 5, HOLD, Tuesday -> Work block 33
def test_phase3_run_a_holds_weeks_3_to_5():     # weeks 3,4,5 HOLD Tuesday -> 33 each
def test_run_a_is_easy_in_every_phase_and_week(): # handoff 6.4: Tuesday base type "easy" for phases 1-3, weeks 1-5
def test_deload_work_min_floor():               # deload_work_min(None) == 13; deload_work_min(5) == 8
```

Keep `test_deload_run_is_zone2_not_zone1`, `test_strength_*_messaging`.

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_plan_generator.py -q`
Expected: FAIL (`ImportError: deload_work_min`, week-5 row missing).

- [ ] **Step 3: Implement** the tables, `plan_week_for`, `deload_work_min`; in `generate_session` look up `plan_table[plan_week_for(current_week)]` and use `deload_work_min(base_work_min)` in the DELOAD branch. In `calendar_generator._run_session` (deload branch) and `_run_session_actual` (DELOAD branch) call `deload_work_min(base["work_min"])` on the `plan_week_for(...)` row. Update the module docstring's week table.

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add plan_generator.py calendar_generator.py tests/test_plan_generator.py
git commit -m "feat: 5 build weeks per run phase; deload computed once from week 5"
```

---

### Task 4: Push/Pull/Full strength sessions with jumps; delete the KB ladder from the server

**Files:**
- Modify: `plan_generator.py:136-210` (delete `kb_peak_from_weeks`, `_kb_ladder_blocks`; rewrite `_DAY_LABEL`, `generate_strength_session`)
- Modify: `server.py:52` (import), `server.py:82-100` (`_DEFAULT_PLAN_STATE`), `server.py:509-525` (strength branch)
- Modify: `reset.py` (drop `kb_*` keys; docstring "6-week plan")
- Test: `tests/test_plan_generator.py`, `tests/test_server_strength.py` (new)

**Interfaces:**
- Consumes: `cycle.jump_prescription(cycle_start, today) -> dict`, `cycle.week_in_cycle`, `cycle.is_deload_week`; `rule_engine` result `"trigger"` (Task 2).
- Produces in `plan_generator.py`:
  - `_DAY_LABEL = {"mon": "Push", "wed": "Pull", "fri": "Full"}`
  - `_LIFT_MENU: dict[str, str]`: one line per lift slot for each day, copied from `01-protocol.md` "Lift menu" (Push / Pull / Full lines; farmer carries included on Full).
  - `jump_line(rx: dict) -> str`: `"Jumps: 2 x 10 countermovement jumps (weekly target 60). Land softly, rest 30-60 s."` or, when `rx["sets"] == 0`, `"Jumps: none this week (deload)."`. Task 5 uses it for calendar text.
  - `generate_strength_session(decision: str, day: str, today: date = None, skip_jumps: bool = False) -> dict`; the `bell_reset` parameter is removed. Blocks, in order: `{"name": "Jumps", "sets": int, "reps": 10, "notes": jump_line(rx)}` (omitted when `skip_jumps`, decision is DELOAD/SUPPRESS, or `rx["sets"] == 0`), then `{"name": <label>, "notes": _STRENGTH_NOTES[decision] + "\n" + _LIFT_MENU[day]}`. Summary format unchanged except the label (e.g. `"⬇️ 🏋️ Pull — Pull back — same weight, drop to ~80% of your sets."`). `rx` comes from `jump_prescription(plan_state["cycle_start_date"], today)`.
- `server.post_healthkit` strength branch: no KB state; calls `generate_strength_session(decision["decision"], day_key, today=date.today(), skip_jumps=...)` with `skip_jumps = decision["decision"] == "REDUCE" and decision.get("trigger") in ("hrv", "sleep")`. Passing `today` from `server`'s own `date` is what lets the server tests freeze the day.

- [ ] **Step 1: Write the failing tests**

In `tests/test_plan_generator.py` (patch `plan_generator._load_json` to return `{"cycle_start_date": "2026-10-26"}`; pass `today=date(2026, 10, 26)`):

```python
def test_labels_are_push_pull_full():           # summaries contain "Push"/"Pull"/"Full" for mon/wed/fri; none contain "Lower", "Upper", "KB"
def test_jumps_block_first_with_week1_prescription(): # HOLD mon -> blocks[0] == {"name": "Jumps", "sets": 2, "reps": 10, ...}, "weekly target 60" in notes
def test_jumps_week5_three_sets():              # today=2026-11-23 -> sets 3, "weekly target 90"
def test_no_jumps_on_deload_or_suppress():      # DELOAD and SUPPRESS -> no block named "Jumps"
def test_no_jumps_when_skip_requested():        # REDUCE, skip_jumps=True -> no "Jumps" block
def test_lift_menu_in_notes():                  # mon notes contain "squat 3 x 5–8"; wed contains "trap-bar deadlift 3 x 5"
def test_kb_ladder_gone():                      # import plan_generator; not hasattr(plan_generator, "kb_peak_from_weeks")
```

In `tests/test_server_strength.py`, use Flask's `app.test_client()`, point `server.PLAN_STATE_FILE`, `server.HISTORY_FILE`, `server.CURRENT_SESSION_FILE` (and the same names in `plan_generator` / `rule_engine`) at `tmp_path` files via `monkeypatch`, set `server.GITHUB_TOKEN = ""`, and freeze the weekday by monkeypatching `server.date` with a `date` subclass whose `today()` returns Monday `2026-10-26`:

```python
PI_STATE = {  # shape of the real Pi file on 2026-10-15, synthetic values
    "current_week": 3, "cycle_start_date": "2026-10-26", "consecutive_suppress": 0, "total_runs": 5,
    "phase": 2, "kb_weeks_elapsed": 4, "kb_peak_rung": 15, "lthr_test_date": "2026-08-15",
    "lthr_test_tier": "urgent", "last_execution_date": "", "last_execution_decision": "",
}

def test_legacy_state_with_kb_keys_loads(...):     # POST /healthkit steady payload -> 200, type "strength_mon", no "KB" anywhere in response JSON
def test_reduce_from_load_keeps_jumps(...):        # load_pct 30 (above), good sleep/HRV -> REDUCE, "Jumps" block present
def test_reduce_from_sleep_drops_jumps(...):       # load_pct 0, sleep_total_hrs 5.5 -> REDUCE, no "Jumps" block
def test_server_no_longer_writes_kb_state(...):    # after POST, saved plan_state has no new kb_* changes (kb_weeks_elapsed still 4, untouched)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_plan_generator.py tests/test_server_strength.py -q`
Expected: FAIL (labels still Lower/Upper; `skip_jumps` unexpected keyword).

- [ ] **Step 3: Implement** the `plan_generator` changes, the server strength branch, and remove `kb_weeks_elapsed` / `kb_peak_rung` from `_DEFAULT_PLAN_STATE` and `reset.py`. Leave existing keys in a loaded state untouched (do not delete them from the file).

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`). `test_calendar_accuracy.py` will still fail to import `kb_peak_from_weeks` until Task 5; if so, run `python3 -m pytest -q --ignore=tests/test_calendar_accuracy.py` here and confirm everything else passes. Task 5 restores the full suite.

- [ ] **Step 5: Commit**

```bash
git add plan_generator.py server.py reset.py tests/test_plan_generator.py tests/test_server_strength.py
git commit -m "feat: Push/Pull/Full sessions with jump block; remove KB ladder"
```

---

### Task 5: Calendar on the 6-week cycle with Push/Pull/Full events

**Files:**
- Modify: `calendar_generator.py` (docstring, imports, `_STRENGTH_NORMAL`, delete `_STRENGTH_DELOAD`, `generate_ics` loop and window)
- Modify: `server.py:300` (`get_calendar` docstring "4-week" → describe the window)
- Test: `tests/test_calendar_accuracy.py`

**Interfaces:**
- Consumes: `cycle.week_in_cycle`, `cycle.is_deload_week`, `cycle.jump_prescription`, `cycle.DELOAD_EVERY_N_WEEKS`; `plan_generator._DAY_LABEL`, `_LIFT_MENU`, `jump_line`, `plan_week_for`, `deload_work_min`, `_STRENGTH_NOTES`.
- Produces: `generate_ics(plan_state, today=None) -> str` (signature unchanged). Week numbers come from `week_in_cycle(plan_state.get("cycle_start_date", ""), today=week_monday)` for each shown week; `plan_state["current_week"]` is no longer read.
  - Window: `weeks_to_show = max(4, DELOAD_EVERY_N_WEEKS - this_week + 1)` where `this_week` is today's cycle week (always shows through the next deload).
  - Strength event, every lift day every week (no dropped Friday): summary `"🏋️ Push"` / `"🏋️ Pull"` / `"🏋️ Full"`, `"⛔️ "` prefix in deload weeks. Description: `"About 45–55 min."`, the day's `_LIFT_MENU` line, `jump_line(rx)` with `rx = jump_prescription(cycle_start, today=week_monday)` (deload weeks show the "none this week" line), and in deload weeks `_STRENGTH_NOTES["DELOAD"]`. Today's live-decision emoji and guidance logic stays as is.
  - Run events: deload weeks use `deload_work_min` on the `plan_week_for(6)` row.

- [ ] **Step 1: Update the failing tests** in `tests/test_calendar_accuracy.py`

Drop `kb_weeks_elapsed` / `kb_peak_rung` from `_base_plan_state`; set its default `cycle_start_date` to `_MONDAY.isoformat()` (already the case). Rewrite `test_strength_deload_week_guidance_not_doubled` to build a deload week with `cycle_start_date=(_MONDAY - timedelta(weeks=5)).isoformat()`. Add:

```python
def test_strength_events_are_push_pull_full():   # Mon/Wed/Fri summaries end with "Push"/"Pull"/"Full"; "KB" not in ics; "Lower Body" not in ics
def test_week1_events_carry_jump_target():       # Mon description contains "weekly target 60"
def test_deload_week_keeps_all_three_lift_days(): # cycle start 5 weeks back: Mon, Wed AND Fri events exist, each starts with "⛔️", contain "none this week (deload)" and "half the sets"
def test_window_reaches_next_deload():            # cycle start 0 weeks back -> an event exists on _MONDAY + 5 weeks (week 6); cycle start 4 weeks back -> 4 weeks shown
def test_deload_run_is_70pct_of_week5():          # phase 2, deload week Tuesday summary == "⛔️ 🏃‍♂️ Deload Run — 34 mins" (24 work + 10)
def test_pre_start_week_is_deload():              # cycle_start_date = _MONDAY + 1 week -> this week's Mon summary starts with "⛔️"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_calendar_accuracy.py -q`
Expected: FAIL (`ImportError: kb_peak_from_weeks` or wrong labels).

- [ ] **Step 3: Implement** the calendar changes above and update the module docstring (schedule, "6-week cycle", no Friday drop).

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Verify the KB ladder is gone from code**

Run: `grep -rniE 'kb_|ladder|bell_reset|kettlebell' --include='*.py' .`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add calendar_generator.py server.py tests/test_calendar_accuracy.py
git commit -m "feat: calendar follows 6-week cycle with Push/Pull/Full and jump targets"
```

---

### Task 6: Docs, git sync and Pi deploy

**Files:**
- Modify: `CLAUDE.md`, `SHORTCUTS_GUIDE.md`, `run-coach-training-structure-v1.md`, `docs/deload_protocol.md` (if it names week 4)

- [ ] **Step 1: Update docs.** In `CLAUDE.md`: replace the "4-week plan cycle", "Weekly schedule", "Strength session intensity class flags" deload line ("Week 4 deload: Mon → Full Body (no lower)…"), the whole "KB Breathing Ladder" section, `kb_*` fields in the `plan_state.json` schema, "Calendar window" text, and KB lines in "Current state" / "Key design decisions" with the 6-week cycle, Push/Pull/Full, jump block and new window rule. In `run-coach-training-structure-v1.md`: line 65 → "Deload every 6th week (5 build + 1 deload)"; line ~201 example REDUCE strength text → "Strength: same weight, ~80% of sets."; "Strength Session Load Weighting" table → Push 0.7, Pull 1.0, Full 1.0. Remove ladder text from `SHORTCUTS_GUIDE.md`.

- [ ] **Step 2: Verify no stale text remains**

Run: `grep -rniE 'ladder|kb_|kettlebell|lower body|upper body|% 4|4-week' --include='*.md' --include='*.py' . | grep -v docs/superpowers`
Expected: no output (or only historical lines in the "Completed" list, which may stay).

- [ ] **Step 3: Commit docs**

```bash
git add CLAUDE.md SHORTCUTS_GUIDE.md run-coach-training-structure-v1.md docs/deload_protocol.md
git commit -m "docs: 6-week cycle, Push/Pull/Full, jumps; remove KB ladder"
```

- [ ] **Step 4: Sync with GitHub.** `git fetch origin && git merge origin/main`; on conflict in `calendar-rc7f4a2b.ics`, take the remote copy (`git checkout --theirs calendar-rc7f4a2b.ics`). Run `python3 -m pytest -q` (all pass), then ask David before `git push`.

- [ ] **Step 5: Deploy to the Pi** using the Terminal SSH session method in `~/.claude/CLAUDE.md` (base64 transfer, verify `sha256sum`, timestamped `.bak`). Files: `cycle.py` (new), `server.py`, `rule_engine.py`, `plan_generator.py`, `calendar_generator.py`, `reset.py`. Then on the Pi set `"cycle_start_date": "2026-10-26"` in `~/run-coach/data/plan_state.json` (edit only that key; keep a `.bak`). Ask David to run `sudo systemctl restart run-coach` (never type the sudo password), then verify with `systemctl show run-coach -p ActiveEnterTimestamp`.

- [ ] **Step 6: Smoke test on the Pi.** `curl -s -X POST http://localhost:5001/calendar/push` from the Pi shell; then fetch `https://k-david-360.github.io/run-coach/calendar-rc7f4a2b.ics` and confirm: this week's events start with `⛔️` (pre-block deload) if before Oct 26; Mon Oct 26 shows `🏋️ Push` with "weekly target 60"; no "KB" text anywhere.
