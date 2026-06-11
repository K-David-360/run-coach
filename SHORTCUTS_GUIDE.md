# Run Coach — iOS Shortcut Guide

**One shortcut. Fully automatic. No manual input.**

Run it manually each morning, or set it to auto-trigger when a Running
workout ends. Either way it reads everything from HealthKit and POSTs to
the server.

**Rest day behavior:** If you already ran the shortcut today, the server
skips plan advancement but still re-runs the rule engine with fresh HRV,
sleep, and load data. You always get a current recommendation without the
plan counter moving.

**Terminology:** The Shortcut fires every morning regardless of whether a running workout happened. The server calls this a *daily execution*. "Run day" means Tuesday or Saturday (the calendar slots) — not a confirmed running workout. The server has no knowledge of whether you actually ran.

---

## Before you start — find your Mac's local IP

The server is running on your Mac for now. Run this in Terminal:

```bash
ipconfig getifaddr en0
```

You'll get something like `192.168.1.42` — that's your server address for
testing. You'll swap it for the Pi's Tailscale IP later.

---

## Step 0 — Server URL variable

First action in the shortcut. Makes it easy to update the address later.

- Action: **Text**
- Value: `http://192.168.1.42:5001` *(use your actual IP from above)*
- Tap the result → **Add to Variable** → `Server URL`

---

## Step 1 — HRV last night

Apple Watch measures HRV throughout sleep. Get the most recent reading.

- Action: **Find Health Samples**
  - Type: **Heart Rate Variability (SDNN)**
  - Sort: **Start Date, Newest First**
  - Limit: **1**
- Action: **Get Details of Health Sample** → **Value**
- → **Add to Variable**: `HRV Last Night`

---

## Step 2 — HRV 7-day samples *(optional after first week)*

The server computes the 7-day HRV baseline from execution history automatically after 7 executions. This step seeds the baseline during the first week only.

- Action: **Find Health Samples**
  - Type: **Heart Rate Variability (SDNN)**
  - Filter: **Date is in the last 7 Days**
  - Sort: **Start Date, Newest First**
- Action: **Repeat with Each**
  - Inside loop: **Get Details of Health Sample** → **Value**
  - Inside loop: **Add to Variable** → `HRV 7D Samples`
- *(End Repeat)*

> After 7 executions the server ignores this field and uses history instead. Safe to keep in the Shortcut permanently — the server handles it gracefully either way.

---

## Step 3 — Deep sleep last night

18-hour window catches last night without pulling in yesterday morning.

- Action: **Find Health Samples**
  - Type: **Sleep**
  - Filter: **Category = Deep**
  - Filter: **Date is in the last 18 Hours**
- Action: **Repeat with Each**
  - **Get Details of Health Sample** → **Duration**
    > If "Duration" isn't available: **Calculate** End Date minus Start Date (seconds)
  - **Calculate**: `Repeat Result ÷ 3600`
  - **Add to Variable**: `Deep Sleep Chunks`
- Action: **Calculate Statistics** on `Deep Sleep Chunks` → **Sum**
- → **Add to Variable**: `Sleep Deep Hrs`

---

## Step 4 — Total sleep last night

Run **three separate** Find Health Samples queries and funnel all chunks into
the same variable before summing. Excludes "Awake" intentionally.

Repeat the duration loop from Step 3 for each category, all adding to
`Total Sleep Chunks`:

- **Find Health Samples** → Sleep → Category = **Core** → last 18 Hours → loop → **Add to Variable**: `Total Sleep Chunks`
- **Find Health Samples** → Sleep → Category = **Deep** → last 18 Hours → loop → **Add to Variable**: `Total Sleep Chunks`
- **Find Health Samples** → Sleep → Category = **REM** → last 18 Hours → loop → **Add to Variable**: `Total Sleep Chunks`

Then:
- Action: **Calculate Statistics** on `Total Sleep Chunks` → **Sum**
- → **Add to Variable**: `Sleep Total Hrs`

---

## Step 5 — Training load (manual percentage)

Glance at the Fitness app → Activity → Training Load and note the percentage
Apple shows (e.g. +46%, -18%). Type it in here — the server maps it to the
right category automatically.

- Action: **Ask for Input**
  - Input Type: **Number**
  - Prompt: `Training load % (e.g. -18 or 46)`
- → **Add to Variable**: `Load Pct`

> **Mapping (for reference):** > +50% = well above, +20–50% = above,
> -20 to +20% = steady, -50 to -20% = below, < -50% = well below.

---

## Step 6 — Resting heart rate

Apple Watch computes a daily resting HR figure. Get the most recent value.

- Action: **Find Health Samples**
  - Type: **Resting Heart Rate**
  - Sort: **Start Date, Newest First**
  - Limit: **1**
- Action: **Get Details of Health Sample** → **Value**
- → **Add to Variable**: `Resting HR`

> If the watch hasn't computed today's resting HR yet (common early in the
> morning), this will return yesterday's value — that's fine. The server
> handles a missing or zero value safely.

---

## Step 7 — Today's date (deduplication key)

The server uses today's date to detect rest days. If you've already posted
today, it won't advance the plan counter — it just re-runs the rule engine
with fresh recovery data.

- Action: **Date**
  *(this gives you the current date and time)*
- Action: **Format Date**
  - Date: result from above
  - Format: **Custom**
  - Custom format: `yyyy-MM-dd`
- → **Add to Variable**: `Last Workout Date`

> If you don't see "Format Date", search for it in the action list. It's
> under the Scripting or Date section. The custom format `yyyy-MM-dd`
> produces strings like `2026-05-09`.

---

## Step 8 — POST to server

- Action: **Get Contents of URL**
  - URL: tap the field → insert variable `Server URL` → then type `/healthkit`
    directly after it (no space)
  - Method: **POST**
  - Request Body: **JSON**
  - Add each row below as a key-value pair:

| Key | Variable |
|---|---|
| `last_workout_date` | `Last Workout Date` |
| `hrv_last_night` | `HRV Last Night` |
| `hrv_7d_samples` | `HRV 7D Samples` |
| `sleep_deep_hrs` | `Sleep Deep Hrs` |
| `sleep_total_hrs` | `Sleep Total Hrs` |
| `resting_hr` | `Resting HR` |
| `load_pct` | `Load Pct` |

- → **Add to Variable**: `Server Response`

---

## Step 9 — Notification

- Action: **Get Dictionary from Input**
  - Input: `Server Response`
  - → **Add to Variable**: `Server Response Dict`
- Action: **Get value for Key in Dictionary**
  - Key: `notification`
  - Dictionary: `Server Response Dict`
- Action: **Show Notification**
  - Title: `Run Coach`
  - Body: result above

The `notification` field is the concise banner text — e.g.
"✅ On track — follow today's plan as scheduled." or
"⛔️ Deload week — reduced load across all sessions."

It's the same message regardless of session type (run, strength, rest),
which is why it's used for the banner rather than `summary`.

> **Note:** If your Shortcut currently reads the `summary` key here,
> switch it to `notification`. The `summary` field contains the full
> session detail (e.g. block durations) which is too long for a banner.

---

## Optional: auto-trigger after a run

Shortcuts → **Automation** → **+** → **Workout** → **Ends** → **Running**
→ select this shortcut → disable "Ask Before Running"

---

## When you move to the Pi

1. Update the `Server URL` variable to `http://100.x.x.x:5001`
   (your Pi's Tailscale IP — run `sudo tailscale ip` on the Pi to find it)
2. Everything else stays the same

**Tailscale setup on the Pi:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up        # follow the auth link it prints
sudo tailscale ip        # copy this address into the shortcut
```

**On iPhone:** Install Tailscale → App Store, sign in with same account,
toggle on. Your phone can now reach the Pi from anywhere.

---

## Verifying what the server received (debug)

Every non-rest-day response includes a `debug` field with the exact values the server processed. Use it to confirm the Shortcut is sending correct data.

**To read the debug output in your Shortcut**, add these steps after Step 9:

- Action: **Get value for Key in Dictionary**
  - Key: `debug`
  - Dictionary: `Server Response Dict`
- Action: **Show Alert** (or **Quick Look**)
  - Message: result above

**Key debug fields to check:**

| Field | What it confirms |
|-------|-----------------|
| `sleep_total_hrs` | Exactly what total sleep value the server received |
| `sleep_deep_hrs` | Exactly what deep sleep value the server received |
| `hrv_ratio` | `hrv_last_night ÷ hrv_7d_avg` — should be near 1.0 on a normal day |
| `hrv_7d_avg` | The 7-day HRV baseline the server computed |
| `load_classification` | How the server mapped your `load_pct` input |
| `decision` | The final rule engine output |

**If `sleep_total_hrs` looks wrong:**
Check Step 4 in the Shortcut:
1. Are all three categories (Core, Deep, REM) being summed? Each needs its own Find Health Samples query.
2. Is the time window set to **18 hours** on each query? A shorter window (e.g. 8 hrs) can miss sleep that started before midnight.
3. Is the duration being divided by **3600** (seconds → hours)? HealthKit returns duration in seconds in some configurations.

**If `sleep_deep_hrs` looks wrong:**
Check Step 3: only the **Deep** category should be queried, and duration divided by 3600.

> The debug field is absent on rest days (Thu/Sun) — the server short-circuits before health data processing on those days.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "couldn't convert from Rich Text to Dictionary" | Missing "Get Dictionary from Input" step — add it before "Get value for Key" in Step 9 |
| `{"error": "Invalid or missing JSON body."}` | Key name typo in Step 8 — check every key exactly matches the table |
| Notification is blank or shows raw JSON | Reading wrong key in Step 9 — must be `notification`, not `summary` |
| Notification says `rest_day: true` in debug | Working as intended — already ran shortcut today, plan counter won't advance again |
| `Sleep Deep Hrs` is 0 | Watch didn't detect deep sleep; rule engine handles 0 safely |
| `Format Date` produces wrong format | Make sure custom format is exactly `yyyy-MM-dd` (lowercase y and d) |
| Rule engine ignoring load | `load_classification` value doesn't match expected strings — must be exactly one of: `well_below`, `below`, `steady`, `above`, `well_above` |
| Shortcut times out | Server not running, or IP/port wrong |
| Works on Wi-Fi, fails on cellular | Open Tailscale app on phone, make sure it's connected |
| Plan counter advanced twice in one day | `Last Workout Date` date format changed mid-day — should be consistent |
