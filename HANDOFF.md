# Run Coach — Outstanding Items (2026-10-16)

State at handoff: the training rework (6-week cycle, Push/Pull/Full, jumps, KB ladder removed) and the
body-comp weekly check (spec `health-bootcamp/06-weekly-checkin-handoff.md`) are merged into local
`main`. 146 tests pass (`python3 -m pytest -q`). **Nothing is pushed to GitHub and nothing is deployed
to the Pi.** The Pi still runs the old 4-week / KB-ladder code.

> This repo is public. Keep personal numbers (weight, height, protein/calorie targets, lab or DEXA
> values, secrets) out of this file and every tracked file.

---

## 1. Blocking before `git push`

- [x] **Git history:** David accepted the older commits going public as-is (2026-10-16). No rewrite.
- [ ] **Sync with GitHub.** Local `main` is 39 commits ahead of `origin/main` and 101 behind. The
  101 are all the Pi's automatic "Update run coach calendar" commits. Run `git fetch origin && git
  merge origin/main`, and on conflict take the remote calendar file (`git checkout --theirs
  calendar-rc7f4a2b.ics`). Run the tests, then push (ask David first).

## 2. Pi deploy — done 2026-10-16

- Pi `~/run-coach` is now a clean checkout of `origin/main`. **Cron runs `deploy.sh` every minute
  (`git pull` + `sudo systemctl restart`)**; the restart fails without a password, so after a push
  David runs `sudo systemctl restart run-coach`. Pre-deploy backup: `~/run-coach-backup-20261016005539`.
- `plan_state.json` restored from that backup with `cycle_start_date` 2026-10-26 (the rest of
  this week and the week of Oct 19 read as deload). Pi plan state is **phase 2**.
- `.env` (Pi and Mac): `BODYCOMP_SECRET` (Pi only, generated on the Pi), `TELEGRAM_BOT_TOKEN`,
  `TELEGRAM_CHAT_ID` (bot @healthbootcamp_bot). `data/bodycomp/config.json` on the Pi.
- Smoke tests passed: calendar (deload through Oct 24, Push weekly target 60 on Oct 26, no KB);
  synthetic `/bodycomp/weekly` → 200 + banner; test report deleted.
- [ ] Confirm the Telegram message from the smoke test arrived.
- [ ] **Hazard:** `data/plan_state.json` and `data/current_session.json` are tracked although
  gitignored. A commit touching them overwrites the Pi's live copy on the next pull (happened once
  during this deploy). Untrack them with a careful Pi-side step.
- [ ] Optional: NOPASSWD sudoers line for `systemctl restart run-coach` so pushes deploy fully.
- Set `baseline_weight_lb` after the week ending Sat Oct 31.

## 3. To-dos for David (phone)

- [x] Telegram bot, secret, Pi config.
- [ ] Sunday Shortcut branch (`SHORTCUTS_GUIDE.md` Step 9b; one Find per metric, Group By Day,
  no `week_ending` needed). Check whether Sleep offers Group By Day. Dry run with only the branch.
- [ ] Check "Find Workouts" exists (else leave `lift_sessions_done` out).
- [ ] "Run Coach Tape" Shortcut + monthly Reminder.
- [ ] Change the Pi's `pi` password (`passwd`).

## 4. Open questions — decided 2026-10-16

- **S1 calendar:** generic `Jumps: skip this week.` on S1-week lift events, no reason. Done.
- **Saturday optional run:** low HRV **or** S1 week. Done (note reworded to "recovery is down").
- **`lift_sessions_done`:** stays optional.
- **`POST /bodycomp/measurements`:** kept.
- **W1 baseline:** set `baseline_weight_lb` on the Pi after the intro week (week ending Sat Oct 31).

## 5. Deferred minor issues — fixed 2026-10-16 (`tests/test_handoff_fixes.py`)

Training rework:
- ~~Non-Monday `cycle_start_date`~~ — `cycle.py` now counts from that date's own Monday.
- ~~`generate_session` / `_count_nights_below` call `date.today()`~~ — both (and `rule_engine`)
  take `today`; the server passes it.
- ~~No server test of the pre-start case~~ — added (Tue Oct 20 → DELOAD, 28 min).
- ~~Legacy `POST /run` never recomputes `current_week`~~ — it does now.

Body-comp:
- ~~`null` config / string threshold → plain 500~~ — `load_config` raises a clear ValueError
  naming the key (the routes return it as the error message).
- ~~S1 note says "~80% of sets" on DELOAD/SUPPRESS~~ — those days get the fixed
  `S1_NOTE_LOW_DAY` ("Sleep was short last week: skip jumps.").
- ~~Store writes not atomic~~ — temp file + `os.replace`.
- Still open (not code): the Shortcut's `EEEE == "Sunday"` check depends on the phone's language
  (noted in the guide), and `bc_phase_start_date` must be set at deploy (section 2) or W1 never
  stops after week 12.

## 6. Older backlog (from CLAUDE.md "Remaining tasks")

- Manual "rough week" override via the `/note` stub (e.g. `{"stress": "high"}` for 7 days).
- ~~CLAUDE.md `/calendar/push` and deploy-section tidy~~ — done 2026-10-16.
- `docs/superpowers/plans/2026-10-15-bodycomp-module.md` is partly superseded by spec 06 (noted at
  its top).

## References

- Specs: `health-bootcamp/03-run-coach-handoff.md`, `health-bootcamp/06-weekly-checkin-handoff.md`,
  protocol `health-bootcamp/01-protocol.md`
- Plans: `docs/superpowers/plans/2026-10-15-training-rework.md`,
  `docs/superpowers/plans/2026-10-15-bodycomp-module.md`
- Project docs: `CLAUDE.md` (6-week cycle, jump block, body-comp section with the S1 exception),
  `SHORTCUTS_GUIDE.md` (Step 9b Sunday branch, tape Shortcut)
