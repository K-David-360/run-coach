# Reduce Tier Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development (recommended) or superpowers-executing-plans to implement this plan task-by-task.

**Goal:** Align REDUCE day strength messaging with the Galpin protocol — same weight, ~80% of sets — instead of the current "80% of planned load" (which wrongly implies cutting weight).
**Architecture:** Two string changes in `plan_generator.py` (`_STRENGTH_PHRASE` and `_STRENGTH_NOTES`), plus a `CLAUDE.md` doc update. Runs are already correct (85% duration, same zone) and need no changes.
**Tech Stack:** Python 3, Flask (no new dependencies)

Reference: `docs/training_intensity_tiers.md`

---

## Why runs need no change

The REDUCE branch in `generate_session()` already does:
```python
work_min = max(8, ceil((base_work_min or 18) * 0.85))
blocks = _blocks_for_type(base_type, work_min)
```
`_easy_blocks()` produces Zone 2. That is correct per the Galpin protocol (same zone, ~85% duration). No code change required for runs.

---

## File map

| File | Change |
|------|--------|
| `plan_generator.py` | Update `_STRENGTH_PHRASE["REDUCE"]` and `_STRENGTH_NOTES["REDUCE"]` |
| `CLAUDE.md` | Update the strength intensity class table REDUCE row |

---

## Task 1: Fix strength REDUCE messaging

**Files:**
- Modify: `plan_generator.py` — `_STRENGTH_PHRASE` and `_STRENGTH_NOTES` dicts (~lines 178–192)
- Test: `tests/test_plan_generator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_plan_generator.py`:
```python
from unittest.mock import patch
from plan_generator import generate_strength_session

@patch("plan_generator._load_json", return_value={"kb_weeks_elapsed": 0})
def test_strength_reduce_messaging(mock_load):
    """Strength REDUCE should say 'same weight, fewer sets' — not 'load' or 'light'."""
    session = generate_strength_session("REDUCE", "mon")
    notes = session["blocks"][0]["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "set" in notes, f"Expected set-reduction language in notes: {notes}"
    assert "load" not in notes, f"'load' should not appear (implies weight cut): {notes}"
```

- [ ] **Step 2: Run test to confirm it fails**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/test_plan_generator.py::test_strength_reduce_messaging -v
```
Expected: FAIL — notes contain "load", not "same weight"

- [ ] **Step 3: Update the dicts**

In `plan_generator.py`, find:
```python
_STRENGTH_PHRASE = {
    "BUILD":    "Push it today.",
    "HOLD":     "Follow the plan.",
    "REDUCE":   "Pull back — 80% of planned load.",
    "DELOAD":   "Deload week — same weight, half the sets.",
    "SUPPRESS": "Easy load only.",
}

_STRENGTH_NOTES = {
    "BUILD":    "Recovery looks strong — lift at full planned load.",
    "HOLD":     "Follow planned load.",
    "REDUCE":   "Back off — work at roughly 80% of planned load.",
    "DELOAD":   "Deload week — keep the same weight as planned. Cut your sets to 50% of normal.",
    "SUPPRESS": "Skip if feeling rough. If you lift, keep it very easy.",
}
```

Replace with:
```python
_STRENGTH_PHRASE = {
    "BUILD":    "Push it today.",
    "HOLD":     "Follow the plan.",
    "REDUCE":   "Pull back — same weight, drop to ~80% of your sets.",
    "DELOAD":   "Deload week — same weight, half the sets.",
    "SUPPRESS": "Easy load only.",
}

_STRENGTH_NOTES = {
    "BUILD":    "Recovery looks strong — lift at full planned load.",
    "HOLD":     "Follow planned load.",
    "REDUCE":   "Back off on volume — keep the same weight as planned. Drop to roughly 80% of your normal sets.",
    "DELOAD":   "Deload week — keep the same weight as planned. Cut your sets to 50% of normal.",
    "SUPPRESS": "Skip if feeling rough. If you lift, keep it very easy.",
}
```

- [ ] **Step 4: Run all tests**
```
cd ~/Documents/Claude/run-coach && python3 -m pytest tests/ -v
```
Expected: all PASS

- [ ] **Step 5: Commit**
```
git commit -am "fix: strength REDUCE now 'same weight, 80% of sets' (Galpin protocol)"
```

---

## Task 2: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the strength intensity class table**

Find:
```
| REDUCE | ⬇️ | ~80% of planned load |
```
Replace with:
```
| REDUCE | ⬇️ | Same weight, ~80% of sets |
```

- [ ] **Step 2: Commit**
```
git commit -am "docs: update CLAUDE.md REDUCE description to match Galpin protocol"
```

---

## Task 3: Deploy to Pi

- [ ] **Step 1: Copy updated file**
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
  -d '{"hrv_last_night":55,"sleep_total_hrs":6.0,"sleep_deep_hrs":1.0,"load_pct":30}' \
  | python3 -m json.tool | grep -A3 '"notes"'
```
Expected: strength notes contain "same weight" and "sets", not "load"

---

## Self-review

- **Spec coverage:** Strength REDUCE messaging fixed ✓. Run REDUCE confirmed correct, no change needed ✓. CLAUDE.md updated ✓.
- **Placeholders:** None
- **Type consistency:** `generate_strength_session` return shape unchanged
