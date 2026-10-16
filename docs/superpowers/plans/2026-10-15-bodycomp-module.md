# Body-Composition Weekly Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Sunday-morning weekly check on the Pi that turns a week of Apple Health data into a severity-ranked banner and stored report, plus a monthly tape log and a compact markdown packet for occasional Claude reviews.

**Architecture:** A `bodycomp/` package inside run-coach: `config.py` (defaults overlaid by a gitignored JSON), `store.py` (gitignored JSON files), `checks.py` (pure functions: samples → metrics → rule results → report), `review_packet.py` (markdown), `flags.py` (read-only hooks into the daily output). Three new routes on the existing Flask app. The existing morning Shortcut gains a Sunday-only branch; no second Shortcut.

**Tech Stack:** Python 3, Flask, pytest. No new dependencies.

**Spec:** `/Users/David/Documents/Claude/health-bootcamp/03-run-coach-handoff.md` (sections 3–5, 6 items 5–6, 7–10).

**Depends on:** `docs/superpowers/plans/2026-10-15-training-rework.md` merged first (uses `cycle.py`, `generate_strength_session(..., skip_jumps=)`, `rule_engine` `trigger`).

**Decisions this plan makes that refine the spec** (flagged to David with the plan):
1. Weekly payload carries per-sample `date=value` lines instead of 7-element arrays, because Shortcuts can loop over Health samples and format text but cannot easily build day-aligned arrays. The server groups by day.
2. Sleep for S1 comes from the existing `data/history.json` (already recorded by the daily Shortcut), not the weekly payload. Thursday and Sunday executions skip health processing, so at most 5 nights per week are available; S1 counts the nights it has.
3. `lift_sessions_done` and `lift_stalled` are optional Shortcut prompts ("Find Workouts" is unavailable in Shortcuts on this device, per `CLAUDE.md`). When absent, L1/L2 are not evaluated.
4. W1's baseline is `baseline_weight_lb` from the gitignored config if set; otherwise the first stored BC-1 week's average (the Oct 19 intro week). No personal number is needed in any file.

## Global Constraints

- Body-comp phases are `bc_phase` `"BC-1"` (maintenance build) / `"BC-2"` (deficit) and `bc_phase_start_date`, stored in `data/bodycomp/config.json`. Never a bare `phase` key; bodycomp code never reads or writes run-coach's `phase`. `bc_phase` is never advanced by code.
- `data/bodycomp/` is gitignored before any file is written there. Tests use `tmp_path` and synthetic numbers only; no real weight, height, lab or DEXA values in code, tests, comments or commits.
- Code defaults for absolute protein and calorie thresholds are `None` (rule not evaluated). The real protocol targets (P1, P2, E1 per phase, from `health-bootcamp/01-protocol.md`) go only into the Pi's gitignored config, never into code, tests or docs in this public repo. P3's g/kg rule (1.6) is the only protein default in code. Test fixtures use clearly synthetic values (weights around 180 lb, thresholds unlike the real ones).
- Bodycomp values, flags and flag text never go into the ICS calendar, `_push_calendar_to_github`, `data/plan_state.json` or `data/current_session.json`. The only exception is the generic, number-free S1/optional-run sentences defined in Task 6.
- Severity order: `["RED", "AMBER", "INFO", "OK"]`; banner lists the highest severity first.
- Missing-data rule: weight rules need ≥ 4 of 7 weight days; protein/energy rules need ≥ 5 of 7 days; otherwise the metric reports `INFO` "insufficient data" and recommends nothing.
- Values that are empty strings, `null`, unparseable, or `0` count as missing (Shortcuts sends `""` for missing values).
- Optional shared secret: when env `BODYCOMP_TOKEN` is set, every `/bodycomp/*` route requires header `X-Bodycomp-Token` equal to it, else 401.
- Date-dependent functions take `today: date = None`. Run tests with `python3 -m pytest -q`. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- The Shortcut re-runs on the same Sunday (or posts twice): the second report replaces the first for that `week_ending`, and deltas are computed against the previous week, never against itself: test in Task 4.
- First-ever week (no history): no delta, W2/W3/W4 skipped, banner shows `weight 180.0 (new)`: test in Task 3.
- Samples with `""`, `0`, junk lines, or dates outside the Sun–Sat window: ignored, not averaged in as 0: test in Task 2.
- A protein value logged as several samples on one day (one per meal): summed per day, not averaged: test in Task 2.
- `config.json` missing, empty, or holding an invalid `bc_phase`: defaults load for missing/empty; invalid `bc_phase` raises a clear `ValueError` and the route returns 500 with that message rather than silently checking the wrong phase: test in Task 1.

---

### Task 1: Package scaffold, config, store, gitignore

**Files:**
- Create: `bodycomp/__init__.py` (empty), `bodycomp/config.py`, `bodycomp/store.py`
- Modify: `.gitignore` (add `data/bodycomp/`)
- Test: `tests/test_bodycomp_store.py`

**Interfaces:**
- Produces in `bodycomp/config.py`:
  - `BODYCOMP_DIR = <repo>/data/bodycomp`, `CONFIG_FILE = BODYCOMP_DIR/config.json`
  - `DEFAULTS: dict` with exactly these keys and values:
    `bc_phase "BC-1"`, `bc_phase_start_date ""`, `baseline_weight_lb None`, `w1_hold_band_lb 1.0`, `w1_max_bc_week 12`, `w2_fast_loss_lb 1.0`, `w2_weeks 2`, `w3_early_rise_weeks 2`, `w3_loss_lb 0.2`, `w4_flat_lb 0.2`, `w4_weeks 3`, `protein_avg_min_g None`, `protein_low_g None`, `protein_min_g_per_kg 1.6`, `kcal_floor_bc1 None`, `kcal_floor_bc2 None`, `sleep_short_hrs 6.5`, `sleep_short_nights 3`, `steps_min_avg 6000`, `lift_sessions_min 3`, `min_weight_days 4`, `min_nutrition_days 5`
  - `load_config(path: str = CONFIG_FILE) -> dict`: `DEFAULTS` overlaid with the file's keys; missing or empty file → `dict(DEFAULTS)`; `bc_phase` not in `{"BC-1", "BC-2"}` → `ValueError("bc_phase must be BC-1 or BC-2")`.
- Produces in `bodycomp/store.py` (every function takes an optional path so tests use `tmp_path`):
  - `WEEKLY_FILE`, `MEASUREMENTS_FILE` under `BODYCOMP_DIR`
  - `load_weeks(path=WEEKLY_FILE) -> list[dict]`: stored reports sorted by `week_ending`; `[]` if missing.
  - `save_week(report: dict, path=WEEKLY_FILE) -> None`: replaces any report with the same `week_ending`, keeps sorted, creates the directory.
  - `latest_report(path=WEEKLY_FILE) -> dict | None`
  - `load_measurements(path=MEASUREMENTS_FILE) -> list[dict]`, `append_measurement(entry: dict, path=MEASUREMENTS_FILE) -> None` (same replace-by-`date` rule).

- [ ] **Step 1: Write the failing tests**

```python
def test_bodycomp_dir_is_gitignored():
    # subprocess.run(["git", "check-ignore", "-q", "data/bodycomp/weekly.json"], cwd=REPO).returncode == 0
def test_load_config_defaults_when_missing(tmp_path):    # == DEFAULTS
def test_load_config_defaults_when_empty_file(tmp_path): # file "" -> == DEFAULTS
def test_load_config_overlays_file(tmp_path):            # {"bc_phase": "BC-2", "protein_low_g": 100} -> those two changed, rest default
def test_load_config_rejects_bad_phase(tmp_path):        # {"bc_phase": "2"} -> pytest.raises(ValueError)
def test_save_week_replaces_same_week(tmp_path):         # save two reports with same week_ending -> load_weeks has 1, the second
def test_save_week_keeps_sorted(tmp_path):               # save 2026-11-07 then 2026-10-31 -> order 10-31, 11-07
def test_latest_report_none_when_empty(tmp_path)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_store.py -q`
Expected: FAIL (`ModuleNotFoundError: bodycomp`, and the gitignore check fails).

- [ ] **Step 3: Implement** `.gitignore` line, `config.py`, `store.py`.

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore bodycomp/__init__.py bodycomp/config.py bodycomp/store.py tests/test_bodycomp_store.py
git commit -m "feat(bodycomp): config defaults, gitignored store"
```

---

### Task 2: Sample parsing and weekly metrics

**Files:**
- Create: `bodycomp/checks.py`
- Test: `tests/test_bodycomp_checks.py`

**Interfaces:**
- Produces in `bodycomp/checks.py`:
  - `week_days(week_ending: str) -> list[str]`: the 7 ISO dates Sunday..Saturday ending on `week_ending` (a Saturday). `ValueError` if `week_ending` is not a Saturday.
  - `parse_samples(text: str, days: list[str], how: str) -> list[float | None]`: `text` is newline-separated `YYYY-MM-DD=value` lines. Groups by date into the 7 `days`; `how` is `"mean"` (weight) or `"sum"` (protein, energy, steps). Lines that are blank, malformed, outside `days`, or have value `""`/`0`/non-numeric are ignored. A day with no valid sample is `None`.
  - `sleep_nights(history: list[dict], days: list[str]) -> list[float]`: `run_data.sleep.total_hrs` (> 0) from history entries whose `session.date` is in `days`.
  - `summarize_week(payload: dict, history: list[dict]) -> dict` returning keys: `week_ending`, `avg_weight_lb`, `weight_days`, `avg_protein_g`, `protein_days`, `avg_kcal`, `kcal_days`, `avg_steps`, `steps_days`, `sleep_nights` (count), `short_sleep_nights` (filled in Task 3; set `None` here), `waist_in`, `lift_sessions_done`, `lift_stalled`. Averages are over present days only, rounded to 1 decimal (`avg_steps` to int); `None` when no days present. `waist_in`, `lift_sessions_done`, `lift_stalled` are `None` when missing or `""`; `lift_stalled` accepts `true/false`, `"yes"/"no"`.

- [ ] **Step 1: Write the failing tests** (synthetic values only)

```python
DAYS = week_days("2026-10-31")
def test_week_days_sun_to_sat():           # ["2026-10-25", ..., "2026-10-31"]
def test_week_days_rejects_non_saturday(): # week_days("2026-10-30") raises ValueError
def test_parse_mean_ignores_blanks_zero_junk_and_out_of_window():
    text = "2026-10-25=180.0\n2026-10-25=181.0\n2026-10-26=\n2026-10-27=0\nbad line\n2026-11-01=179\n2026-10-28=179.5"
    assert parse_samples(text, DAYS, "mean") == [180.5, None, None, 179.5, None, None, None]
def test_parse_sum_adds_meals_per_day():   # "2026-10-25=40\n2026-10-25=60\n2026-10-25=50" -> first day 150.0
def test_sleep_nights_from_history():       # 3 entries in window (6.0, 7.2, 0) + 1 outside -> [6.0, 7.2]
def test_summarize_counts_present_days():   # 3 weights present -> weight_days 3, avg over those 3
def test_summarize_optional_fields_blank(): # waist_in "", lift_sessions_done "", lift_stalled "" -> all None
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_checks.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement** the four functions.

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add bodycomp/checks.py tests/test_bodycomp_checks.py
git commit -m "feat(bodycomp): parse Health samples into weekly metrics"
```

---

### Task 3: Rules, report and banner

**Files:**
- Modify: `bodycomp/checks.py`
- Test: `tests/test_bodycomp_checks.py`

**Interfaces:**
- Consumes: `summarize_week`, `sleep_nights`, `week_days` (Task 2); `cycle.week_in_cycle`, `cycle.is_deload_week` (training rework).
- Produces in `bodycomp/checks.py`:
  - `SEVERITY_ORDER = ["RED", "AMBER", "INFO", "OK"]`
  - `RULE_LABELS = {"W1": "weight hold", "W2": "fast loss", "W3": "still dropping", "W4": "flat", "P1": "protein", "P2": "protein low", "P3": "protein per kg", "E1": "calories", "S1": "sleep", "S2": "steps", "L1": "lift stall", "L2": "sessions", "D1": "deload next week"}`
  - `weekly_check(payload: dict, history: list[dict], past_reports: list[dict], config: dict, cycle_start: str) -> dict`. `past_reports` are earlier stored reports (any with the same `week_ending` must be excluded by the caller or here; exclude here). Returns:
    `{"week_ending": str, "bc_phase": str, "bc_week": int | None, "metrics": {...summarize_week..., "delta_lb": float | None, "protein_g_per_kg": float | None, "short_sleep_nights": int}, "results": [{"id": str, "severity": str, "message": str}], "highest": str, "banner": str}`
  - `bc_week` = whole weeks from `bc_phase_start_date` to `week_ending`, plus 1; `None` if the start date is blank.
  - `delta_lb` = this week's `avg_weight_lb` minus the most recent past report's `avg_weight_lb` (both present), rounded to 1 decimal.

Rules (thresholds read from `config`; a rule whose threshold is `None` is skipped; a rule whose data is insufficient yields one `INFO` "insufficient data" result per metric group, ids `W*` for weight and `P*`/`E1` for nutrition):

| ID | Fires when | Severity | Message |
|---|---|---|---|
| W1 | BC-1, `bc_week` is `None` or ≤ `w1_max_bc_week`, baseline known, `abs(avg - baseline) > w1_hold_band_lb` | INFO | `"Weight drifting from baseline"` (else OK `"Weight holding"`) |
| W2 | this week's and the previous `w2_weeks - 1` deltas all `< -w2_fast_loss_lb` | AMBER | `"Falling too fast: add 150-200 kcal/day"` |
| W3 | BC-1, `bc_week` > `w3_early_rise_weeks` (or `None`), `delta_lb < -w3_loss_lb` | AMBER | `"Still dropping: add 150-200 kcal/week until it holds"` |
| W4 | BC-2, this and previous `w4_weeks - 1` deltas all `abs(d) < w4_flat_lb` | INFO | `"Flat: cut about 150 kcal or add 2,000 steps"` |
| P2 | `avg_protein_g < protein_low_g` | RED | `"Protein low: fix before touching calories"` |
| P1 | not P2, `avg_protein_g < protein_avg_min_g` | AMBER | `"Protein under target"` |
| P3 | `protein_g_per_kg < protein_min_g_per_kg` (`g/kg = avg_protein_g / (avg_weight_lb / 2.2046)`, 2 decimals) | INFO | `"Protein {x:.2f} g/kg"` |
| E1 | `avg_kcal < kcal_floor_bc1` (BC-1) or `< kcal_floor_bc2` (BC-2) | AMBER | `"Calories under floor"` |
| S1 | `short_sleep_nights` (nights `< sleep_short_hrs`) `>= sleep_short_nights` | AMBER | `"Sleep short: REDUCE lift volume next week, skip jumps, eat at maintenance"` |
| S2 | `avg_steps < steps_min_avg` | INFO | `"Steps low"` |
| L1 | `lift_stalled is True` | INFO | `"Lift stalled: check sleep and protein, then deload"` |
| L2 | `lift_sessions_done` not `None` and `< lift_sessions_min` | INFO | `"Fewer than 3 lift sessions"` |
| D1 | `is_deload_week(week_in_cycle(cycle_start, today=<week_ending + 2 days>))` | INFO | `"Deload week next week"` |

Banner: `"Weekly: weight {avg:.1f} ({delta:+.1f}), protein {p:.0f} g {pstatus}, steps {steps/1000:.1f}k"`, then, if any non-OK results, `", "` + counts in severity order such as `"1 red (protein low), 1 amber (sleep)"` (labels from `RULE_LABELS`, comma-joined inside the parentheses when several), then `"."`. Substitutions: weight `n/a` when insufficient; `(new)` in place of the delta when there is no delta; `pstatus` = `"OK"` unless P1/P2 fired (then the lowercase severity); protein/steps `n/a` when absent. `highest` = most severe result, `"OK"` if none.

- [ ] **Step 1: Write the failing tests**

Build payload helpers that produce sample text from 7-value lists. Use `cycle_start="2026-10-26"` and week_ending `"2026-10-31"` unless stated (next week is block week 2, so D1 does not fire).

```python
def test_banner_matches_spec_example():
    # weights 180.0 x7, previous report avg 179.8, protein 150 x7, kcal 2100 x7, steps 7100 x7,
    # history sleep 6.0, 6.2, 6.1, 7.5, 7.5 in window, config defaults (absolute thresholds None)
    assert report["banner"] == "Weekly: weight 180.0 (+0.2), protein 150 g OK, steps 7.1k, 1 amber (sleep)."
    assert report["highest"] == "AMBER"
def test_first_week_no_delta():          # no past reports -> delta_lb None, banner starts "Weekly: weight 180.0 (new)", no W2/W3/W4 results
def test_insufficient_weight_days():     # 3 weights -> one W INFO "insufficient data", banner "weight n/a"
def test_insufficient_nutrition_days():  # 4 protein days -> P INFO "insufficient data", no P1/P2/P3
def test_w2_needs_two_consecutive_fast_weeks(): # deltas -1.1 then -1.2 -> W2 AMBER; -1.1 then -0.5 -> no W2; exactly -1.0 -> no W2
def test_w3_only_after_early_window_in_bc1(): # bc_week 2 delta -0.5 -> no W3; bc_week 3 -> W3 AMBER; BC-2 -> no W3
def test_w4_bc2_only_three_flat_weeks():  # BC-2 deltas 0.1, -0.1, 0.0 -> W4 INFO; same deltas in BC-1 -> no W4; one 0.2 -> no W4
def test_w1_uses_config_or_first_bc1_week(): # baseline None, first past BC-1 report avg 180.0, this avg 181.2 -> W1 INFO; config baseline 181.0 -> OK
def test_p2_red_supersedes_p1():          # config protein_low_g 100, protein_avg_min_g 120, avg 95 -> P2 RED, no P1; avg 110 -> P1 AMBER; avg 100 -> P1 AMBER (not P2)
def test_protein_rules_skipped_without_thresholds(): # defaults -> no P1/P2, P3 evaluated
def test_p3_g_per_kg():                   # avg weight 154.32 lb (70 kg), protein 105 -> 1.5 g/kg -> P3 INFO "Protein 1.50 g/kg"
def test_e1_floor_by_phase():             # kcal 1950, floors bc1 2000 / bc2 1900 -> AMBER in BC-1, none in BC-2
def test_s1_threshold_boundary():         # sleep 6.5 counts as not short; three nights 6.4 -> S1
def test_l1_l2_optional():                # lift fields None -> no L1/L2; stalled True, sessions 2 -> both INFO
def test_d1_when_next_week_is_deload():   # cycle_start "2026-09-28", week_ending "2026-10-31" -> Mon 11-02 is cycle week 6 -> D1 INFO; cycle_start "2026-10-26" -> no D1
def test_severity_order_in_banner():      # RED + AMBER + INFO present -> "1 red (...), 1 amber (...), 1 info (...)" in that order
def test_bc_phase_never_changes():        # report["bc_phase"] == config["bc_phase"] even when every rule says hold steady for 12 weeks
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_checks.py -q`
Expected: FAIL (`ImportError: weekly_check`).

- [ ] **Step 3: Implement** `weekly_check` and the banner per the table above.

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add bodycomp/checks.py tests/test_bodycomp_checks.py
git commit -m "feat(bodycomp): weekly rules, severity ranking and banner"
```

---

### Task 4: `POST /bodycomp/weekly` and the Sunday Shortcut branch

**Files:**
- Modify: `server.py` (new route + `_bodycomp_auth()` helper; import `bodycomp.config`, `bodycomp.store`, `bodycomp.checks`)
- Modify: `SHORTCUTS_GUIDE.md` (new section "Sunday weekly check")
- Test: `tests/test_bodycomp_routes.py`

**Interfaces:**
- Consumes: `load_config`, `load_weeks`, `save_week`, `weekly_check`, `server.HISTORY_FILE`, `server.PLAN_STATE_FILE` (`cycle_start_date`).
- Produces:
  - `_bodycomp_auth() -> tuple | None`: returns `(jsonify({"error": "unauthorized"}), 401)` when env `BODYCOMP_TOKEN` is set and header `X-Bodycomp-Token` differs; else `None`. Read the env var at request time (tests set it with `monkeypatch.setenv`).
  - `POST /bodycomp/weekly`: body `{"week_ending", "weight_samples", "protein_samples", "energy_samples", "steps_samples", "waist_in", "lift_sessions_done", "lift_stalled"}` (all sample fields optional strings). 400 `{"error": ...}` for missing/non-Saturday `week_ending`; 500 `{"error": "bc_phase must be BC-1 or BC-2"}` for bad config. On success: `save_week(report)` and return 200 `{"notification": report["banner"], "highest": report["highest"], "flags": ["S1 AMBER", ...]}` (non-OK results, severity order). Must not touch `current_session.json`, `plan_state.json` or the calendar.

- [ ] **Step 1: Write the failing tests** (Flask test client; monkeypatch `bodycomp.store.WEEKLY_FILE`, `bodycomp.config.CONFIG_FILE`, `server.HISTORY_FILE`, `server.PLAN_STATE_FILE`, `server.CURRENT_SESSION_FILE` to `tmp_path`)

```python
def test_weekly_returns_banner_and_stores_report()   # 200, notification starts "Weekly: weight", weekly.json has 1 report
def test_weekly_rerun_same_week_replaces()            # post twice with different weights -> 1 stored report (second); delta computed vs the prior week's report, not vs the first post
def test_weekly_rejects_bad_week_ending()             # "2026-10-30" and missing -> 400
def test_weekly_requires_token_when_configured()      # setenv BODYCOMP_TOKEN=abc: no header -> 401; header abc -> 200
def test_weekly_does_not_touch_daily_files()          # current_session.json and plan_state.json bytes unchanged after the POST
def test_weekly_bad_config_returns_500()              # config {"bc_phase": "3"} -> 500 with the ValueError text
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_routes.py -q`
Expected: FAIL (404 on `/bodycomp/weekly`).

- [ ] **Step 3: Implement** the route and auth helper.

- [ ] **Step 4: Document the Shortcut branch** in `SHORTCUTS_GUIDE.md`, matching the existing step style: after the existing `/healthkit` POST and banner, `If Current Date (formatted EEEE) is Sunday` → for each of Weight, Dietary Protein, Dietary Energy, Steps: `Find Health Samples` (start date in the last 8 days) → `Repeat with Each` → Text `{Start Date yyyy-MM-dd}={Value}` → `Add to Variable` → `Combine Text` with new lines. Latest Waist Circumference sample (optional). Optional `Ask for Input` number "Lift sessions this week?" and `Choose from Menu` "Main lift stalled 3+ weeks?" (Yes/No/Skip). `week_ending` = yesterday as `yyyy-MM-dd`. POST JSON to `{Server URL}/bodycomp/weekly` with header `X-Bodycomp-Token` if set. Show `notification` in a second banner. No personal numbers in the guide.

- [ ] **Step 5: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 6: Commit**

```bash
git add server.py SHORTCUTS_GUIDE.md tests/test_bodycomp_routes.py
git commit -m "feat(bodycomp): POST /bodycomp/weekly and Sunday Shortcut branch"
```

---

### Task 5: Tape measurements and the Claude review packet

**Files:**
- Create: `bodycomp/review_packet.py`
- Modify: `server.py` (two routes)
- Modify: `SHORTCUTS_GUIDE.md` (section "Monthly tape measurements")
- Test: `tests/test_bodycomp_packet.py`, `tests/test_bodycomp_routes.py`

**Interfaces:**
- Consumes: `load_weeks`, `load_measurements`, `append_measurement`, `load_config`, `_bodycomp_auth`.
- Produces:
  - `TAPE_SITES = ["neck_in", "shoulders_in", "chest_in", "waist_in", "arm_in", "thigh_in", "calf_in"]` (from `01-protocol.md` "Tape measure").
  - `POST /bodycomp/measurements`: body `{"date": "YYYY-MM-DD", <any TAPE_SITES>}`. 400 if `date` invalid or no site has a positive number. Stores the present sites plus `shoulder_waist_ratio` (2 decimals) when both `shoulders_in` and `waist_in` are present. Returns 200 `{"status": "ok"}`.
  - `build_packet(weeks: list[dict], measurements: list[dict], config: dict, run_phase: int, today: date = None) -> str` in `review_packet.py`. Markdown, in this order: `# Body-comp review packet`; a header line with `bc_phase`, latest `bc_week`, `run phase {run_phase}`, date range of the included weeks; a "Thresholds" line listing the non-`None` config thresholds; a table of the last 12 weekly reports (columns: Week ending | Avg weight | Delta | Protein | kcal | Steps | Short-sleep nights | Flags); "Tape" with the latest measurement, change vs the previous one and vs the first one, per site; "RED/AMBER events" listing each such result with its week; then this footer verbatim:

    ```
    ---
    Please review: (1) interpret the weight, waist and tape trends; (2) should I hold BC-1/BC-2 or change phase; (3) any calorie change; (4) anything to bring to my doctor.
    ```
  - `GET /bodycomp/review-packet`: auth-guarded; returns `build_packet(...)` with `Content-Type: text/markdown; charset=utf-8`; `run_phase` from `plan_state.json` `phase`.

- [ ] **Step 1: Write the failing tests**

```python
def test_packet_limits_to_12_weeks()             # 15 stored weeks -> table has 12 data rows, newest last
def test_packet_tape_changes()                   # two measurements waist 34.0 then 33.5 -> "waist_in" line shows "-0.5"
def test_packet_lists_red_amber_only()           # results with INFO/OK not listed under "RED/AMBER events"
def test_packet_footer_verbatim()                # packet.endswith(FOOTER)
def test_packet_handles_no_data()                # no weeks, no measurements -> still returns header and footer, no exception
def test_measurements_route_stores_ratio()       # shoulders 46.0 waist 32.0 -> stored shoulder_waist_ratio 1.44
def test_measurements_route_rejects_empty()      # only date -> 400
def test_packet_route_markdown_and_auth()        # 200 text/markdown; with BODYCOMP_TOKEN set and no header -> 401
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_packet.py tests/test_bodycomp_routes.py -q`
Expected: FAIL (`ModuleNotFoundError: bodycomp.review_packet`, 404s).

- [ ] **Step 3: Implement** `review_packet.py` and both routes.

- [ ] **Step 4: Document** a small "Run Coach Tape" Shortcut in `SHORTCUTS_GUIDE.md`: one `Ask for Input` (number) per site, POST to `/bodycomp/measurements`; tell David to add a monthly phone Reminder that opens it.

- [ ] **Step 5: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 6: Commit**

```bash
git add bodycomp/review_packet.py server.py SHORTCUTS_GUIDE.md tests/test_bodycomp_packet.py tests/test_bodycomp_routes.py
git commit -m "feat(bodycomp): tape measurements and review packet"
```

---

### Task 6: Weekly flags into the daily output (read-only)

**Files:**
- Create: `bodycomp/flags.py`
- Modify: `server.py` (strength branch and Saturday run branch of `post_healthkit`)
- Test: `tests/test_bodycomp_flags.py`

**Interfaces:**
- Consumes: `latest_report`; `generate_strength_session(..., skip_jumps=)` and the `trigger`-based `skip_jumps` from the training rework.
- Produces in `bodycomp/flags.py`:
  - `S1_NOTE = "Sleep was short last week: same weight, ~80% of sets, no jumps."`
  - `OPTIONAL_RUN_NOTE = " Optional today: sleep or HRV is down, an easy walk is fine."`
  - `s1_active(report: dict | None, today: date = None) -> bool`: true when `report` has an `S1` result with severity `AMBER` and `week_ending + 1 day <= today <= week_ending + 7 days` (the Sunday after through the next Saturday).
- `server.post_healthkit`, wrapped so any bodycomp error is ignored (daily output must never fail because of bodycomp):
  - Strength days: if `s1_active(latest_report(), date.today())`, pass `skip_jumps=True` and append block `{"name": "Weekly check", "notes": S1_NOTE}` to the session.
  - Saturday (slot B): if `s1_active(...)` or `hrv_ratio < 0.90`, append `OPTIONAL_RUN_NOTE` to the session `summary` (handoff 6.5). Run B stays the default session.
  - Neither note contains digits or bodycomp values. Nothing bodycomp-related is written to `plan_state.json` or passed to `generate_ics`.

- [ ] **Step 1: Write the failing tests**

```python
def test_s1_active_window():                       # week_ending 2026-10-31 S1 AMBER: active 11-01..11-07, not 10-31, not 11-08
def test_s1_inactive_without_amber():              # S1 absent or INFO -> False; report None -> False
def test_strength_day_gets_note_and_no_jumps(...): # server test client, Monday 2026-11-02, stored report with S1 AMBER -> "Weekly check" block with S1_NOTE, no "Jumps" block
def test_saturday_optional_on_low_hrv(...):        # Saturday, no report, hrv_ratio < 0.90 -> summary endswith OPTIONAL_RUN_NOTE
def test_daily_output_survives_corrupt_store(...): # weekly.json contains "not json" -> /healthkit still 200
def test_no_bodycomp_numbers_in_daily_files(...):  # after an S1 Monday POST: current_session.json has no "bodycomp" key and its text contains none of the report's metric values; generate_ics(plan_state) output contains neither S1_NOTE nor "Weekly check"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python3 -m pytest tests/test_bodycomp_flags.py -q`
Expected: FAIL (`ModuleNotFoundError: bodycomp.flags`).

- [ ] **Step 3: Implement** `flags.py` and the two server hooks.

- [ ] **Step 4: Run the full suite** (`python3 -m pytest -q`), expected all pass.

- [ ] **Step 5: Commit**

```bash
git add bodycomp/flags.py server.py tests/test_bodycomp_flags.py
git commit -m "feat(bodycomp): S1 note and optional Saturday run in daily output"
```

---

### Task 7: Docs and Pi deploy

**Files:**
- Modify: `CLAUDE.md` (new "Body-composition weekly check" section: routes, payload, BC-1/BC-2 vs run phase, privacy rules, config keys; add `bodycomp/` to the project tree)

- [ ] **Step 1: Update `CLAUDE.md`** and commit:

```bash
git add CLAUDE.md
git commit -m "docs: body-comp weekly check"
```

- [ ] **Step 2: Privacy check before pushing**

Run: `git ls-files data/bodycomp; git log -p origin/main..HEAD | grep -nE '[0-9]{3}\.[0-9] ?lb|DEXA|lab result' || true`
Expected: no files listed; any grep hits are synthetic test values only (inspect each). Ask David before `git push`.

- [ ] **Step 3: Deploy** `bodycomp/` (four files) and `server.py` to `~/run-coach/` on the Pi via the Terminal SSH method in `~/.claude/CLAUDE.md` (base64, verify `sha256sum`, `.bak`). Create `~/run-coach/data/bodycomp/config.json` on the Pi with `{"bc_phase": "BC-1", "bc_phase_start_date": "2026-10-19", "protein_avg_min_g": <P1>, "protein_low_g": <P2>, "kcal_floor_bc1": <E1 BC-1>, "kcal_floor_bc2": <E1 BC-2>}` with the targets from `health-bootcamp/01-protocol.md` (typed on the Pi only) (protocol values; leave `baseline_weight_lb` out so W1 uses the first BC-1 week). Ask David to restart the service; verify `ActiveEnterTimestamp`.

- [ ] **Step 4: Smoke test on the Pi**: `curl -s -X POST http://localhost:5001/bodycomp/weekly -H 'Content-Type: application/json' -d '{"week_ending":"2026-10-24","weight_samples":"2026-10-20=150"}'` → 200 with a banner containing `weight n/a`; then remove that test report from `data/bodycomp/weekly.json` (keep a `.bak`). David builds the Sunday Shortcut branch from `SHORTCUTS_GUIDE.md`; watch the first real Sunday (Nov 1) output before trusting it.
