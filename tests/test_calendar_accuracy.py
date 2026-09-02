# tests/test_calendar_accuracy.py
"""
Tests for calendar accuracy: per-slot run execution decisions and
strength-day decision display.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from calendar_generator import generate_ics

# The calendar anchors to the current week's Monday, so tests must use
# dates relative to today rather than hardcoded calendar dates.
_MONDAY = date.today() - timedelta(days=date.today().weekday())


def _day(weekday: int, week_offset: int = 0) -> str:
    """ISO date for a weekday (0=Mon .. 6=Sun) in the current or a later week."""
    return (_MONDAY + timedelta(weeks=week_offset, days=weekday)).isoformat()


def _ymd(iso: str) -> str:
    """YYYY-MM-DD -> YYYYMMDD (the form DTSTART uses)."""
    return iso.replace("-", "")


def _base_plan_state(**overrides):
    state = {
        "current_week":                1,
        "cycle_start_date":            _MONDAY.isoformat(),
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


def _descriptions_on(ics: str, date_str: str) -> list:
    """Return all DESCRIPTION values for events on the given YYYYMMDD date string."""
    unfolded = ics.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")
    lines = unfolded.splitlines()
    descriptions = []
    in_event = False
    event_date = None
    description = None
    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            event_date = None
            description = None
        elif line.strip() == "END:VEVENT":
            if in_event and event_date == date_str and description is not None:
                descriptions.append(description)
            in_event = False
        elif in_event and line.startswith("DTSTART;VALUE=DATE:"):
            event_date = line.split(":")[1].strip()
        elif in_event and line.startswith("DESCRIPTION:"):
            description = line[len("DESCRIPTION:"):]
    return descriptions


def test_strength_reduce_appends_set_guidance():
    """A REDUCE strength day spells out the set cut in the calendar description."""
    mon = _day(0)
    state = _base_plan_state(last_execution_date=mon, last_execution_decision="REDUCE")
    ics = generate_ics(state)
    descs = _descriptions_on(ics, _ymd(mon))
    assert any("80% of your normal sets" in d for d in descs), descs


def test_strength_hold_has_no_guidance_line():
    """HOLD adds no callout — the base description is unchanged."""
    mon = _day(0)
    state = _base_plan_state(last_execution_date=mon, last_execution_decision="HOLD")
    ics = generate_ics(state)
    descs = _descriptions_on(ics, _ymd(mon))
    assert descs and all("Follow planned load" not in d for d in descs), descs


def test_strength_deload_week_guidance_not_doubled():
    """On a scheduled deload week the static wording is not duplicated by a live DELOAD."""
    mon = _day(0)
    state = _base_plan_state(
        current_week=4, cycle_start_date=(_MONDAY - timedelta(weeks=3)).isoformat(),
        last_execution_date=mon, last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    descs = _descriptions_on(ics, _ymd(mon))
    assert descs, descs
    assert descs[0].count("50% of normal") == 1, descs


def test_run_a_decision_visible_after_tuesday_execution():
    """Tuesday's REDUCE decision should appear in the calendar as down-arrow."""
    tue = _day(1)
    state = _base_plan_state(
        last_run_a_execution_date=tue,
        last_run_a_decision="REDUCE",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, _ymd(tue))
    assert any("⬇️" in s for s in summaries), f"Expected ⬇️ in Tue summary, got: {summaries}"


def test_run_b_decision_visible_after_saturday_execution():
    """Saturday's BUILD decision should appear in the calendar as up-arrow."""
    sat = _day(5)
    state = _base_plan_state(
        last_run_b_execution_date=sat,
        last_run_b_decision="BUILD",
    )
    ics = generate_ics(state)
    summaries = _events_on(ics, _ymd(sat))
    assert any("⬆️" in s for s in summaries), f"Expected ⬆️ in Sat summary, got: {summaries}"


def test_tuesday_decision_survives_wednesday_execution():
    """After Wednesday fires, Tuesday's run decision must still show in calendar."""
    tue, wed = _day(1), _day(2)
    state = _base_plan_state(
        last_run_a_execution_date=tue,
        last_run_a_decision="REDUCE",
        last_execution_date=wed,                 # Wednesday overwrote last_execution_date
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    tue_summaries = _events_on(ics, _ymd(tue))
    assert any("⬇️" in s for s in tue_summaries), (
        f"Tuesday decision lost after Wed execution. Got: {tue_summaries}"
    )


def test_strength_event_shows_deload_decision():
    """Wednesday strength event should show ⛔️ when DELOAD fired on that day."""
    wed = _day(2)
    state = _base_plan_state(
        last_execution_date=wed,
        last_execution_decision="DELOAD",
    )
    ics = generate_ics(state)
    wed_summaries = _events_on(ics, _ymd(wed))
    assert any("⛔️" in s for s in wed_summaries), (
        f"Expected ⛔️ on Wednesday DELOAD, got: {wed_summaries}"
    )


def test_strength_event_shows_reduce_decision():
    """Monday strength event should show ⬇️ when REDUCE fired on that day."""
    mon = _day(0)
    state = _base_plan_state(
        last_execution_date=mon,
        last_execution_decision="REDUCE",
    )
    ics = generate_ics(state)
    mon_summaries = _events_on(ics, _ymd(mon))
    assert any("⬇️" in s for s in mon_summaries), (
        f"Expected ⬇️ on Monday REDUCE, got: {mon_summaries}"
    )


def test_phase1_run_b_is_easy_zone2():
    """Phase 1: Saturday Run B is a plain easy Zone 2 run."""
    ics = generate_ics(_base_plan_state(phase=1))
    sat_summaries = _events_on(ics, _ymd(_day(5)))
    assert any("Easy Run" in s for s in sat_summaries), sat_summaries
    assert not any("Progression" in s for s in sat_summaries), sat_summaries


def test_phase2_run_b_is_progression():
    """Phase 2: Saturday Run B becomes a progression run; Run A stays easy."""
    ics = generate_ics(_base_plan_state(phase=2))
    sat_summaries = _events_on(ics, _ymd(_day(5)))
    tue_summaries = _events_on(ics, _ymd(_day(1)))
    assert any("Progression Run" in s for s in sat_summaries), sat_summaries
    assert any("Easy Run" in s for s in tue_summaries), tue_summaries


def test_phase2_lthr_test_event_absent():
    """Phase 2: the LTHR field test event is no longer scheduled."""
    state = _base_plan_state(phase=2, total_runs=20, lthr_test_date=_day(5, 2))
    ics = generate_ics(state)
    assert "LTHR Field Test" not in ics
