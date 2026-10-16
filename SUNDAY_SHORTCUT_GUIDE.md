# Sunday Weekly Check — Shortcut Guide

How to finish the Sunday branch of the morning Shortcut, which posts last week's body-comp
data to `POST /bodycomp/weekly`. It replaces Step 9b of `SHORTCUTS_GUIDE.md`.

> Repo is public. No personal numbers, secrets or chat IDs in this file.

---

## Status (2026-10-16)

| Piece | State |
|---|---|
| Server, secret, Telegram | Done and tested. The Pi returns a banner and sends a Telegram message from `@healthbootcamp_bot`. |
| Lists | Verified: a list in a Text field arrives as one value per line. |
| Steps / weight / protein / energy | Built as filtered loops (below). Steps was adding the whole list each pass; fixed by reading the **Repeat Item**. Re-check with a dry run. |
| Sleep | **Decided: the Shortcut sends none.** The server fills it from the daily `/healthkit` history; rest days now log too, so all 7 nights are there. |
| Testing | Done in the real Shortcut with `?dry_run=1` (no separate TEST copy). |

---

## What the server accepts

`POST [Server URL]/bodycomp/weekly`, header `X-Bodycomp-Secret: <secret>`, JSON body:

| Key | Value |
|---|---|
| `weights_lb` | daily weights, lb |
| `protein_g_daily` | daily protein, g |
| `energy_kcal_daily` | daily calories, kcal |
| `steps_daily` | daily steps, or one weekly average |
| `sleep_hrs_daily` | optional; leave out and the server uses the daily posts' sleep |
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

### 1. Today as text

**Format Date** → Current Date, Custom `yyyy-MM-dd` → **Set Variable** `Today Text`.

Find Health Samples won't take a date variable in "is between", and If won't take one in
"is before", so the window is "in the last 7 days" with today dropped by a text compare.

### 2. One filtered loop per metric

1. **Find Health Samples** → Type, **in the last 7 days**, Group By **Day**, Fill Missing
   **off**, **no Limit**, Unit.
2. **Repeat with Each** (Health Samples)
   - **Get Details of Health Sample** → **Start Date** of **Repeat Item**
   - **Format Date** → that Start Date, Custom `yyyy-MM-dd`
   - **If** Formatted Date **is not** `Today Text`
     - **Get Details of Health Sample** → **Value** of **Repeat Item** (not Health
       Samples, or every pass adds the whole list)
     - **Add to Variable** → the variable below
   - **End If**
3. **End Repeat**

| Type | Unit | Variable |
|---|---|---|
| Body Mass | lb | `Weights` |
| Dietary Protein | g | `Protein` |
| Dietary Energy | kcal | `Energy` |
| Steps | count | `Steps` |

The window starts at the time of day the Shortcut runs, so last Sunday is partial. Fine
for weight (morning weigh-in); food and steps for that day may be undercounted.

### 3. Post

**Get Contents of URL** → `[Server URL]/bodycomp/weekly`, Method **POST**, Header
`X-Bodycomp-Secret` = the secret, Request Body **JSON**, each field type **Text**:
`weights_lb` = `Weights`, `protein_g_daily` = `Protein`, `energy_kcal_daily` = `Energy`,
`steps_daily` = `Steps`. No sleep key.

### 4. Banner

- **Get Dictionary Value** `notification` from Contents of URL.
- **If** it *does not have any value* → **Get Dictionary Value** `error` → **Show
  Notification** "Weekly check failed: [error]".
- **Otherwise** → **Show Notification** (title "Weekly check") with `notification`.
- **End If**.

---

## Testing

1. Add `?dry_run=1` to the URL. Dry runs store nothing and send no Telegram. The reply
   lists, per metric, `count`, raw `values` and `read_as`, plus `sleep_source`.
2. The Pi keeps the last dry-run reply, **including rejected ones**, in
   `data/bodycomp/last_dry_run.json`, so Claude can read it with no copy-paste.
3. Running the whole morning Shortcut also posts `/healthkit`, which adds a history entry.
   Tell Claude after testing so the extra entries can be removed.
4. For data: add dummy entries in the **Health app** (Browse → Weight / Protein / Dietary
   Energy → Add Data) dated **yesterday**, then delete them afterwards. Change `Sunday` in
   the If to today's weekday while testing.

**Expected:** each `count` ≤ 7 and equal to the days with data, no today value, nothing in
`read_as` is `null`, `sleep_source` = `history`.

When it's right: remove `?dry_run=1`, restore `Sunday`, and wait for **Sun Nov 1** (first
full week, ending Sat Oct 31).
