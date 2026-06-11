# tests/test_calendar_accuracy.py
"""
Tests for calendar accuracy: per-slot run execution decisions and
strength-day decision display.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from calendar_generator import generate_ics


def _base_plan_state(**overrides):
    state = {
        "current_week":                1,
        "cycle_start_date":            "2026-06-08",   # Monday
        "consecutive_suppress":        0,
        "total_runs":                  0,
        "phase":                       1,
        "last_execution_date":         "",
        "last_execution_type":         "",
        "last_execution_decision":     "",
        "last_run_a_execution_date":   "",
        "last_run_a_decision":         "",
        "last_run_b_execution_date":   "",
        "last_run_b_decision":         "",
        "kb_weeks_elapsed":            0,
        "kb_peak_rung":                10,
    }
    state.update(overrides)
    return state


def _events_on(ics: str, date_str: str) -> list:
    """Return all SUMMARY values for events on the given YYYYMMDD date string."""
    # Unfold RFC 5545 line continuations (CRLF + space/tab = continuation)
    unfolded = ics.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")
    lines = unfolded.splitlines()
    summaries = []
    in_event = False
    event_date = None
    summary = None
    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            event_date = None
            summary = None
        elif line.strip() == "END:VEVENT":
            if in_event and event_date == date_str and summary:
                summaries.append(summary)
            in_event = False
        elif in_event and line.startswith("DTSTART;VALUE=DATE:"):
            event_date = line.split(":")[1].strip()
        elif in_event and line.startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):]
    return summaries


def test_run_a_decision_visible_after_tuesday_execution():
    """Tuesday's REDUCE decision should appear in the calendar as down-arrow."""
    state = _base_plan_state(
        last_run_a_execution_date="2026-06-09",  # Tuesday
        last_run_a_decision="REDUCE",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, "20260609")
    assert any("⬇️" in s for s in summaries), f"Expected ⬇️ in Tue summary, got: {summaries}"


def test_run_b_decision_visible_after_saturday_execution():
    """Saturday's BUILD decision should appear in the calendar as up-arrow."""
    state = _base_plan_state(
        last_run_b_execution_date="2026-06-13",  # Saturday
        last_run_b_decision="BUILD",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, "20260613")
    assert any("⬆️" in s for s in summaries), f"Expected ⬆️ in Sat summary, got: {summaries}"


def test_tuesday_decision_survives_wednesday_execution():
    """After Wednesday fires, Tuesday's run decision must still show in calendar."""
    state = _base_plan_state(
        last_run_a_execution_date="2026-06-09",
        last_run_a_decision="REDUCE",
        last_execution_date="2026-06-10",        # Wednesday overwrote last_execution_date
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    tue_summaries = _events_on(ics, "20260609")
    assert any("⬇️" in s for s in tue_summaries), (
        f"Tuesday decision lost after Wed execution. Got: {tue_summaries}"
    )


def test_strength_event_shows_deload_decision():
    """Wednesday strength event should show ⛔️ when DELOAD fired on that day."""
    state = _base_plan_state(
        last_execution_date="2026-06-10",      # Wednesday
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    wed_summaries = _events_on(ics, "20260610")
    assert any("⛔️" in s for s in wed_summaries), (
        f"Expected ⛔️ on Wednesday DELOAD, got: {wed_summaries}"
    )


def test_strength_event_shows_reduce_decision():
    """Monday strength event should show ⬇️ when REDUCE fired on that day."""
    state = _base_plan_state(
        last_execution_date="2026-06-08",      # Monday
        last_execution_decision="REDUCE",
    )
    ics = generate_ics(state)
    mon_summaries = _events_on(ics, "20260608")
    assert any("⬇️" in s for s in mon_summaries), (
        f"Expected ⬇️ on Monday REDUCE, got: {mon_summaries}"
    )
