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

See **`SUNDAY_SHORTCUT_GUIDE.md`**: build steps, what the server accepts, testing with
`?dry_run=1`, and the open sleep decision.

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
