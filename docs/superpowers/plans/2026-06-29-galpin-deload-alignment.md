# Galpin Deload Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task.

**Goal:** Align the week 4 deload behaviour with the Galpin/Huberman protocol — runs stay Zone 2 at ~70% duration; strength deload messaging changes from "light load" to "same weight, half the sets."
**Architecture:** Two targeted edits to `plan_generator.py` plus a `CLAUDE.md` doc update. No schema changes, no new files beyond the reference doc already created.
**Tech Stack:** Python 3, Flask (no new dependencies)

Reference: `docs/deload_protocol.md`

---

## File map

| File | Change |
|------|--------|
| `plan_generator.py` | (1) DELOAD run branch: Zone 2 at 70% duration instead of Zone 1 fixed 10 min. (2) Strength DELOAD phrase/notes: "same weight, half the sets." (3) Remove now-dead `_deload_blocks()` function. |
| `CLAUDE.md` | Update the strength intensity class table and run deload description to match the new protocol. |

---

## Task 1: Fix the DELOAD run branch

**Files:**
- Modify: `plan_generator.py` — `generate_session()`, DELOAD branch (~line 294)
- Test: `tests/test_plan_generator.py` (create if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_plan_generator.py
import pytest
from unittest.mock import patch
from plan_generator import generate_session

MOCK_STATE_WEEK3 = {
    "current_week": 3,
    "run_in_week": 0,
    "phase": 1,
    "kb_weeks_elapsed": 0,
    "kb_peak_rung": 10,
}

@patch("plan_generator._load_json", return_value=MOCK_STATE_WEEK3)
def test_deload_run_is_zone2_not_zone1(mock_load, monkeypatch):
    """DELOAD decision must produce Zone 2 work block, not Zone 1."""
    import datetime
    monkeypatch.setattr("plan_generator.date", type("D", (), {"today": staticmethod(lambda: datetime.date(2026, 6, 30)), "isoformat": datetime.date.isoformat, "weekday": lambda self: 1})())
    session = generate_session("DELOAD", {})
    work_block = next(b for b in session["blocks"] if b["name"] == "Work")
    assert work_block["zone"] == "zone2", f"Expected zone2, got {work_block['zone']}"

@patch("plan_generator._load_json", return_value=MOCK_STATE_WEEK3)
def test_deload_run_is_70pct_of_base(mock_load, monkeypatch):
    """DELOAD duration should be ~70% of the week's planned work_min (+warmup+cooldown)."""
    import datetime, math
    monkeypatch.setattr("plan_generator.date", type("D", (), {"today": staticmethod(lambda: datetime.date(2026, 6, 30)), "isoformat": datetime.date.isoformat, "weekday": lambda self: 1})())
    session = generate_session("DELOAD", {})
    work_block = next(b for b in session["blocks"] if b["name"] == "Work")
    # Week 3 Slot A work_min = 23. 70% = ceil(23 * 0.70) = 17
    assert work_block["duration_min"] == math.ceil(23 * 0.70)
```

- [ ] **Step 2: Run test to confirm it fails**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/test_plan_generator.py::test_deload_run_is_zone2_not_zone1 -v
```
Expected: FAIL — zone is "zone1"

- [ ] **Step 3: Replace the DELOAD branch in `generate_session()`**

Find (lines ~294–300):
```python
    # ── DELOAD ───────────────────────────────────────────────────────────────
    elif decision == "DELOAD":
        session_type = "deload"
        blocks = _deload_blocks()
        summary = (
            f"Deload run — {_total_min(blocks)} min total. "
            "Zone 1 only. Let the training from the past three weeks settle in."
        )
```

Replace with:
```python
    # ── DELOAD ───────────────────────────────────────────────────────────────
    elif decision == "DELOAD":
        session_type = "easy"
        work_min = ceil((base_work_min or 18) * 0.70)
        blocks = _easy_blocks(work_min)
        summary = (
            f"Deload run — {_total_min(blocks)} min total (~70% of planned). "
            "Zone 2 at your normal easy pace — same effort, less time."
        )
```

- [ ] **Step 4: Run tests to confirm they pass**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/test_plan_generator.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**
```
git commit -am "fix: deload runs now Zone 2 at 70% duration (Galpin protocol)"
```

---

## Task 2: Remove dead `_deload_blocks()` function

**Files:**
- Modify: `plan_generator.py` — `_deload_blocks()` (~lines 133–141)

- [ ] **Step 1: Confirm no other callers**
```
grep -n "_deload_blocks" ~/Documents/Claude/run-coach/plan_generator.py
```
Expected: only the function definition itself (no call sites after Task 1)

- [ ] **Step 2: Delete the function**

Remove these lines from `plan_generator.py`:
```python
def _deload_blocks() -> list:
    return [
        {"name": "Warmup",   "duration_min": _WARMUP_MIN,  "zone": "zone1",
         "notes": "Slow walk or very light jog."},
        {"name": "Work",     "duration_min": 10,            "zone": "zone1",
         "notes": "Very easy — this is active recovery, not a workout. Stay well below 130 bpm."},
        {"name": "Cooldown", "duration_min": _COOLDOWN_MIN, "zone": "zone1",
         "notes": "Easy walk to finish."},
    ]
```

Also remove `"deload"` from the `_blocks_for_type` match (~line 247):
```python
    elif session_type == "deload":
        return _deload_blocks()
```

- [ ] **Step 3: Run the full test suite**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/ -v
```
Expected: all PASS, no NameError on `_deload_blocks`

- [ ] **Step 4: Commit**
```
git commit -am "refactor: remove dead _deload_blocks() — superseded by Galpin protocol"
```

---

## Task 3: Fix strength DELOAD messaging

**Files:**
- Modify: `plan_generator.py` — `_STRENGTH_PHRASE` and `_STRENGTH_NOTES` dicts (~lines 178–192)
- Test: `tests/test_plan_generator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_plan_generator.py`:
```python
from plan_generator import generate_strength_session

@patch("plan_generator._load_json", return_value={"kb_weeks_elapsed": 0})
def test_strength_deload_messaging(mock_load):
    """Strength DELOAD should say 'same weight, half the sets' not 'light load'."""
    session = generate_strength_session("DELOAD", "mon")
    notes = session["blocks"][0]["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "half" in notes or "50%" in notes, f"Expected set reduction language: {notes}"
    assert "light" not in notes, f"'light' should not appear: {notes}"
```

- [ ] **Step 2: Run test to confirm it fails**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/test_plan_generator.py::test_strength_deload_messaging -v
```
Expected: FAIL

- [ ] **Step 3: Update the dicts**

Find and replace in `plan_generator.py`:

```python
# Before
_STRENGTH_PHRASE = {
    ...
    "DELOAD":   "Easy load only — deload week.",
    ...
}

_STRENGTH_NOTES = {
    ...
    "DELOAD":   "Deload week — keep loads light, cut sets if needed.",
    ...
}
```

```python
# After
_STRENGTH_PHRASE = {
    ...
    "DELOAD":   "Deload week — same weight, half the sets.",
    ...
}

_STRENGTH_NOTES = {
    ...
    "DELOAD":   "Deload week — keep the same weight as planned. Cut your sets to 50% of normal.",
    ...
}
```

- [ ] **Step 4: Run tests**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 5: Commit**
```
git commit -am "fix: strength deload now 'same weight, half the sets' (Galpin protocol)"
```

---

## Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the strength intensity class table**

Find this row in the `| Decision | Summary prefix | Implied action |` table:
```
| DELOAD | ⛔️ | Light load, cut sets |
```
Replace with:
```
| DELOAD | ⛔️ | Same weight, half the sets |
```

- [ ] **Step 2: Update the run deload description**

Find in the 4-week plan cycle table:
```
| 4 | Deload 20 min | Deload 20 min |
```
Replace with:
```
| 4 | Deload ~70% duration, Zone 2 | Deload ~70% duration, Zone 2 |
```

- [ ] **Step 3: Commit**
```
git commit -am "docs: update CLAUDE.md deload descriptions to match Galpin protocol"
```

---

## Task 5: Deploy to Pi

- [ ] **Step 1: Copy updated files**
```
scp ~/Documents/Claude/run-coach/plan_generator.py pi@192.168.1.136:~/run-coach/
```

- [ ] **Step 2: Restart service**
```
ssh pi@192.168.1.136 'sudo systemctl restart run-coach && systemctl status run-coach'
```
Expected: `Active: active (running)`

- [ ] **Step 3: Smoke test**
```
curl -s -X POST http://192.168.1.136:5001/healthkit \
  -H "Content-Type: application/json" \
  -d '{"hrv_last_night":55,"sleep_total_hrs":7.5,"sleep_deep_hrs":1.5,"load_pct":0}' \
  | python3 -m json.tool | grep -A5 '"blocks"'
```
Expected: Work block shows `"zone": "zone2"` when DELOAD fires

---

## Self-review

- **Spec coverage:** All three Galpin requirements covered — Zone 2 runs ✓, 70% duration ✓, same weight / half sets ✓
- **Placeholders:** None — all code is complete
- **Type consistency:** `generate_session` return shape unchanged; `generate_strength_session` return shape unchanged
