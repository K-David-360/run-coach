# tests/test_week_logic.py
from datetime import date
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import _week_from_cycle_start, _most_recent_monday


# ── _week_from_cycle_start ────────────────────────────────────────────────────

def test_week1_on_cycle_start_day():
    start = date(2026, 6, 8)  # Monday
    assert _week_from_cycle_start("2026-06-08", today=start) == 1

def test_week1_last_day():
    start = date(2026, 6, 8)
    sunday = date(2026, 6, 14)  # 6 days after Monday = Sunday
    assert _week_from_cycle_start("2026-06-08", today=sunday) == 1

def test_week2_starts_on_second_monday():
    start = date(2026, 6, 8)
    second_monday = date(2026, 6, 15)
    assert _week_from_cycle_start("2026-06-08", today=second_monday) == 2

def test_week3():
    start = date(2026, 6, 8)
    third_monday = date(2026, 6, 22)
    assert _week_from_cycle_start("2026-06-08", today=third_monday) == 3

def test_week4():
    start = date(2026, 6, 8)
    fourth_monday = date(2026, 6, 29)
    assert _week_from_cycle_start("2026-06-08", today=fourth_monday) == 4

def test_week6_is_last_week_of_cycle():
    assert _week_from_cycle_start("2026-06-08", today=date(2026, 7, 13)) == 6

def test_cycle_rolls_to_week1_after_six_weeks():
    assert _week_from_cycle_start("2026-06-08", today=date(2026, 7, 20)) == 1

def test_before_cycle_start_is_deload_week():
    assert _week_from_cycle_start("2026-06-08", today=date(2026, 6, 7)) == 6

def test_invalid_cycle_start_returns_1():
    assert _week_from_cycle_start("", today=date(2026, 6, 9)) == 1
    assert _week_from_cycle_start("not-a-date", today=date(2026, 6, 9)) == 1

def test_tuesday_of_week1_is_still_week1():
    start = date(2026, 6, 9)
    tuesday = date(2026, 6, 10)
    assert _week_from_cycle_start("2026-06-09", today=tuesday) == 1

def test_saturday_of_week4_is_still_week4():
    start = date(2026, 6, 9)
    week4_saturday = date(2026, 7, 4)
    assert _week_from_cycle_start("2026-06-09", today=week4_saturday) == 4


# ── _most_recent_monday ───────────────────────────────────────────────────────

def test_most_recent_monday_when_today_is_monday():
    monday = date(2026, 6, 8)
    assert _most_recent_monday(monday) == monday

def test_most_recent_monday_when_today_is_wednesday():
    wednesday = date(2026, 6, 10)
    assert _most_recent_monday(wednesday) == date(2026, 6, 8)

def test_most_recent_monday_when_today_is_sunday():
    sunday = date(2026, 6, 14)
    assert _most_recent_monday(sunday) == date(2026, 6, 8)
