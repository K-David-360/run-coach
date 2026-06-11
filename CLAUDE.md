# Run Coach — Project Handoff

Personal running coach server for Raspberry Pi. Reads Apple HealthKit data
via an iOS Shortcut, runs a rule engine to decide training load adjustments,
and returns a structured workout session.

---

## Project structure

```
run-coach/
├── server.py                     # Flask API — main entry point
├── rule_engine.py                # Decision engine: SUPPRESS / DELOAD / REDUCE / HOLD / BUILD
├── plan_generator.py             # Builds session blocks from decision + plan state
├── calendar_generator.py         # ICS calendar — full KB Phase 1 arc, anchored to current Monday
├── reset.py                      # Resets plan_state.json and history.json to defaults
├── data/
│   ├── plan_state.json           # Persistent plan state (see schema below)
│   ├── history.json              # Log of every processed session
│   └── current_session.json      # Most recent session (written on every POST)
└── SHORTCUTS_GUIDE.md            # Step-by-step iOS Shortcut build guide
```

Dependencies: `pip3 install flask requests python-dotenv`

Start server: `cd ~/Documents/Claude/run-coach && python3 server.py`
Default port: **5001** (5000 is taken by AirPlay Receiver on Mac).

---

## Terminology

| Term | Meaning |
|------|---------|
| **execution** / **daily execution** | When the iOS Shortcut fires and the server processes it (happens every morning) |
| **run day** | Tuesday (slot A) or Saturday (slot B) — a calendar slot, not a confirmed running workout |
| **running workout** | A physical run the user actually performed |
| **`total_runs`** | Count of run-day executions (Tue/Sat fires), NOT running workouts completed |

The server has zero knowledge of actual workout completion. All decisions are driven by passive health metrics.

---

## How it works

### iOS Shortcut → server pipeline

The Shortcut fires **every morning** (not just on run days). It pulls data
from HealthKit and POSTs a flat JSON payload to `/healthkit`. The server
determines the day of the week and returns the appropriate session type —
run, strength, KB ladder, or rest.

**Shortcut collects:**
- HRV last night (SDNN, ms) — most recent single sample (limit 1, newest first)
- Deep sleep hours — sum of Deep category samples, last 18 hrs
- Total sleep hours — sum of Core + Deep + REM, last 18 hrs
- Training load % — raw percentage Apple shows in Fitness → Activity → Training Load
  (user types the number, e.g. -21 or 46; server maps to category)
- Today's date (yyyy-MM-dd) — used as dedup key

**HRV 7-day baseline** is computed server-side from the last 7 `hrv_last_night`
values in `history.json`. Accurate after 7 real sessions; until then uses
available history or falls back to last night's value.

**Effort score** is not sent — Apple doesn't expose workout effort ratings in
Shortcuts. It is not used anywhere in the rule engine.

### Day-of-week routing

The `/healthkit` endpoint determines what session to generate based on
`date.today().weekday()`:

| Day | Type | Rule engine |
|-----|------|-------------|
| Mon (0) | 🏋️ Lower Body | Runs, intensity class applied |
| Tue (1) | 🏃 Run A | Runs, full run session generated |
| Wed (2) | 🏋️ Upper Body + KB Ladder | Runs, KB advancement logic |
| Thu (3) | Rest | Skipped — returns rest response immediately |
| Fri (4) | 🏋️ Full Body | Runs, intensity class applied |
| Sat (5) | 🏃 Run B | Runs, full run session generated |
| Sun (6) | Rest | Skipped — returns rest response immediately |

Rest days skip health data processing entirely and return:
```json
{"type": "rest", "summary": "Rest Day — No Session", "blocks": []}
```

### Intensity class (rule engine decisions)

The rule engine fires on all non-rest days. Its decision (intensity class)
applies to every session type:

- **Runs**: affects duration, zone, session type
- **Strength**: applied as a header flag in the summary (⬆️/⬇️/⛔️); the
  user self-regulates actual load based on the flag
- **KB Ladder**: affects peak rung (see KB section below)

Modifiers only make decisions **more conservative**, never less aggressive.
The most conservative signal wins.

**Priority order:**

1. **SUPPRESS** — HRV ratio < 0.70 AND (total sleep < 5 h OR deep sleep < 0.75 h).
   Body needs full rest. Skip or walk only.
2. **DELOAD** — week 4 of the 4-week cycle, OR ≥ 2 consecutive suppresses,
   OR ≥ 2 nights below 5 h in the last 7 history entries,
   OR load is `well_above` (ACWR > 1.5 equivalent).
3. **Base signal from load** (proxy for ACWR):
   - `above` → REDUCE
   - `steady` → HOLD
   - `below` / `well_below` → BUILD
4. **HRV modifier** — ratio < 0.90: caps BUILD → HOLD.
5. **Sleep modifiers**:
   - < 6 h: shifts one level more conservative (BUILD→HOLD, HOLD→REDUCE)
   - 6–7.5 h: caps BUILD → HOLD
   - ≥ 7.5 h: no change
6. **Resting HR modifier** — 2+ of last 7 history entries with resting HR ≥
   personal baseline + 5 bpm: caps BUILD → HOLD. Baseline = mean of all
   available `resting_hr` values; skipped until 3+ data points exist.
7. **HOLD** — default fallback.

### Training phases (runs)

Phase is stored in `plan_state.json` as `"phase"`. Advance manually after
the LTHR field test.

| Phase | Duration | Run A | Run B |
|-------|----------|-------|-------|
| 1 | Weeks 1–6 | Easy Zone 2 | Easy Zone 2 |
| 2 | Weeks 7–12 | Easy Zone 2 | Progression run (Zone 2 → Zone 3 finish) |
| 3 | Weeks 13–20 | Easy Zone 2 | Intervals (400–800 m) |

### 4-week plan cycle (repeats within each phase)

| Week | Slot A (Tuesday) | Slot B (Saturday) |
|------|-----------------|-------------------|
| 1 | Easy 28 min | Easy 30 min |
| 2 | Easy 30 min | Easy 33 min |
| 3 | Easy 33 min | Easy 35 min |
| 4 | Deload 20 min | Deload 20 min |

Week 4 is always a deload regardless of rule engine decision.
`run_in_week` tracks slot (0 = A next, 1 = B next), resets after 2 runs
and increments `current_week` (cycles 1→2→3→4→1).

### Weekly schedule (fixed days)

| Day | Session |
|-----|---------|
| Mon | 🏋️ Lower Body strength |
| Tue | 🏃‍♂️ Run 1 (Slot A) |
| Wed | 🏋️ Upper Body + KB Ladder |
| Thu | Rest |
| Fri | 🏋️ Full Body |
| Sat | 🏃‍♂️ Run 2 (Slot B) |
| Sun | Rest |

Week 4 deload: Mon → Full Body (no lower), Wed → Upper (lighter), Fri dropped.

### Strength session intensity class flags

Strength sessions get a summary flag based on the day's intensity class.
No specific exercise splits are generated — the user applies load based on
the flag.

| Decision | Summary prefix | Implied action |
|----------|---------------|----------------|
| BUILD | ⬆️ | Full planned load |
| HOLD | (none) | Follow planned load |
| REDUCE | ⬇️ | ~80% of planned load |
| DELOAD | ⛔️ | Light load, cut sets |
| SUPPRESS | ⛔️ | Skip or very easy only |

---

## KB Breathing Ladder (Wednesday finisher)

### Format

Breathing ladder as a finisher after upper body + core. Structure:
1 swing → 1 breath → 2 swings → 2 breaths → ... → peak → ... → 1 swing.
Breaths are the rest protocol (autoregulated). Bell weight fixed within a cycle.

### Phase 1 progression

| kb_weeks_elapsed | Peak rung | Total swings |
|-----------------|-----------|--------------|
| 0–2 | 10 | 100 |
| 3–5 | 15 | 225 |
| 6–8 | 20 | 400 |
| 9+ | resets to 0 | heavier bell flagged in session notes |

`kb_peak_from_weeks(weeks_elapsed)` in `plan_generator.py` computes the peak.

### Intensity class modulation

| Decision | kb_weeks_elapsed | Swings |
|----------|-----------------|--------|
| BUILD | +1 | Scheduled peak |
| HOLD | +1 | Scheduled peak |
| REDUCE | no change | Peak − 2 rungs (min 5) |
| DELOAD | no change | Omitted entirely |
| SUPPRESS | no change | Omitted entirely |

`kb_weeks_elapsed` only advances on BUILD or HOLD, and only once per Wednesday
(guarded by `last_session_date != today`).

### State tracking

`kb_weeks_elapsed` and `kb_peak_rung` are persisted in `plan_state.json`.
The calendar description for Wednesday always shows the current scheduled peak.
`current_session.json` on Wednesday shows the intensity-adjusted peak.

---

## `/healthkit` response

Every `/healthkit` response includes:
- The session JSON (type, summary, blocks)
- A top-level `notification` field for the iOS Shortcut banner

| Decision | Notification text |
|----------|------------------|
| SUPPRESS | ⛔️ Rest day — your body needs recovery. Skip training today. |
| DELOAD | ⛔️ Deload week — reduced load across all sessions. Keep it easy. |
| REDUCE | ⬇️ Pull back today — do a shorter, easier version of your session. |
| HOLD | ✅ On track — follow today's plan as scheduled. |
| BUILD | ⬆️ Good recovery — you can push a little harder today. |
| REST | 🛌 Rest day — no training today. |

The Shortcut reads `notification` (not `summary`) for the banner — generic
enough to apply on any day type.

---

## API endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/healthkit` | Main endpoint — iOS Shortcut posts here daily |
| GET | `/session` | Returns last generated session |
| GET | `/test` | Returns static dummy session (server alive check) |
| POST | `/run` | Legacy nested-JSON endpoint (kept for curl testing) |
| POST | `/note` | Stub, 501 not implemented |

### `/healthkit` expected payload

```json
{
  "last_workout_date": "2026-05-10",
  "hrv_last_night":    73.0,
  "sleep_deep_hrs":    1.0,
  "sleep_total_hrs":   7.2,
  "resting_hr":        52.0,
  "load_pct":          -21
}
```

All float fields are safely converted — empty strings from Shortcuts are
treated as 0. `load_pct` (Apple's raw %) is mapped to a category by the
server. Falls back to `load_classification` label if `load_pct` not present.

### `plan_state.json` schema

```json
{
  "current_week":                1,
  "run_in_week":                 0,
  "consecutive_suppress":        0,
  "total_runs":                  0,
  "phase":                       1,
  "last_processed_workout_date": "",
  "last_execution_date":         "",
  "last_execution_type":         "",
  "last_execution_decision":     "",
  "last_run_a_execution_date":   "",
  "last_run_a_decision":         "",
  "last_run_b_execution_date":   "",
  "last_run_b_decision":         "",
  "kb_weeks_elapsed":            0,
  "kb_peak_rung":                10
}
```

`last_execution_*` fields are written after every `/healthkit` POST (including
rest days) and used by `calendar_generator.py` to show the actual decision
on today's calendar run event. `last_run_a/b_*` fields track the most recent
execution decision per run slot independently.

---

## Calendar integration

The server generates a KB-phase-anchored ICS calendar and pushes it to
GitHub Pages after every `/healthkit` POST.

| Item | Value |
|------|-------|
| GitHub repo | `K-David-360/run-coach` |
| Calendar file | `calendar-rc7f4a2b.ics` (obscure name — repo is public) |
| Subscribe URL | `https://k-david-360.github.io/run-coach/calendar-rc7f4a2b.ics` |
| Local endpoint | `GET http://localhost:5001/calendar.ics` |

**Calendar window:** `max(4, 9 - kb_weeks_elapsed)` weeks, anchored to the
current week's Monday. Shows the full KB Phase 1 arc at the start; shrinks
as the phase progresses. Minimum 4 weeks always shown.

**What the calendar contains:**
- Run events on Tue/Sat — base plan (HOLD) for future, actual decision for today
- Strength events on Mon/Wed/Fri — labelled by type, intensity flag on today's event
- Wednesday events include KB Breathing Ladder description with current peak
- All deload week events prefixed with ⛔️
- Decision emoji prefixes: ⬆️ BUILD · ⬇️ REDUCE · ⛔️ SUPPRESS/DELOAD

**Triggering a calendar push manually:**
```bash
curl -X POST http://192.168.1.136:5001/healthkit \
  -H "Content-Type: application/json" \
  -d '{"hrv_last_night":55,"sleep_total_hrs":7.5,"sleep_deep_hrs":1.5,"load_pct":0}'
```

**LTHR field test auto-scheduling:**
- When `total_runs >= 10` and `phase == 1`, a `🔬 LTHR Field Test` event
  replaces Run 2 (Saturday) two weeks out
- Becomes urgent (moves to next Saturday) at `total_runs >= 14`
- Disappears once `phase` is set to 2

**First-time setup:**
1. Create `.env` in the project root with `GITHUB_TOKEN=ghp_...`
2. In the `K-David-360/run-coach` repo: add a `README.md`, then enable Pages
   in Settings → Pages → branch: `main`, root `/`
3. POST to `/healthkit` — this pushes `calendar-rc7f4a2b.ics` to the repo
4. On iPhone: Calendar app → Add Account → Other → Add Subscribed Calendar →
   paste the subscribe URL above

---

## LTHR field test

**When:** Auto-appears in calendar after run 10 (week 5). Do it when Zone 2
runs feel genuinely easy at current pace.

**Protocol:**
1. 10 min easy warm up
2. 30 min all-out sustained effort (hardest pace you can hold the full 30 min)
3. 5 min walking cool down
4. Average HR of the **final 20 min** = your measured LTHR

**After the test:**
1. Recalculate zone boundaries from the new LTHR value
2. Update Apple Watch custom zone breakpoints manually
3. Set `"phase": 2` in `data/plan_state.json` — plan generator immediately
   switches Run B to progression runs

No code changes required — phases 2 and 3 plan tables are already defined
in `plan_generator.py`. KB ladder continues unaffected through the phase change.

---

## Infrastructure

- **Pi address**: `192.168.1.136` (local) / Tailscale IP (remote)
- **Service**: `sudo systemctl restart run-coach` / `systemctl status run-coach`
- **Service file**: `/etc/systemd/system/run-coach.service`
- **Run-coach path on Pi**: `/home/pi/run-coach/`

### Deploying changes to Pi

```bash
scp /Users/David/Documents/Claude/run-coach/plan_generator.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/server.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/calendar_generator.py pi@192.168.1.136:~/run-coach/
scp /Users/David/Documents/Claude/run-coach/data/plan_state.json pi@192.168.1.136:~/run-coach/data/

ssh pi@192.168.1.136 'sudo systemctl restart run-coach && systemctl status run-coach'
```

Run `python3 reset.py` any time to wipe history and restart from week 1, slot A.

---

## Current state

- **Server**: running on Pi, systemd service, auto-starts on boot
- **iOS Shortcut**: fires daily (not just on run days); notification fires correctly
- **Calendar**: live, pushes to GitHub after every POST; KB-anchored window
- **Rule engine**: fires every non-rest day; SUPPRESS/DELOAD/REDUCE/HOLD/BUILD
- **Phase**: 1 (both runs Zone 2 easy). Advance to 2 after LTHR field test.
- **KB Ladder**: Phase 1 active — peak 10 (weeks 1–3), 15 (weeks 4–6), 20 (weeks 7–9)
- **HRV baseline**: builds from history — accurate after 7 real sessions
- **Resting HR baseline**: builds from history — modifier active after 3+ sessions
- **Plan state**: reset — week 1, run 0, 0 total runs, kb_weeks_elapsed 0 (May 2026)

---

## Remaining tasks

### Code

1. **Manual "rough week" override** — a way to shift the recommendation one
   level more conservative when life stress is high. Proposed: `/note` endpoint
   stub already exists; could accept `{"stress": "high"}` to set a flag for
   7 days.

2. **`POST /calendar/push`** — dedicated endpoint to regenerate and push the
   calendar without submitting health data. Useful after deploying code changes.

### Completed

- ~~Resting HR rule engine signal~~ — Done
- ~~Pi deployment~~ — Done
- ~~Tailscale~~ — Done
- ~~Systemd service~~ — Done
- ~~KB Breathing Ladder (Wednesday finisher)~~ — Done
- ~~Daily rule engine (all non-rest days, not just runs)~~ — Done
- ~~Strength session intensity class~~ — Done
- ~~Calendar anchored to current Monday (not next)~~ — Done
- ~~KB-phase-anchored calendar window~~ — Done

---

## Key design decisions

- **Flat JSON payload** — nested JSON is hard to construct in the Shortcuts
  app. The `/healthkit` endpoint normalises it internally.
- **Date-string dedup** — "Find Workouts" is not available in Shortcuts on
  this device. Today's date caps at one plan advancement per calendar day.
- **Load % instead of category** — user reads the raw % from Fitness app and
  types it into an Ask for Input step. Server maps to category: ±20% = steady,
  >+50% = well above, <-50% = well below, ±20–50% = above/below.
- **Effort score removed** — not accessible in Shortcuts. Rule engine uses
  HRV and sleep exclusively.
- **Modifiers only make decisions more conservative** — load drives the base
  decision (ACWR proxy); HRV and sleep can only pull it down, never up.
- **Phase system** — plan table is phase-aware. Phase 1 = both runs Zone 2
  easy (no intensity). Phases 2 and 3 tables already defined, activated by
  setting `"phase"` in `plan_state.json` after LTHR field test.
- **Rule engine fires every non-rest day** — the intensity class applies to
  all session types (runs, strength, KB ladder), not just runs. Rest days
  short-circuit before health data processing.
- **Strength sessions have no prescribed splits** — only the intensity class
  flag is generated. The user applies it to their own program.
- **KB state advances on BUILD and HOLD** — HOLD means steady training
  continues and the ladder can progress. REDUCE and DELOAD/SUPPRESS pause
  advancement without resetting it.
- **KB peak is independent of run phase** — the KB 9-week progression runs
  through phase transitions. LTHR test and phase change don't affect it.
- **Calendar anchored to current Monday** — restarting mid-week shows the
  current week, not next week.
- **Calendar window = KB phase arc** — `max(4, 9 - kb_weeks_elapsed)` weeks.
  Shows the full remaining KB Phase 1 at a glance.
- **Future calendar events show HOLD** — rule engine needs live recovery data.
  Only today's event is updated with the actual decision via `last_session_*`.
- **LTHR field test auto-scheduled** — appears in calendar at run 10, urgent
  at run 14, disappears when phase advances. No manual reminder needed.
- **Port 5001** — macOS AirPlay Receiver occupies 5000.
- **`_safe_float()` helper** — Shortcuts sends empty strings for missing
  health values; bare `float()` crashes on `""`.
- **Obscure ICS filename** — repo is public (GitHub Pages free tier), but
  `calendar-rc7f4a2b.ics` is unguessable. Workout data only, no sensitive info.
