# Run Coach — Handoff (2026-10-16, after deploy)

The training rework (6-week cycle, Push/Pull/Full, jumps) and the body-comp weekly check are
**deployed and live on the Pi**. 178 tests pass (`python3 -m pytest -q`). What's left is mostly
the Sunday Shortcut on the phone, plus a few small items.

> Repo is public. Keep personal numbers (weight, targets, lab values), secrets, tokens and chat
> IDs out of this file and every tracked file.

The previous handoff (open questions, §5 fixes, deploy steps) is in git history:
`git show 3e1998c:HANDOFF.md`.

---

## 1. Finish the Sunday Shortcut (main outstanding item)

Full instructions: **`SUNDAY_SHORTCUT_GUIDE.md`**. Where it stands:

- [x] Server route, secret header, Telegram (`@healthbootcamp_bot`): tested end to end.
- [x] Steps: Find + Group By Day works; the Shortcut sends the weekly **average**.
- [ ] **Date window:** use *Start Date is between `Week Start` and `Week End`* (last Sunday
  00:00 → Saturday 23:59). "In the last 7 days" includes today, which pulls the steps
  average down (today has only a few hours of steps).
- [ ] **Weight / protein / energy:** send as **lists** (Text fields), not averages. The server
  needs the day counts (4 weigh-ins, 5 food days) or it always reports "n/a". Not yet verified
  with real data; add dummy Health entries dated yesterday and dry-run.
- [ ] **Sleep: decide** (guide, "Sleep" section). The branch currently reuses last night's
  sleep, one value, so S1 (3+ short nights) can never fire. Recommended: server fills the week
  from `history.json` (5 of 7 nights, since rest days don't log), or a 7-day sleep loop.
- [ ] `Run Coach TEST` copy: delete its `/healthkit` post (each run added a history entry;
  cleaned up three times on 2026-10-16).
- [ ] Final: real Shortcut without `?dry_run=1`, `Sunday` restored. First real check
  **Sun Nov 1** (week ending Sat Oct 31).
- [ ] Check whether Find Workouts exists in Shortcuts; if not, leave `lift_sessions_done` out.

**Debugging:** `POST /bodycomp/weekly?dry_run=1` stores nothing, sends nothing, and replies
with per-metric `count` / `values` / `read_as`. The Pi keeps the last reply in
`~/run-coach/data/bodycomp/last_dry_run.json` (gitignored), so Claude can read it via the
Terminal SSH session.

## 2. Pi state

- `~/run-coach` is a checkout of `origin/main` (branch `master`). Cron runs `deploy.sh` every
  minute: `git pull` + `sudo systemctl restart run-coach`. **The restart needs a password**, so it
  only works within about 15 min of David running sudo himself. After a push, David runs
  `sudo systemctl restart run-coach` (check: `systemctl show run-coach -p MainPID -p ActiveEnterTimestamp`).
- [ ] Optional: a NOPASSWD sudoers line for `/bin/systemctl restart run-coach` (one exists for
  `canvas`), so pushes deploy with no manual step.
- `data/plan_state.json` and `data/current_session.json` are untracked now (4b2f827); a pull
  can no longer overwrite them.
- Plan state: **phase 2**, `cycle_start_date` 2026-10-26. This week and the week of Oct 19 read
  as deload (34-min runs, no jumps). Block week 1 starts Mon Oct 26.
- `.env` on the Pi: `GITHUB_TOKEN`, `BODYCOMP_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
  The Mac `.env` has the same except `BODYCOMP_SECRET`.
- `data/bodycomp/config.json` on the Pi: BC-1, start 2026-10-19, `telegram_detail` trends,
  David's targets. No weekly reports stored yet.
- Backups: `~/run-coach-backup-20261016005539` (pre-deploy code and data, `.env`, test-cleanup
  copies) and `~/run-coach-data-backup-20261016020329` (data before the untrack pull).

## 3. To-dos for David

- [ ] Set `baseline_weight_lb` in the Pi config after the week ending Sat Oct 31 (W1 reports
  "not configured" until then).
- [ ] Build the "Run Coach Tape" Shortcut and add a monthly Reminder (`SHORTCUTS_GUIDE.md`).
- [ ] Change the Pi's `pi` password (`passwd`).
- [ ] Confirm the phase: the Pi is on **phase 2** but `CLAUDE.md` says phase 1. Was the LTHR
  test done? Update `CLAUDE.md` "Current state" to match.

## 4. Smaller open items

- The Shortcut's `EEEE == "Sunday"` check depends on the phone's language.
- Manual "rough week" override via the `/note` stub (e.g. `{"stress": "high"}` for 7 days).
- `docs/superpowers/plans/2026-10-15-bodycomp-module.md` is partly superseded by spec 06.

## Decisions made 2026-10-16 (also in `CLAUDE.md`)

- S1 week: the calendar shows a generic `Jumps: skip this week.`, and Saturday's run becomes
  optional (low HRV **or** S1 week).
- `lift_sessions_done` optional; `/bodycomp/measurements` kept; W1 baseline set after the
  intro week.
- Old git history with near-real values accepted as public.
- `/bodycomp/weekly`: 0–7 values per metric (or Text, one per line), `week_ending` optional
  (last Saturday before today; any date snaps back), `?dry_run=1` for testing.

## References

- Specs: `health-bootcamp/03-run-coach-handoff.md`, `health-bootcamp/06-weekly-checkin-handoff.md`,
  protocol `health-bootcamp/01-protocol.md`
- Guides: `SUNDAY_SHORTCUT_GUIDE.md`, `SHORTCUTS_GUIDE.md`
- Deploy technique: `~/.claude/CLAUDE.md` (Terminal SSH session)
