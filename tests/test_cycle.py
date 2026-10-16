# tests/test_cycle.py
from datetime import date
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cycle import block_week, week_in_cycle, is_deload_week, jump_prescription, DELOAD_EVERY_N_WEEKS

START = "2026-10-26"  # Monday


def test_week_in_cycle_runs_1_to_6_then_wraps():
    assert week_in_cycle(START, today=date(2026, 10, 26)) == 1
    assert week_in_cycle(START, today=date(2026, 11, 1)) == 1      # Sunday, same week
    assert week_in_cycle(START, today=date(2026, 11, 30)) == 6     # 5 weeks later
    assert week_in_cycle(START, today=date(2026, 12, 7)) == 1      # wraps


def test_before_start_is_deload():
    assert week_in_cycle(START, today=date(2026, 10, 19)) == DELOAD_EVERY_N_WEEKS
    assert block_week(START, today=date(2026, 10, 19)) == 0
    assert jump_prescription(START, today=date(2026, 10, 19)) == {"sets": 0, "reps": 10, "weekly_target": 0}


def test_bad_start_reads_as_week_one():
    for bad in ("", "not-a-date", None):
        assert week_in_cycle(bad, today=date(2026, 10, 26)) == 1
        assert block_week(bad, today=date(2026, 10, 26)) == 1


def test_is_deload_week():
    assert is_deload_week(6) and not is_deload_week(5) and not is_deload_week(1)


def test_jump_progression_skips_deload_weeks():
    # block week -> (sets, weekly_target), per handoff 6.3b mapping table
    expected = {1: (2, 60), 4: (2, 60), 5: (3, 90), 6: (0, 0), 7: (3, 90), 11: (3, 90), 12: (0, 0)}
    for bw, (sets, target) in expected.items():
        monday = date(2026, 10, 26).toordinal() + (bw - 1) * 7
        rx = jump_prescription(START, today=date.fromordinal(monday))
        assert (rx["sets"], rx["weekly_target"]) == (sets, target), bw
