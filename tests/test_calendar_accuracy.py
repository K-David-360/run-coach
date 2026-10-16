# tests/test_calendar_accuracy.py
"""
Tests for calendar accuracy: per-slot run execution decisions and
strength-day decision display.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta
from calendar_generator import generate_ics

# Fixed anchor Monday, passed to generate_ics as `today` so these fixtures
# stay valid regardless of when the suite actually runs.
_MONDAY = date(2026, 6, 8)


def _day(weekday: int, week_offset: int = 0) -> str:
    """ISO date for a weekday (0=Mon .. 6=Sun) in the anchor week or a later week."""
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
    ics = generate_ics(state, today=_MONDAY)
    descs = _descriptions_on(ics, _ymd(mon))
    assert any("80% of your normal sets" in d for d in descs), descs


def test_strength_hold_has_no_guidance_line():
    """HOLD adds no callout — the base description is unchanged."""
    mon = _day(0)
    state = _base_plan_state(last_execution_date=mon, last_execution_decision="HOLD")
    ics = generate_ics(state, today=_MONDAY)
    descs = _descriptions_on(ics, _ymd(mon))
    assert descs and all("Follow planned load" not in d for d in descs), descs


def test_strength_deload_week_guidance_not_doubled():
    """On a scheduled deload week the static wording is not duplicated by a live DELOAD."""
    mon = _day(0)
    state = _base_plan_state(
        cycle_start_date=(_MONDAY - timedelta(weeks=5)).isoformat(),
        last_execution_date=mon, last_execution_decision="DELOAD",
    )
    ics = generate_ics(state, today=_MONDAY)
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
    ics = generate_ics(state, today=_MONDAY)
    summaries = _events_on(ics, _ymd(tue))
    assert any("⬇️" in s for s in summaries), f"Expected ⬇️ in Tue summary, got: {summaries}"


def test_run_b_decision_visible_after_saturday_execution():
    """Saturday's BUILD decision should appear in the calendar as up-arrow."""
    sat = _day(5)
    state = _base_plan_state(
        last_run_b_execution_date=sat,
        last_run_b_decision="BUILD",
    )
    ics = generate_ics(state, today=_MONDAY)
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
    ics = generate_ics(state, today=_MONDAY)
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
    ics = generate_ics(state, today=_MONDAY)
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
    ics = generate_ics(state, today=_MONDAY)
    mon_summaries = _events_on(ics, _ymd(mon))
    assert any("⬇️" in s for s in mon_summaries), (
        f"Expected ⬇️ on Monday REDUCE, got: {mon_summaries}"
    )


def test_phase1_run_b_is_easy_zone2():
    """Phase 1: Saturday Run B is a plain easy Zone 2 run."""
    ics = generate_ics(_base_plan_state(phase=1), today=_MONDAY)
    sat_summaries = _events_on(ics, _ymd(_day(5)))
    assert any("Easy Run" in s for s in sat_summaries), sat_summaries
    assert not any("Progression" in s for s in sat_summaries), sat_summaries


def test_phase2_run_b_is_progression():
    """Phase 2: Saturday Run B becomes a progression run; Run A stays easy."""
    ics = generate_ics(_base_plan_state(phase=2), today=_MONDAY)
    sat_summaries = _events_on(ics, _ymd(_day(5)))
    tue_summaries = _events_on(ics, _ymd(_day(1)))
    assert any("Progression Run" in s for s in sat_summaries), sat_summaries
    assert any("Easy Run" in s for s in tue_summaries), tue_summaries


def test_phase2_lthr_test_event_absent():
    """Phase 2: the LTHR field test event is no longer scheduled."""
    state = _base_plan_state(phase=2, total_runs=20, lthr_test_date=_day(5, 2))
    ics = generate_ics(state, today=_MONDAY)
    assert "LTHR Field Test" not in ics


def _weeks_back(n: int) -> str:
    return (_MONDAY - timedelta(weeks=n)).isoformat()


def test_strength_events_are_push_pull_full():
    ics = generate_ics(_base_plan_state(), today=_MONDAY)
    for weekday, label in ((0, "Push"), (2, "Pull"), (4, "Full")):
        summaries = _events_on(ics, _ymd(_day(weekday)))
        assert any(s.endswith(label) for s in summaries), summaries
    assert "KB" not in ics
    assert "Lower Body" not in ics


def test_week1_events_carry_jump_target():
    ics = generate_ics(_base_plan_state(), today=_MONDAY)
    descs = _descriptions_on(ics, _ymd(_day(0)))
    assert any("weekly target 60" in d for d in descs), descs


def test_deload_week_keeps_all_three_lift_days():
    ics = generate_ics(_base_plan_state(cycle_start_date=_weeks_back(5)), today=_MONDAY)
    for weekday in (0, 2, 4):
        summaries = _events_on(ics, _ymd(_day(weekday)))
        descs = _descriptions_on(ics, _ymd(_day(weekday)))
        strength = [s for s in summaries if "🏋️" in s]
        assert strength and strength[0].startswith("⛔️"), summaries
        assert any("none this week (deload)" in d and "50% of normal" in d for d in descs), descs


def test_window_reaches_next_deload():
    ics = generate_ics(_base_plan_state(), today=_MONDAY)
    assert _events_on(ics, _ymd(_day(0, 5))), "week 6 (next deload) should be shown"
    ics4 = generate_ics(_base_plan_state(cycle_start_date=_weeks_back(4)), today=_MONDAY)
    assert _events_on(ics4, _ymd(_day(0, 3)))
    assert not _events_on(ics4, _ymd(_day(0, 4))), "only 4 weeks shown from cycle week 5"


def test_deload_run_is_70pct_of_week5():
    ics = generate_ics(_base_plan_state(phase=2, cycle_start_date=_weeks_back(5)), today=_MONDAY)
    assert "⛔️ 🏃‍♂️ Deload Run — 34 mins" in _events_on(ics, _ymd(_day(1)))


def test_pre_start_week_is_deload():
    ics = generate_ics(_base_plan_state(cycle_start_date=(_MONDAY + timedelta(weeks=1)).isoformat()), today=_MONDAY)
    strength = [s for s in _events_on(ics, _ymd(_day(0))) if "🏋️" in s]
    assert strength and strength[0].startswith("⛔️"), strength
