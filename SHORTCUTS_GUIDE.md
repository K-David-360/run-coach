# Run Coach — iOS Shortcut Guide

This documents the **working shortcut** (exported as `Run Coach.json`). The steps
below match the implementation exactly.

**What it does:** Connects Tailscale, collects HealthKit data, POSTs to the Pi,
shows a notification banner, then disconnects Tailscale. One tap each morning.

**Rest day behavior:** If you already ran the shortcut today, the server skips
plan advancement but still re-runs the rule engine with fresh recovery data.

**Terminology:** The Shortcut fires every morning regardless of whether a running
workout happened. The server calls this a *daily execution*. "Run day" means
Tuesday or Saturday (the calendar slots) — not a confirmed running workout.

---

## Step 0 — Connect Tailscale

- Action: **Tailscale → Connect**
  - Show When Run: off

This lets the shortcut reach the Pi from anywhere (Wi-Fi or cellular).

---

## Step 1 — Server URL variable

- Action: **Text**
  - Value: `http://100.109.212.86:5001`
- → **Add to Variable**: `Server URL`

Update this value if the Pi's Tailscale IP changes (`sudo tailscale ip` on the Pi).

---

## Step 2 — Current date (deduplication key)

The server uses today's date to detect duplicate runs. If you've already posted
today, it won't advance the plan counter — it just re-runs the rule engine with
fresh recovery data.

- Action: **Date** *(gives current date + time)*
- Action: **Format Date**
  - Format: *(default — used internally for the 18-hour sleep check below)*

Keep a reference to this formatted date — it's used in the sleep steps.

Also format for the POST payload:

- Action: **Format Date**
  - Date: result from **Date** above
  - Format: **Custom** → `yyyy-MM-dd`
- → **Add to Variable**: `Last Workout Date`

---

## Step 3 — Training load (manual percentage)

The Shortcut opens the Fitness Training Load card automatically so you can read
the current %, then prompts you to type it in.

- Action: **Fitness → Open Training Load** *(opens the Training Load summary card)*
- Action: **Ask for Input**
  - Input Type: **Number** (whole numbers only, no decimals)
  - Prompt: `Training Load %`
- → **Add to Variable**: `Load Pct`

> **Mapping (for reference):** > +50% = well above, +20–50% = above,
> -20 to +20% = steady, -50 to -20% = below, < -50% = well below.

---

## Step 4 — Resting heart rate

- Action: **Find Health Samples**
  - Type: **Resting Heart Rate**
  - Sort: **End Date, Newest First**
  - Limit: **1**
- Action: **Get Details of Health Sample** → **Value**
- → **Add to Variable**: `Resting HR`

> If the watch hasn't computed today's resting HR yet (common early morning),
> this returns yesterday's value — fine. The server handles a missing or zero value safely.

---

## Step 5 — HRV last night

- Action: **Find Health Samples**
  - Type: **Heart Rate Variability (SDNN)**
  - Sort: **Start Date, Newest First**
  - Limit: **1**
  - Filter: **Start Date is in the last 1 Days**
- Action: **Get Details of Health Sample** → **Value**
- → **Add to Variable**: `HRV Last Night`

> The server computes the 7-day HRV baseline from stored history — the shortcut
> only sends last night's single value.

---

## Step 6 — Deep sleep (18-hour window)

HealthKit's "last N days" filter is calendar-date-based. Using 1 day gives all
samples from the current and previous calendar dates — potentially too far back.
The shortcut applies a secondary 18-hour check per sample to isolate last night.

**How the 18-hour check works:** `Get Time Between Dates` computes
`now − sample_start` in hours (positive = past). If the result is < 18, the
sample started within the last 18 hours and belongs to last night.

- Action: **Find Health Samples**
  - Type: **Sleep**
  - Filter: **Category = Deep**
  - Filter: **Start Date is in the last 1 Days**
  - Limit: disabled
- Action: **Repeat with Each** (over the health samples)
  - **Get Details of Health Sample** → **Start Date** (of Repeat Item)
  - **Get Time Between Dates**
    - From: today's formatted date (from Step 2)
    - To: sample's Start Date
    - In: **Hours**
  - **If** Time Between Dates **< 18**:
    - **Get Details of Health Sample** → **Duration** (of Repeat Item)
    - **Calculate**: `Duration ÷ 3600`
    - **Add to Variable**: `Deep Sleep Chunks`
  - *(End If)*
- *(End Repeat)*
- Action: **Calculate Statistics** on `Deep Sleep Chunks` → **Sum**
- → **Add to Variable**: `Sleep Deep Hrs`

---

## Step 7 — Total sleep (18-hour window)

Same 18-hour approach, looping over three categories. "Asleep" catches
uncategorized sleep (e.g. naps) that HealthKit doesn't assign to REM/Core/Deep —
these categories don't overlap, so no double-counting.

- Action: **List** → items: `Asleep`, `REM`, `Core`
- Action: **Repeat with Each** (over the list)
  - **Find Health Samples**
    - Type: **Sleep**
    - Filter: **Category = [Repeat Item]**
    - Filter: **Start Date is in the last 1 Days**
    - Limit: disabled
  - **Repeat with Each** (over the health samples)
    - **Get Details of Health Sample** → **Start Date** (of Repeat Item 2)
    - **Get Time Between Dates** (same as Step 6 — `now − start`)
    - **If** result **< 18**:
      - **Get Details of Health Sample** → **Duration** (of Repeat Item 2)
      - **Calculate**: `Duration ÷ 3600`
      - **Add to Variable**: `Non Deep Sleep Chunks`
    - *(End If)*
  - *(End inner Repeat)*
- *(End outer Repeat)*
- Action: **Calculate Statistics** on `Non Deep Sleep Chunks` → **Sum**
- → **Add to Variable**: `Non Deep Sleep Hrs`
- Action: **Calculate**: `Non Deep Sleep Hrs + Sleep Deep Hrs`
- → **Add to Variable**: `Total Sleep Hrs`

---

## Step 8 — POST to server

- Action: **Get Contents of URL**
  - URL: `[Server URL]/healthkit`
  - Method: **POST**
  - Request Body: **JSON**

| Key | Variable |
|-----|----------|
| `last_workout_date` | `Last Workout Date` |
| `hrv_last_night` | `HRV Last Night` |
| `sleep_deep_hrs` | `Sleep Deep Hrs` |
| `sleep_total_hrs` | `Total Sleep Hrs` |
| `load_pct` | `Load Pct` |
| `resting_hr` | `Resting HR` |

- → **Add to Variable**: `Server Response`

---

## Step 9 — Parse and show notification

- Action: **Get Dictionary from Input**
  - Input: `Server Response`
  - → **Add to Variable**: `Server Response Dict`
- Action: **Get Value for Key** → Key: `decision_reason`
- Action: **Get Value for Key** → Key: `notification`
- Action: **Show Notification**
  - Title: *(empty)*
  - Body: `[decision_reason] [notification]`

The banner shows the rule engine decision label followed by the notification text,
e.g. `HOLD ✅ On track — follow today's plan as scheduled.`

---

## Step 9b — Sunday weekly check (body composition)

Runs only on Sundays, after Step 9 and before Tailscale disconnects. It sends the
previous Sunday–Saturday as 7 daily values per metric to `/bodycomp/weekly`.
MyFitnessPal writes protein and dietary energy into Health, so there is no manual entry.
Action names vary by iOS version; verify on the phone.

1. **Format Date** → Current Date, custom format `EEEE` → **If** result **is** `Sunday`
   (the weekday name follows the phone's language).
2. **Dates:**
   - No `week_ending` needed: the server uses the last Saturday before today (yesterday,
     on a Sunday). Send `week_ending` (`yyyy-MM-dd`) only to re-post an older week; any date
     snaps back to the Saturday on or before it.
   - **Format Date** → Current Date, custom `yyyy-MM-dd` → **Get Dates from Input** →
     `Today Start` (today 00:00).
   - **Adjust Date** → `Today Start`, subtract 7 days → `Week Start` (last Sunday 00:00).
   - **Adjust Date** → `Today Start`, subtract 1 minute → `Week End` (Saturday 23:59).
3. **One Find per metric, each into its own variable.** Filter **Start Date is between
   `Week Start` and `Week End`**, not "in the last 7 days": on a Sunday morning that also
   catches today and can return 8 days, which the server rejects. Then **Get Details of
   Health Sample** → *Value* to get the list of numbers.

   | Health type | Find options | Variable | JSON key |
   |-------------|--------------|----------|----------|
   | Body Mass | Group By Day (lb in Health) | `Weights` | `weights_lb` |
   | Dietary Protein | Group By Day | `Protein` | `protein_g_daily` |
   | Dietary Energy | Group By Day | `Energy` | `energy_kcal_daily` |
   | Steps | Group By Day (merges iPhone + Watch) | `Steps` | `steps_daily` |
   | Sleep | see below | `Sleep` | `sleep_hrs_daily` |

   **No padding needed.** Group By Day skips days with no data; the server accepts 0–7
   values per list (day order is never used), treats the missing days as missing, and
   rejects more than 7. A list with one value or none is fine too.

   **Sleep** must be hours per night. If Find Health Samples offers Group By Day for Sleep
   (Value is not *Awake*, not *In Bed*), use it and divide each value by 3600 if it comes in
   seconds. If it does not, raw sleep samples are per sleep stage, not per night, so they
   cannot be sent as-is; use a small **Repeat 7 times** loop for sleep only (Find Sleep
   samples whose End Date falls on that day → Get Details *Duration* → Calculate Statistics
   *Sum* → ÷ 3600 → Add to `Sleep`).

4. Optional: **Find Workouts** (Strength Training) in the window → **Count** →
   `lift_sessions_done`. Find Workouts is not available in Shortcuts on every device;
   if it is missing, leave the key out and the server skips the session-count check.
5. **Get Contents of URL** → `{Server URL}/bodycomp/weekly`, Method POST, Request Body JSON
   with the five lists, **each field of type Text** (a Number field keeps only the first
   item; Text joins the list one value per line, which the server splits) (and `lift_sessions_done` if available). Header
   `X-Bodycomp-Secret` = the shared secret (stored only in the Shortcut; never export or
   share the Shortcut with it inside).
6. **Get Dictionary Value** `notification` from the response. **If** it *does not have any
   value* → **Get Dictionary Value** `error` → **Show Notification** "Weekly check failed:
   [error]" (a rejected post, e.g. more than 7 values or a wrong secret, is then visible).
   **Otherwise** → **Show Notification** with the `notification` value (title "Weekly check").
7. **End If**

The Pi also sends a Telegram message (trends tier: weight change, average protein,
steps and sleep, plus flags; never absolute weight or calories). Re-running on the same
Sunday replaces that week's report.

**Debugging:** add `?dry_run=1` to the URL and a **Quick Look** right after Get Contents of
URL. The reply lists, per metric, the `count`, the raw `values` and how the server `read_as`
them; nothing is stored and no Telegram message is sent.

**Dry run:** run only this branch (a copy of the Shortcut with everything before Step 9b
deleted, so no extra `/healthkit` entries), with the weekday condition changed to today.
Confirm the banner and the Telegram message, then restore `Sunday`. The dry run's report
is filed under last Saturday's week; ask for it to be deleted afterwards.

**Server environment (names only; values live on the Pi, never in the repo):**
`BODYCOMP_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

---

## Step 10 — Disconnect Tailscale

- Action: **Tailscale → Disconnect**
  - Show When Run: off

---

## Monthly tape measurements (separate "Run Coach Tape" Shortcut)

Measure in the morning, relaxed. One small Shortcut, run once a month:

1. **Tailscale → Connect**
2. **Format Date** → Current Date, `yyyy-MM-dd` → `Tape Date`
3. One **Ask for Input** (Number, inches) per site, each into its own variable:
   neck, shoulders (widest), chest, waist (at navel), arm (flexed), thigh, calf
4. **Get Contents of URL** → `{Server URL}/bodycomp/measurements`, POST JSON with keys
   `date`, `neck_in`, `shoulders_in`, `chest_in`, `waist_in`, `arm_in`, `thigh_in`, `calf_in`
   with header `X-Bodycomp-Secret`. Blank sites are skipped.
5. **Tailscale → Disconnect**

Add a monthly iPhone Reminder that opens this Shortcut. For a Claude review, fetch
`{Server URL}/bodycomp/review-packet` with the `X-Bodycomp-Secret` header (a tiny Shortcut:
Get Contents of URL → Copy to Clipboard) and paste it into a chat.

---

## Verifying what the server received (debug)

Every non-rest-day response includes a `debug` field. Add these steps after Step 9
to inspect it:

- Action: **Get Value for Key** → Key: `debug` → Dictionary: `Server Response Dict`
- Action: **Show Alert** (or **Quick Look**) → result above

**Key debug fields:**

| Field | What it confirms |
|-------|-----------------|
| `sleep_total_hrs` | Exact total sleep value the server received |
| `sleep_deep_hrs` | Exact deep sleep value the server received |
| `hrv_ratio` | `hrv_last_night ÷ hrv_7d_avg` — near 1.0 on a normal day |
| `hrv_7d_avg` | 7-day HRV baseline computed from stored history |
| `load_classification` | How the server mapped your `load_pct` input |
| `decision` | Final rule engine output |

> The `debug` field is absent on rest days (Thu/Sun) — server short-circuits before
> health data processing on those days.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Shortcut fails immediately | Tailscale not installed or not signed in — install from App Store |
| "couldn't convert from Rich Text to Dictionary" | Missing "Get Dictionary from Input" before "Get Value for Key" in Step 9 |
| `{"error": "Invalid or missing JSON body."}` | Key name typo in Step 8 — check every key matches the table exactly |
| Notification body is blank | `decision_reason` or `notification` key missing — confirm server is up to date |
| `Sleep Deep Hrs` is 0 | Watch didn't detect deep sleep; rule engine handles 0 safely |
| `Format Date` wrong format | Custom format must be exactly `yyyy-MM-dd` (lowercase y and d) |
| Works on Wi-Fi, fails on cellular | Open Tailscale app on phone and make sure it's connected before running |
| Plan counter advanced twice in one day | `Last Workout Date` format changed — must be consistent `yyyy-MM-dd` |
| Server not reachable | Check Pi is on and `systemctl status run-coach` shows active |
