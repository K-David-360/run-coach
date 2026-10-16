# Sunday Weekly Check — Shortcut Guide

How to finish the Sunday branch of the morning Shortcut, which posts last week's body-comp
data to `POST /bodycomp/weekly`. It replaces Step 9b of `SHORTCUTS_GUIDE.md`.

> Repo is public. No personal numbers, secrets or chat IDs in this file.

---

## Status (2026-10-16)

| Piece | State |
|---|---|
| Server, secret, Telegram | Done and tested. The Pi returns a banner and sends a Telegram message from `@healthbootcamp_bot`. |
| Steps | Works. Find returns daily totals; the Shortcut sends their **average** (one number). The window still includes today, so the average is too low. **Fix the window (step 2).** |
| Weight / protein / energy | Not yet verified with real data: Health had nothing in the window. Send them as **lists**, not averages (see "Why lists"). |
| Sleep | **Open decision.** The branch reuses the daily Shortcut's sleep variable, which is one night only. See "Sleep". |
| Dry-run test copy | `Run Coach TEST` exists. It still posts to `/healthkit` on every run; delete that action. |

---

## What the server accepts

`POST [Server URL]/bodycomp/weekly`, header `X-Bodycomp-Secret: <secret>`, JSON body:

| Key | Value |
|---|---|
| `weights_lb` | daily weights, lb |
| `protein_g_daily` | daily protein, g |
| `energy_kcal_daily` | daily calories, kcal |
| `steps_daily` | daily steps, or one weekly average |
| `sleep_hrs_daily` | hours per night |
| `lift_sessions_done` | optional; leave out if Find Workouts is missing |

- Each value can be a list of **0–7** numbers, a single number, or **Text** with one number
  per line (that is what a Shortcuts Text field holding a list sends). More than 7 is
  rejected with a message about the date filter.
- Units and thousands separators are tolerated (`"11,576"`, `"180.4 lb"`). `0` or empty is
  treated as missing, except steps, where `0` is a real 0.
- `week_ending` is optional. The server uses the last Saturday before today.
- Day order doesn't matter.

### Why lists for weight, protein and energy

The server only reports an average when there are enough days: at least **4 weigh-ins** and
**5 food-logged days**. An average computed in the Shortcut arrives as one value, which the
server counts as **one day**, so weight and protein would always read "n/a". Steps has no
day minimum, so its average is fine.

---

## Build steps

All inside `If [Format Date (EEEE)] is Sunday`, after the daily Step 9, before
Tailscale Disconnect.

### 1. Date variables (window = last Sunday 00:00 → Saturday 23:59)

1. **Format Date** → Current Date, Custom `yyyy-MM-dd`.
2. **Get Dates from Input** (Formatted Date) → **Set Variable** `Today Start`.
3. **Adjust Date** → `Today Start`, subtract **7 days** → **Set Variable** `Week Start`.
4. **Adjust Date** → `Today Start`, subtract **1 minute** → **Set Variable** `Week End`.

### 2. One Find per metric

For each metric: **Find Health Samples** with
- **Start Date is between `Week Start` and `Week End`**. Not "in the last 7 days": that
  includes today and returns 8 day-groups.
- **Group By: Day**, Fill Missing **off**, **no Limit**.

Then **Get Details of Health Sample → Value** into its own variable.

| Type | Unit | Then | Variable |
|---|---|---|---|
| Body Mass | lb | (list as-is) | `Weights` |
| Dietary Protein | g | (list as-is) | `Protein` |
| Dietary Energy | kcal | (list as-is) | `Energy` |
| Steps | count | **Calculate Statistics → Average** | `Steps` |
| Sleep | — | see "Sleep" | `Sleep` |

### 3. Post

**Get Contents of URL** → `[Server URL]/bodycomp/weekly`, Method **POST**, Header
`X-Bodycomp-Secret` = the secret, Request Body **JSON** with the five keys above, **each
field type Text**.

### 4. Banner

- **Get Dictionary Value** `notification` from Contents of URL.
- **If** it *does not have any value* → **Get Dictionary Value** `error` → **Show
  Notification** "Weekly check failed: [error]".
- **Otherwise** → **Show Notification** (title "Weekly check") with `notification`.
- **End If**.

---

## Sleep (decision needed)

The weekly rule S1 flags 3+ nights under 6.5 h, so it needs **one value per night**. The
daily Shortcut's sleep variable is last night only, so S1 can never trigger with it. Options:

1. **Server fills it from history (recommended).** The daily `/healthkit` post already logs
   `sleep_total_hrs` each morning. The server could use those for the week when the Shortcut
   sends one value or none. Catch: rest days (Thu, Sun) return before logging, so that's 5
   nights of 7, unless rest days start logging sleep too. Needs a server change.
2. **Small sleep loop in the Shortcut.** Repeat 7 times: Find Sleep samples whose End Date
   falls on that day, Value is not Awake / In Bed → Details Duration → Sum → ÷ 3600 → add to
   `Sleep`.
3. **Check Group By Day for Sleep** on the phone. If Find Health Samples offers it for
   Sleep, use it like the others (convert seconds to hours if needed).

---

## Testing

Use the copy `Run Coach TEST`:

1. Delete its **Get Contents of URL … /healthkit** action and the daily banner after it.
   Every run of the full morning Shortcut adds a `/healthkit` history entry, which skews the
   HRV baseline and short-sleep counts (cleaned up three times on 2026-10-16).
2. Change `Sunday` in the If to today's weekday.
3. URL: `[Server URL]/bodycomp/weekly?dry_run=1`. Dry runs store nothing and send no
   Telegram. The reply lists, per metric, `count`, raw `values` and `read_as`.
4. Optional: **Quick Look** right after Get Contents of URL to see the reply on the phone.
   The Pi also keeps the last reply in `data/bodycomp/last_dry_run.json`, so Claude can read
   it with no copy-paste.
5. For data: add dummy entries in the **Health app** (Browse → Weight / Protein / Dietary
   Energy → Add Data) dated **yesterday**, then delete them afterwards.

**Expected:** `steps_daily` one value close to the true 7-day average (no today), weight /
protein / energy `count` = number of days with data, nothing in `read_as` is `null`.

When it's right: remove `?dry_run=1` in the real morning Shortcut's branch, restore
`Sunday`, and wait for **Sun Nov 1** (first full week, ending Sat Oct 31).
