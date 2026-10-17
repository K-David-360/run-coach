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


_BLOCK_STATE = {"cycle_start_date": "2026-10-26"}
_WEEK1_MON = datetime.date(2026, 10, 26)


def _strength(decision, day="mon", today=_WEEK1_MON, **kw):
    from plan_generator import generate_strength_session
    with patch("plan_generator._load_json", return_value=dict(_BLOCK_STATE)):
        return generate_strength_session(decision, day, today=today, **kw)


def _lift_block(session):
    return next(b for b in session["blocks"] if b["name"] != "Jumps")


def _has_jumps(session):
    return any(b["name"] == "Jumps" for b in session["blocks"])


def test_strength_deload_messaging():
    """Strength DELOAD should say 'same weight, half the sets' not 'light load'."""
    notes = _lift_block(_strength("DELOAD"))["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "half" in notes or "50%" in notes, f"Expected set reduction language: {notes}"
    assert "light" not in notes, f"'light' should not appear: {notes}"


def test_strength_reduce_messaging():
    """Strength REDUCE should say 'same weight, fewer sets' — not 'load' or 'light'."""
    notes = _lift_block(_strength("REDUCE"))["notes"].lower()
    assert "same weight" in notes, f"Expected 'same weight' in notes: {notes}"
    assert "set" in notes, f"Expected set-reduction language in notes: {notes}"
    assert "load" not in notes, f"'load' should not appear (implies weight cut): {notes}"


def test_labels_are_push_pull_full():
    for day, label in (("mon", "Push"), ("wed", "Pull"), ("fri", "Full")):
        summary = _strength("HOLD", day)["summary"]
        assert label in summary, summary
        for old in ("Lower", "Upper", "KB"):
            assert old not in summary, summary


def test_jumps_block_first_with_week1_prescription():
    first = _strength("HOLD")["blocks"][0]
    assert (first["name"], first["sets"], first["reps"]) == ("Jumps", 2, 10)
    assert "weekly target 60" in first["notes"]


def test_jumps_week5_three_sets():
    first = _strength("HOLD", today=datetime.date(2026, 11, 23))["blocks"][0]
    assert first["sets"] == 3
    assert "weekly target 90" in first["notes"]


def test_no_jumps_on_deload_or_suppress():
    assert not _has_jumps(_strength("DELOAD"))
    assert not _has_jumps(_strength("SUPPRESS"))


def test_no_jumps_when_skip_requested():
    assert not _has_jumps(_strength("REDUCE", skip_jumps=True))


def test_lift_menu_in_notes():
    assert "squat 3 x 5–8" in _lift_block(_strength("HOLD", "mon"))["notes"].lower()
    assert "trap-bar deadlift 3 x 5" in _lift_block(_strength("HOLD", "wed"))["notes"].lower()


def test_kb_ladder_gone():
    import plan_generator
    assert not hasattr(plan_generator, "kb_peak_from_weeks")


def test_phase3_interval_deload_uses_week5_easy_duration():
    # Saturday slot B is intervals (no work_min); deload falls back to the same week's slot A
    assert _work_min(3, 6, "DELOAD", today=datetime.date(2026, 11, 7))[0] == 24


def test_suppress_strength_is_no_lifting():
    session = _strength("SUPPRESS")
    notes = _lift_block(session)["notes"].lower()
    assert "no lifting" in notes and "walk" in notes, notes
    assert "squat" not in notes, notes


def test_phase1_runs_match_protocol_lengths():
    # Protocol: Tue 30–40 min, Sat 30–45 min; work + 10 min warm-up/cool-down.
    from plan_generator import _PLAN_PHASE1
    tue = [_PLAN_PHASE1[w]["A"]["work_min"] + 10 for w in range(1, 6)]
    sat = [_PLAN_PHASE1[w]["B"]["work_min"] + 10 for w in range(1, 6)]
    assert tue == [30, 32, 34, 36, 38]
    assert sat == [32, 34, 36, 38, 40]


def test_strength_reduce_is_65pct():
    assert "65%" in _lift_block(_strength("REDUCE"))["notes"]
