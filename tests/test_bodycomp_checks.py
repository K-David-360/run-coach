# tests/test_bodycomp_checks.py — synthetic data only
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from bodycomp.checks import parse_samples, sleep_nights, summarize_week, week_days

DAYS = week_days("2026-10-31")


def _samples(values, days=DAYS):
    """7 per-day values (None = no sample) -> Shortcut-style 'date=value' text."""
    return "\n".join(f"{d}={v}" for d, v in zip(days, values) if v is not None)


def _history(nights):
    """[(date, total_hrs)] -> history.json-shaped entries."""
    return [{"session": {"date": d}, "run_data": {"sleep": {"total_hrs": h}}} for d, h in nights]


def test_week_days_sun_to_sat():
    assert DAYS == ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28",
                    "2026-10-29", "2026-10-30", "2026-10-31"]


def test_week_days_rejects_non_saturday():
    with pytest.raises(ValueError):
        week_days("2026-10-30")


def test_parse_mean_ignores_blanks_zero_junk_and_out_of_window():
    text = "2026-10-25=150.0\n2026-10-25=151.0\n2026-10-26=\n2026-10-27=0\nbad line\n2026-11-01=149\n2026-10-28=149.5"
    assert parse_samples(text, DAYS, "mean") == [150.5, None, None, 149.5, None, None, None]


def test_parse_sum_adds_meals_per_day():
    assert parse_samples("2026-10-25=40\n2026-10-25=50\n2026-10-25=38", DAYS, "sum")[0] == 128.0


def test_sleep_nights_from_history():
    hist = _history([("2026-10-26", 6.0), ("2026-10-27", 7.2), ("2026-10-28", 0), ("2026-11-01", 5.0)])
    assert sleep_nights(hist, DAYS) == [6.0, 7.2]


def test_summarize_counts_present_days():
    payload = {"week_ending": "2026-10-31", "weight_samples": _samples([150, None, 151, None, 152, None, None])}
    m = summarize_week(payload, [])
    assert m["weight_days"] == 3
    assert m["avg_weight_lb"] == 151.0


def test_summarize_optional_fields_blank():
    m = summarize_week({"week_ending": "2026-10-31", "waist_in": "", "lift_sessions_done": "", "lift_stalled": ""}, [])
    assert (m["waist_in"], m["lift_sessions_done"], m["lift_stalled"]) == (None, None, None)
