import datetime
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

class _FixedDate(datetime.date):
    """date subclass whose today() is pinned, for slot selection by weekday."""
    fixed = datetime.date(2026, 11, 3)  # Tuesday -> slot A

    @classmethod
    def today(cls):
        return cls.fixed


def _work_min(phase, week, decision, today=datetime.date(2026, 11, 3)):
    from plan_generator import generate_session
    state = {"current_week": week, "phase": phase}
    _FixedDate.fixed = today
    with patch("plan_generator._load_json", return_value=state), \
         patch("plan_generator.date", _FixedDate):
        session = generate_session(decision, {})
    return next(b for b in session["blocks"] if b["name"] in ("Work", "Easy"))["duration_min"], session


def test_week6_deload_is_70pct_of_week5():
    assert _work_min(2, 6, "DELOAD")[0] == math.ceil(33 * 0.70) == 24


def test_early_deload_in_build_week_uses_that_week():
    assert _work_min(2, 2, "DELOAD")[0] == math.ceil(27 * 0.70) == 19


def test_week5_hold_phase2_run_a():
    assert _work_min(2, 5, "HOLD")[0] == 33


def test_phase3_run_a_holds_weeks_3_to_5():
    assert [_work_min(3, w, "HOLD")[0] for w in (3, 4, 5)] == [33, 33, 33]


def test_run_a_is_easy_in_every_phase_and_week():
    from plan_generator import _PLAN_BY_PHASE
    for phase, table in _PLAN_BY_PHASE.items():
        for week in range(1, 6):
            assert table[week]["A"]["type"] == "easy", (phase, week)


def test_deload_work_min_floor():
    from plan_generator import deload_work_min
    assert deload_work_min(None) == 13
    assert deload_work_min(5) == 8


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
