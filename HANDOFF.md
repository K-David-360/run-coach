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

## 2. Pi deploy (after everything else outstanding is done)

David is OK deploying before Mon Oct 19 (2026-10-16): with the cycle start set to 10-26, the rest
of this week reads as a deload too. The week of Oct 19 is the planned pre-block deload; block week 1
and BC-1 week 1 start Mon Oct 26.

Method: the Terminal SSH session described in `~/.claude/CLAUDE.md` (base64 transfer, check
`sha256sum`, keep a timestamped `.bak`). Direct `scp`/`ssh` from the Mac usually fails.

- [ ] **Copy files** to `~/run-coach/`: `cycle.py` (new), `server.py`, `rule_engine.py`,
  `plan_generator.py`, `calendar_generator.py`, `reset.py`, and `bodycomp/` (`__init__.py`,
  `config.py`, `store.py`, `checks.py`, `flags.py`, `telegram.py`, `review_packet.py`). The Pi's
  `~/run-coach` is its own git repo (`master`) with local edits; don't `git pull` into it.
- [ ] **Edit `data/plan_state.json` on the Pi:** set `"cycle_start_date": "2026-10-26"`, changing
  only that key. The leftover `kb_*` keys are ignored, so leave them alone.
- [ ] **Create `data/bodycomp/config.json` on the Pi** (gitignored; type the values on the Pi
  only): `bc_phase` `"BC-1"`, `bc_phase_start_date` `"2026-10-19"`, `protein_avg_min_g`,
  `protein_low_g`, `kcal_floor_bc1`, `kcal_floor_bc2` (targets from `health-bootcamp/01-protocol.md`),
  and optionally `baseline_weight_lb`. W1 reports "not configured" until the baseline is set.
  Optional `telegram_detail` (default `"trends"`).
- [ ] **Secrets on the Pi:** add `BODYCOMP_SECRET`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to
  `~/run-coach/.env`. `server.py` already calls `load_dotenv()` and `.env` is gitignored. Never put
  them in the repo or in chat. Without `BODYCOMP_SECRET`, every `/bodycomp/*` route returns 503.
- [ ] **Restart:** David runs `sudo systemctl restart run-coach`; never type the sudo password for
  him. Check with `systemctl show run-coach -p ActiveEnterTimestamp`.
- [ ] **Smoke tests on the Pi:**
  - `curl -s -X POST http://localhost:5001/calendar/push`, then check the public ICS:
    - Before Oct 26, this week's events start with `⛔️`.
    - Mon Oct 26 shows `🏋️ Push` with "weekly target 60".
    - There's no "KB" text anywhere.
  - Post one synthetic `/bodycomp/weekly` with the secret header to confirm a banner comes back
    and a Telegram message arrives. Then delete that test report from `data/bodycomp/weekly.json`
    and `data/bodycomp/reports/`, keeping a `.bak`.

## 3. To-dos for David (phone / accounts)

- [ ] **Telegram:** create a separate bot in @BotFather (not the job-search bot), run
  `/setjoingroups` → Disable, and get the chat ID. Put both on the Pi (section 2).
- [ ] **Choose the shared secret.** Put it in the Pi's `.env` and in the Shortcut header
  `X-Bodycomp-Secret`.
- [ ] **Build the Sunday branch** of the morning Shortcut, following `SHORTCUTS_GUIDE.md` Step 9b
  (7-day arrays, Group By Day, secret header, error notification).
- [ ] **Dry run on a weekday before Sun Oct 25:** temporarily switch the weekday condition, then
  restore it. Oct 25 covers the intro week; the first full week ends Sat Oct 31, so the first real
  check is **Sun Nov 1**.
- [ ] **Check on the device:** Group By Day doesn't double-count steps (iPhone + Watch), and the
  numbers arrive without units or separators (the server tolerates both, but confirm).
- [ ] **Check whether "Find Workouts" exists** in Shortcuts on this phone. If not, leave
  `lift_sessions_done` out and the server skips the session-count rule (L2).
- [ ] **Build the "Run Coach Tape" Shortcut** (`SHORTCUTS_GUIDE.md`) and add a monthly Reminder.
- [ ] **Change the Pi's `pi` password** (`passwd` on the Pi). The login banner says the default
  password is still set while SSH is enabled.

## 4. Open questions — decided 2026-10-16

- **S1 calendar:** generic `Jumps: skip this week.` on S1-week lift events, no reason. Done.
- **Saturday optional run:** low HRV **or** S1 week. Done (note reworded to "recovery is down").
- **`lift_sessions_done`:** stays optional.
- **`POST /bodycomp/measurements`:** kept.
- **W1 baseline:** set `baseline_weight_lb` on the Pi after the intro week (week ending Sat Oct 31).

## 5. Deferred minor issues (from the two final reviews)

Training rework:
- A `cycle_start_date` that isn't a Monday makes the calendar (evaluated at each week's Monday) and
  the server (actual day) disagree for part of the first week.
- `plan_generator.generate_session` and `rule_engine._count_nights_below` still call `date.today()`
  with no injectable `today`.
- No server-level test of the real pre-start case (e.g. Tue Oct 20 → DELOAD, 28 min).
- The legacy `POST /run` route never recomputes `current_week`.

Body-comp:
- A config of `null`, or a threshold given as a string, raises TypeError and returns a plain 500
  instead of a clear message.
- The S1 note says "~80% of sets" even on DELOAD/SUPPRESS days.
- Store JSON writes aren't atomic; a crash mid-write corrupts `weekly.json` (the daily path is
  unaffected).
- The Shortcut's `EEEE == "Sunday"` check depends on the phone's language (noted in the guide).
- An empty `bc_phase_start_date` means W1 never stops after week 12 and W3's early guard is
  skipped. Set it at deploy (section 2).

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
