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
├── calendar_generator.py         # ICS calendar — through the next deload week, anchored to current Monday
├── cycle.py                      # 6-week cycle math: cycle week, block week, deload, jump prescription
├── reset.py                      # Resets plan_state.json and history.json to defaults
├── bodycomp/                     # Sunday body-comp weekly check (see section below)
│   ├── config.py                 # Threshold defaults; overlaid by gitignored data/bodycomp/config.json
│   ├── store.py                  # data/bodycomp/weekly.json, measurements.json
│   ├── checks.py                 # Samples → metrics → rules (W/P/E/S/L/D) → report + banner
│   ├── flags.py                  # Read-only hooks into daily output (S1 note, optional Saturday)
│   └── review_packet.py          # Markdown packet for a Claude review
├── data/
│   ├── plan_state.json           # Persistent plan state (see schema below)
│   ├── history.json              # One entry per day (last post wins), last 30 kept
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
run, strength (Push/Pull/Full), or rest.

**Shortcut collects:**
- HRV last night (SDNN, ms) — most recent single sample (limit 1, newest first)
- Resting HR — most recent single sample (limit 1, sort by End Date newest first)
- Deep sleep hours — HealthKit filter: Sleep, Type = Deep, last 1 calendar day;
  then per-sample 18-hour check: `now − sample_start < 18 hrs` (positive = past);
  sum of matching durations ÷ 3600
- Total sleep hours — same 18-hour approach for Core, REM, and Asleep categories
  separately, then `Non Deep Sleep Hrs + Sleep Deep Hrs`. "Asleep" catches
  uncategorized sleep (naps etc.) and does not overlap with REM/Core/Deep.
- Training load % — Shortcut opens Fitness Training Load card automatically so user
  can read the %, then Ask for Input prompt; server maps to category
- Today's date (yyyy-MM-dd) — used as dedup key

**Tailscale:** Shortcut auto-connects Tailscale at the start and disconnects at the
end. Pi Tailscale IP is hardcoded in the shortcut as `http://100.109.212.86:5001`.

**HRV 7-day baseline** is computed server-side from the last 7 `hrv_last_night`
values in `history.json`. Accurate after 7 real sessions; until then uses
available history or falls back to last night's value. The shortcut does NOT send
7-day samples — baseline is derived entirely from stored history.

**Effort score** is not sent — Apple doesn't expose workout effort ratings in
Shortcuts. It is not used anywhere in the rule engine.

### Day-of-week routing

The `/healthkit` endpoint determines what session to generate based on
`date.today().weekday()`:

| Day | Type | Rule engine |
|-----|------|-------------|
| Mon (0) | 🏋️ Push | Runs, intensity class applied |
| Tue (1) | 🏃 Run A | Runs, full run session generated |
| Wed (2) | 🏋️ Pull | Runs, intensity class applied |
| Thu (3) | Rest | Runs for readiness only; night logged to history |
| Fri (4) | 🏋️ Full | Runs, intensity class applied |
| Sat (5) | 🏃 Run B | Runs, full run session generated |
| Sun (6) | Rest | Runs for readiness only; night logged to history |

Rest days have no session but still run the rule engine. They return
`{"type": "rest", "readiness": "<decision>", "summary": "Rest Day — walk and mobility", "blocks": []}`
(Sunday: `"Rest Day — meal prep"`)
with a rest-specific banner, and append the night to `history.json` (so HRV baseline,
short-sleep counts and the weekly sleep check see all 7 nights). Plan state and the
calendar are not touched. Because rest days now log, a low-recovery rest day counts
toward the "≥ 2 low-recovery days in a row" deload trigger.

**History holds one entry per day.** Every `/healthkit` path (rest, strength, new
run-day workout) logs through `server._log_history`: a POST whose `session.date`
matches an existing entry replaces it, so re-running the Shortcut on the same morning
(testing) leaves only the last post. History is trimmed to the last 30 entries.

### Intensity class (rule engine decisions)

The rule engine fires every day. Its decision (intensity class) applies to
every session type (on rest days it is reported as readiness only):

- **Runs**: affects duration, zone, session type
- **Strength**: applied as a header flag in the summary (⬆️/⬇️/⛔️); the
  user self-regulates actual load based on the flag
- **Jumps**: skipped on DELOAD/SUPPRESS, and on a REDUCE triggered by HRV or
  sleep (kept when the REDUCE came from run load; see `rule_engine` `trigger`)

Modifiers only make decisions **more conservative**, never less aggressive.
The most conservative signal wins.

**Priority order:**

1. **SUPPRESS** — HRV ratio < 0.70 AND (total sleep < 5 h OR deep sleep < 0.75 h).
   Body needs full rest. Skip or walk only.
2. **DELOAD** — intro week (before block week 1), OR week 6 of the 6-week cycle,
   OR ≥ 2 low-recovery days in a row (SUPPRESS, or REDUCE from HRV/sleep; a load-only
   REDUCE doesn't count — load % already sets the base decision; `rule_engine._is_low_recovery_day`).
   An early DELOAD covers just that day; the DELOAD itself breaks the streak.
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

### 6-week plan cycle (repeats within each phase)

5 build weeks + 1 deload. `cycle.py` is the single source of truth
(`DELOAD_EVERY_N_WEEKS = 6`); everything derives from
`plan_state["cycle_start_date"]` (a Monday). Before that date the week reads
as a deload. Run work-block minutes (add 10 for warm-up/cool-down):

| Phase | Slot | Wk 1 | Wk 2 | Wk 3 | Wk 4 | Wk 5 | Wk 6 (deload) |
|---|---|---|---|---|---|---|---|
| 1 | A easy | 20 | 22 | 24 | 26 | 28 | 20 |
| 1 | B easy | 22 | 24 | 26 | 28 | 30 | 21 |
| 2 | A easy | 25 | 27 | 30 | 32 | 33 | 24 |
| 2 | B progression | 25 | 27 | 30 | 32 | 33 | 24 easy |
| 3 | A easy | 28 | 30 | 33 | 33 | 33 | 24 |
| 3 | B intervals | 2x800 | 2x800 | 2x800 | 2x800 | 2x800 | 24 easy |

Week 6 is always a deload regardless of rule engine decision. The deload run
is `deload_work_min(week 5) = ceil(work_min * 0.70)`, computed once. An early
DELOAD in a build week cuts that week's own duration the same way.

### Weekly schedule (fixed days)

| Day | Session |
|-----|---------|
| Mon | 🏋️ Push (+ jumps) |
| Tue | 🏃‍♂️ Run 1 (Slot A) — always easy Zone 2 |
| Wed | 🏋️ Pull (+ jumps) |
| Thu | Rest |
| Fri | 🏋️ Full (+ jumps) |
| Sat | 🏃‍♂️ Run 2 (Slot B) |
| Sun | Rest |

Deload week: all three lift days stay, prefixed ⛔️, same weight, half the
sets, no jumps.

### Strength session intensity class flags

Strength sessions get a summary flag based on the day's intensity class.
The session notes and calendar list the day's lift menu (`_LIFT_MENU`, from
the health-bootcamp protocol); the user applies the flag to it.

| Decision | Summary prefix | Implied action |
|----------|---------------|----------------|
| BUILD | ⬆️ | Full planned load ("Full planned session." — not heavier) |
| HOLD | (none) | Follow planned load |
| REDUCE | ⬇️ | Same weight, ~65% of sets (protocol: cut 30–40%) |
| DELOAD | ⛔️ | Same weight, half the sets |
| SUPPRESS | ⛔️ | Skip or very easy only |

---

## Jump block (Push/Pull/Full)

Countermovement jumps right after the warm-up on every lift day. Not logged;
the prescription in the session and calendar is the benchmark.

| Jump-progression week | Per lift day | Weekly target |
|---|---|---|
| 1–4 | 2 x 10 | 60 |
| 5+ | 3 x 10 | 90 |
| Deload / pre-block week | none | 0 |

The progression week advances only in build weeks
(`cycle.jump_prescription`), so deload weeks pause it.

---

## `/healthkit` response

Every `/healthkit` response includes:
- The session JSON (type, summary, blocks)
- A top-level `notification` field for the iOS Shortcut banner

Text is worded per session kind (`server._LIFT_NOTIFICATIONS` / `_RUN_NOTIFICATIONS` /
`_REST_NOTIFICATIONS`, built by `server._notification`):

| Decision | Lift day (Mon/Wed/Fri) | Run day (Tue/Sat) |
|----------|------------------------|-------------------|
| SUPPRESS | ⛔️ Recovery is low — no lifting today. Walk only. | ⛔️ Recovery is low — no running today. Easy walk or skip. |
| DELOAD | ⛔️ Deload week — same weight, half the sets, no jumps. | ⛔️ Deload week — easy Zone 2, about 70% of the usual time. |
| REDUCE | ⬇️ Pull back today — same weight, about 65% of your sets. | ⬇️ Pull back today — same easy effort, about 15% shorter. |
| HOLD | ✅ On track — follow today's lift plan. | ✅ On track — run as planned. |
| BUILD | ⬆️ Good recovery — full planned session today. | ⬆️ Good recovery — run about 10% longer today. |

- Intro week (before block week 1, e.g. Oct 19): "Deload week" reads "Intro week", and the
  rule engine reason is `Intro week (deload volume)` (trigger `intro_week`), not week 6.
- Lift day where jumps were skipped for recovery (REDUCE from HRV/sleep): ` Skip jumps.` appended.
- Rest days: 🛌 Rest day — recovery on track. / good recovery. / a bit low, take it easy. /
  low, keep today fully easy. / deload (or intro) week, keep recovering. (by decision)

The Shortcut reads both `decision_reason` and `notification` from the response
and concatenates them in the banner body (e.g. "Training load steady ✅ On track — run
as planned.").

---

## Body-composition weekly check

Spec: `health-bootcamp/06-weekly-checkin-handoff.md` (supersedes 03 sections 3–5, 8).
Sunday-morning branch of the daily Shortcut posts 7 daily values (Sun–Sat ending
yesterday) for weight, protein, dietary energy, steps and sleep to
`POST /bodycomp/weekly`. Returns a banner such as
`Weekly: weight 180.0 (+0.2), protein OK, steps 7.1k, 1 amber (sleep).` and sends a
Telegram message (tier from `telegram_detail`, default `trends`).

- **Phases:** `bc_phase` `"BC-1"` (maintenance build) / `"BC-2"` (deficit) in
  `data/bodycomp/config.json`. Not run-coach's run `phase` (1/2/3). Never
  advanced by code.
- **Rules:** W1 hold, W2 fast loss, W3 still dropping (BC-1), W4 flat (BC-2),
  P1/P2/P3 protein, E1 calorie floor, S1 short sleep, S2 steps, L2 sessions
  (optional input), D1 deload next week. Severity RED > AMBER > INFO > OK. A
  missing personal threshold reports "not configured".
- **Routes:** `/bodycomp/weekly`, `/bodycomp/report/latest`, `/bodycomp/measurements`
  (monthly tape), `/bodycomp/review-packet`. All require header `X-Bodycomp-Secret`
  matching env `BODYCOMP_SECRET` (503 if unset). Telegram env: `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID`. A Telegram failure never fails the route.
- **Sleep:** if `sleep_hrs_daily` is left out or empty, the server fills it from
  `history.json` (one `sleep.total_hrs` per `session.date` in Sun–Sat, last post of a day
  wins, 0 skipped). The Sunday Shortcut sends no sleep. Dry runs report `sleep_source`
  and are kept in `data/bodycomp/last_dry_run.json` even when rejected (400).
- **Telegram allowlist:** `bodycomp/telegram.build_message` accepts only week_ending,
  flags, protein status, weight delta, protein/steps/sleep averages. Never absolute
  weight, calories, baseline, height or thresholds.
- **Daily hooks:** S1 AMBER → next week's lift days get the fixed `S1_NOTE` and no
  jumps, and Saturday's run gets the "optional" note (also given on HRV ratio < 0.90).
  **Deliberate exceptions (David, 2026-10-16):** that fixed, number-free S1 sentence may
  appear in the `/healthkit` response and `current_session.json`, and on an S1 week the
  calendar's lift events read the generic `Jumps: skip this week.` (no reason given, so it
  reveals no more than a recovery skip). The calendar learns the S1 week by reading the
  latest report at generation time; nothing from bodycomp is stored in
  `current_session.json` beyond `S1_NOTE`, or in `plan_state.json`.
- **Open-question decisions (2026-10-16):** `lift_sessions_done` stays optional (L2
  skipped without it); `/bodycomp/measurements` kept; `baseline_weight_lb` set on the Pi
  after the intro week (average for the week ending Sat Oct 31), W1 "not configured" until then.
- **Privacy (repo is public):** `data/bodycomp/` is gitignored. Personal thresholds
  (protein/kcal floors, baseline weight) live only in the Pi's config. Tests use
  clearly synthetic values.

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
  "cycle_start_date":            "2026-10-26"
}
```

`last_execution_*` fields are written after every `/healthkit` POST (including
rest days) and used by `calendar_generator.py` to show the actual decision
on today's calendar run event. `last_run_a/b_*` fields track the most recent
execution decision per run slot independently.

---

## Calendar integration

The server generates a cycle-anchored ICS calendar and pushes it to
GitHub Pages after every `/healthkit` POST.

| Item | Value |
|------|-------|
| GitHub repo | `K-David-360/run-coach` |
| Calendar file | `calendar-rc7f4a2b.ics` (obscure name — repo is public) |
| Subscribe URL | `https://k-david-360.github.io/run-coach/calendar-rc7f4a2b.ics` |
| Local endpoint | `GET http://localhost:5001/calendar.ics` |

**Calendar window:** `max(4, 6 - this_cycle_week + 1)` weeks, anchored to the
current week's Monday, so it always reaches the next deload week. Minimum 4
weeks always shown.

**What the calendar contains:**
- Run events on Tue/Sat — base plan (HOLD) for future, actual decision for today
- Strength events on Mon/Wed/Fri — Push/Pull/Full with lift menu, ~45–55 min,
  and the jump line (sets and weekly target); intensity flag on today's event
- All deload week events prefixed with ⛔️ (the intro week reads "Intro Week Run" /
  "none this week (intro week)"; deload lift days say "Shorter session: half the sets.")
- Saturday run events end with the protocol's optional line (easy Zone 2 or a 30–45 min
  incline walk; skip if sleep or HRV is down)
- SUPPRESS today: run event is "🚶 Recovery Walk" (Zone 1 walk blocks, as in the session);
  lift event shows only the no-lifting note
- Decision emoji prefixes: ⬆️ BUILD · ⬇️ REDUCE · ⛔️ SUPPRESS/DELOAD

**Triggering a calendar push manually:**
```bash
curl -X POST http://raspberrypi.local:5001/healthkit \
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
in `plan_generator.py`. The 6-week cycle and jumps continue unaffected through the phase change.

---

## Infrastructure

- **Pi address**: `raspberrypi.local` (mDNS; LAN IP changes) / Tailscale `100.109.212.86`
- **Service**: `sudo systemctl restart run-coach` / `systemctl status run-coach`
- **Service file**: `/etc/systemd/system/run-coach.service`
- **Run-coach path on Pi**: `/home/pi/run-coach/` (git checkout of `origin/main`; cron `deploy.sh`
  pulls every minute and tries to restart. The restart needs David's sudo, so after a push he runs it.)

### Deploying changes to Pi

Direct `scp`/`ssh` from the Mac usually fails. Use the Terminal SSH session method in
`~/.claude/CLAUDE.md` (`pi@raspberrypi.local`; base64 transfer, `sha256sum` check,
timestamped `.bak`). David runs `sudo systemctl restart run-coach`; check it with
`systemctl show run-coach -p ActiveEnterTimestamp`.

Run `python3 reset.py` any time to wipe history and restart from week 1, slot A.

---

## Current state

- **Server**: running on Pi, systemd service, auto-starts on boot
- **iOS Shortcut**: fires daily (not just on run days); notification fires correctly
- **Calendar**: live, pushes to GitHub after every POST; window reaches the next deload
- **Rule engine**: fires every day (readiness only on rest days); SUPPRESS/DELOAD/REDUCE/HOLD/BUILD
- **Phase**: 1 (both runs Zone 2 easy). Advance to 2 after LTHR field test.
- **Strength**: Push/Pull/Full with jump block; 6-week cycle from `cycle_start_date` 2026-10-26
- **HRV baseline**: builds from history — accurate after 7 real sessions
- **Resting HR baseline**: builds from history — modifier active after 3+ sessions
- **Plan state**: Pi `cycle_start_date` set to 2026-10-26 at deploy (week of Oct 19 = pre-block deload)

---

## Remaining tasks

### Code

1. **Manual "rough week" override** — a way to shift the recommendation one
   level more conservative when life stress is high. Proposed: `/note` endpoint
   stub already exists; could accept `{"stress": "high"}` to set a flag for
   7 days.

### Completed

- ~~`POST /calendar/push`~~ — exists in `server.py`.
- ~~Galpin deload protocol alignment~~ — Deload/reduce tiers now cut volume only,
  never intensity, per Huberman Lab/Galpin guest series (`docs/deload_protocol.md`).
  Runs: DELOAD = same zone, 70% duration; REDUCE = same zone, 85% duration
  (already correct, no change needed). Strength: DELOAD = same weight, 50% of
  sets; REDUCE = same weight, ~80% of sets, now ~65% (2026-10-16) (both previously worded as load/weight
  cuts — fixed 2026-06-29 and 2026-07-06 respectively). Dead `_deload_blocks()`
  helper removed as part of this work.
- ~~History window fix~~ — `_count_nights_below` now uses a 7-calendar-day lookback
  instead of last-7-entries. Two misread entries (Jun 09 1.78h, Jun 13 4.44h) deleted
  from `history.json`. DELOAD cleared 2026-06-27.
- ~~Resting HR rule engine signal~~ — Done
- ~~Pi deployment~~ — Done
- ~~Tailscale~~ — Done
- ~~Systemd service~~ — Done
- ~~KB Breathing Ladder (Wednesday finisher)~~ — Done
- ~~Daily rule engine (all non-rest days, not just runs)~~ — Done
- ~~Strength session intensity class~~ — Done
- ~~Calendar anchored to current Monday (not next)~~ — Done
- ~~KB-phase-anchored calendar window~~ — Done
- ~~Training rework (2026-10)~~ — 6-week cycle (`cycle.py`), Push/Pull/Full with
  jump block, KB ladder removed, deload run computed once from week 5.
- ~~Calendar accuracy test fixtures anchored to stale dates~~ — `generate_ics()`
  now accepts an optional `today` param (same `today=None` convention as
  `_most_recent_monday`/`_week_from_cycle_start`); tests in
  `test_calendar_accuracy.py` pass a fixed anchor Monday instead of hardcoded
  `2026-06-xx` strings that fell outside the rolling calendar window as real
  time passed.

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
- **Rule engine fires every day** — the intensity class applies to all
  session types (runs, strength, jumps). Rest days report it as readiness
  and log the night, but generate no session and leave plan state alone.
- **Strength sessions carry the lift menu** — Push/Pull/Full from the
  health-bootcamp protocol, plus the intensity flag and jump line.
- **One counter** — deload cycle, run plan week and jump progression all derive
  from `cycle_start_date` via `cycle.py`; `DELOAD_EVERY_N_WEEKS` is one line.
- **KB ladder removed (2026-10)** — legacy `kb_*` keys in an existing
  `plan_state.json` are ignored.
- **Calendar anchored to current Monday** — restarting mid-week shows the
  current week, not next week.
- **Calendar window reaches the next deload** — `max(4, 6 - cycle_week + 1)` weeks.
- **Future calendar events show HOLD** — rule engine needs live recovery data.
  Only today's event is updated with the actual decision via `last_session_*`.
- **LTHR field test auto-scheduled** — appears in calendar at run 10, urgent
  at run 14, disappears when phase advances. No manual reminder needed.
- **Date-dependent functions accept `today: date = None`** — `_most_recent_monday`,
  `_week_from_cycle_start`, and `generate_ics` all default to `date.today()`
  but accept an explicit `today` override. Tests pass a fixed date instead of
  hardcoding absolute date strings, so fixtures don't go stale as real time
  passes relative to rolling windows (e.g. the calendar's Monday-anchored
  window that reaches the next deload).
- **Port 5001** — macOS AirPlay Receiver occupies 5000.
- **`_safe_float()` helper** — Shortcuts sends empty strings for missing
  health values; bare `float()` crashes on `""`.
- **Obscure ICS filename** — repo is public (GitHub Pages free tier), but
  `calendar-rc7f4a2b.ics` is unguessable. Workout data only, no sensitive info.
