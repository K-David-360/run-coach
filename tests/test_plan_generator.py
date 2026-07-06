import pytest
import math
from unittest.mock import patch

MOCK_STATE_WEEK3 = {
    "current_week": 3,
    "run_in_week": 0,
    "phase": 1,
    "kb_weeks_elapsed": 0,
    "kb_peak_rung": 10,
}

@patch("plan_generator._load_json", return_value=MOCK_STATE_WEEK3)
def test_deload_run_is_zone2_not_zone1(mock_load):
    """DELOAD decision must produce Zone 2 work block, not Zone 1."""
    from plan_generator import generate_session
    session = generate_session("DELOAD", {})
    work_block = next(b for b in session["blocks"] if b["name"] == "Work")
    assert work_block["zone"] == "zone2", f"Expected zone2, got {work_block['zone']}"

@patch("plan_generator._load_json", return_value=MOCK_STATE_WEEK3)
def test_deload_run_is_70pct_of_base(mock_load):
    """DELOAD duration should be ~70% of the week's planned work_min."""
    import datetime
    from plan_generator import generate_session
    # Slot depends on weekday: A on Tuesday (1), B otherwise
    weekday = datetime.date.today().weekday()
    if weekday == 1:
        # Week 3 Slot A work_min = 23
        expected = math.ceil(23 * 0.70)
    else:
        # Week 3 Slot B work_min = 25
        expected = math.ceil(25 * 0.70)
    session = generate_session("DELOAD", {})
    work_block = next(b for b in session["blocks"] if b["name"] == "Work")
    assert work_block["duration_min"] == expected, (
        f"Expected {expected} (70% of week 3 base), got {work_block['duration_min']}"
    )

@patch("plan_generator._load_json", return_value={"kb_weeks_elapsed": 0})
def test_strength_deload_messaging(mock_load):
    """Strength DELOAD should say 'same weight, half the sets' not 'light load'."""
    from plan_generator import generate_strength_session
    session = generate_strength_session("DELOAD", "mon")
    notes = session["blocks"][0]["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "half" in notes or "50%" in notes, f"Expected set reduction language: {notes}"
    assert "light" not in notes, f"'light' should not appear: {notes}"

@patch("plan_generator._load_json", return_value={"kb_weeks_elapsed": 0})
def test_strength_reduce_messaging(mock_load):
    """Strength REDUCE should say 'same weight, fewer sets' — not 'load' or 'light'."""
    from plan_generator import generate_strength_session
    session = generate_strength_session("REDUCE", "mon")
    notes = session["blocks"][0]["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "set" in notes, f"Expected set-reduction language in notes: {notes}"
    assert "load" not in notes, f"'load' should not appear (implies weight cut): {notes}"
