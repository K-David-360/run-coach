# tests/test_plan_wording.py
"""User-facing text (session summaries, calendar events, Shortcut banners) matches the plan."""
import datetime
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from calendar_generator import generate_ics
from plan_generator import generate_session, generate_strength_session
from rule_engine import rule_engine
from test_calendar_accuracy import _MONDAY, _base_plan_state, _day, _descriptions_on, _events_on, _ymd
from test_server_strength import _post, client  # noqa: F401  (pytest fixture)

_INTRO_MON = datetime.date(2026, 10, 19)   # week before cycle_start 2026-10-26
_WEEK1_MON = datetime.date(2026, 10, 26)
_STATE = {"cycle_start_date": "2026-10-26", "current_week": 1, "phase": 1}


class _Tue(datetime.date):
    @classmethod
    def today(cls):
        return datetime.date(2026, 10, 27)


def _rule(today):
    data = {"recovery": {"hrv_last_night": 60.0, "hrv_7d_avg": 60.0, "resting_hr": 0},
            "sleep": {"total_hrs": 8.0, "deep_hrs": 1.5}, "load": {"classification": "steady"}}
    fake = lambda path, default=None: dict(_STATE, current_week=6) if path.endswith("plan_state.json") else []
    with patch("rule_engine._load_json", side_effect=fake):
        return rule_engine(data, 1.0, today=today)


# ── Rule engine ──────────────────────────────────────────────────────────────

def test_intro_week_reason_is_not_week6():
    result = _rule(_INTRO_MON)
    assert result["decision"] == "DELOAD"
    assert result["trigger"] == "intro_week"
    assert "Intro week" in result["reason"]


# ── Session text ─────────────────────────────────────────────────────────────

@patch("plan_generator._load_json", return_value=_STATE)
def test_build_strength_summary_has_no_push_harder(_):
    summary = generate_strength_session("BUILD", "mon", today=_WEEK1_MON)["summary"]
    assert "Push it" not in summary
    assert "Full planned session" in summary


@patch("plan_generator._load_json", return_value=_STATE)
def test_intro_week_strength_wording(_):
    session = generate_strength_session("DELOAD", "mon", today=_INTRO_MON)
    assert "Intro week" in session["summary"]
    assert "Deload" not in session["summary"]


@patch("plan_generator._load_json", return_value=_STATE)
def test_suppress_run_is_walk_only(_):
    with patch("plan_generator.date", _Tue):
        session = generate_session("SUPPRESS", {})
    assert session["type"] == "walk"
    assert session["summary"].startswith("Recovery walk")
    assert all(b["zone"] == "zone1" for b in session["blocks"])


# ── Calendar ─────────────────────────────────────────────────────────────────

def test_calendar_intro_week_labels():
    state = _base_plan_state(cycle_start_date=(_MONDAY + datetime.timedelta(weeks=1)).isoformat())
    ics = generate_ics(state, today=_MONDAY)
    assert any("Intro Week Run" in s for s in _events_on(ics, _ymd(_day(1))))
    descs = _descriptions_on(ics, _ymd(_day(0)))
    assert any("none this week (intro week)" in d for d in descs), descs
    # The following week is block week 1, not intro.
    assert not any("Intro" in s for s in _events_on(ics, _ymd(_day(1, 1))))


def test_calendar_saturday_is_marked_optional():
    ics = generate_ics(_base_plan_state(), today=_MONDAY)
    assert any("incline walk" in d for d in _descriptions_on(ics, _ymd(_day(5))))
    assert not any("incline walk" in d for d in _descriptions_on(ics, _ymd(_day(1))))


def test_calendar_suppress_lift_day_has_no_lift_menu():
    state = _base_plan_state(last_execution_date=_day(0), last_execution_decision="SUPPRESS")
    descs = [d for d in _descriptions_on(generate_ics(state, today=_MONDAY), _ymd(_day(0))) if "lifting" in d]
    assert descs and "Squat" not in descs[0] and "Jumps" not in descs[0], descs


def test_calendar_suppress_run_is_recovery_walk():
    state = _base_plan_state(last_run_a_execution_date=_day(1), last_run_a_decision="SUPPRESS")
    summaries = _events_on(generate_ics(state, today=_MONDAY), _ymd(_day(1)))
    assert any("🚶 Recovery Walk" in s for s in summaries), summaries


# ── Shortcut banners ─────────────────────────────────────────────────────────

def test_lift_and_run_banners_differ(client):  # noqa: F811
    lift = _post(client(datetime.date(2026, 10, 26)))
    run = _post(client(datetime.date(2026, 10, 27)))
    assert lift["notification"] == "✅ On track — follow today's lift plan."
    assert run["notification"] == "✅ On track — run as planned."


def test_reduce_lift_banner_says_same_weight_and_skip_jumps(client):  # noqa: F811
    body = _post(client(datetime.date(2026, 10, 26)), sleep_total_hrs=5.5)
    assert body["rule_fired"] == "REDUCE"
    assert "same weight" in body["notification"]
    assert body["notification"].endswith("Skip jumps.")


def test_reduce_from_load_keeps_jumps_in_banner(client):  # noqa: F811
    body = _post(client(datetime.date(2026, 10, 26)), load_pct=30)
    assert "Skip jumps" not in body["notification"]


def test_intro_week_banner(client):  # noqa: F811
    body = _post(client(datetime.date(2026, 10, 19)))
    assert body["notification"].startswith("⛔️ Intro week")
    assert body["decision_reason"] == "Intro week (deload volume)"


def test_rest_day_summaries(client):  # noqa: F811
    assert _post(client(datetime.date(2026, 10, 29)))["summary"] == "Rest Day — walk and mobility"
    assert _post(client(datetime.date(2026, 11, 1)))["summary"] == "Rest Day — meal prep"


def test_calendar_saturday_recovery_walk_has_no_optional_run_note():
    state = _base_plan_state(last_run_b_execution_date=_day(5), last_run_b_decision="SUPPRESS")
    ics = generate_ics(state, today=_MONDAY)
    assert any("Recovery Walk" in s for s in _events_on(ics, _ymd(_day(5))))
    assert not any("incline walk" in d for d in _descriptions_on(ics, _ymd(_day(5))))
    # Next Saturday (no decision yet) still gets the note.
    assert any("incline walk" in d for d in _descriptions_on(ics, _ymd(_day(5, 1))))
