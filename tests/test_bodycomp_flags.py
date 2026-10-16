# tests/test_bodycomp_flags.py — synthetic data only
import datetime
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import bodycomp.store as bc_store
import plan_generator
import rule_engine
import server
from bodycomp.flags import OPTIONAL_RUN_NOTE, S1_NOTE, s1_active
from calendar_generator import generate_ics

S1_REPORT = {"week_ending": "2026-10-31", "bc_phase": "BC-1",
             "metrics": {"avg_weight_lb": 180.0, "avg_protein_g": 150.0},
             "results": [{"id": "S1", "severity": "AMBER", "message": "Sleep short"}]}

GOOD = {"hrv_last_night": 60, "sleep_total_hrs": 8, "sleep_deep_hrs": 1.5, "resting_hr": 50, "load_pct": 0}


def test_s1_active_window():
    d = datetime.date
    assert s1_active(S1_REPORT, d(2026, 11, 1)) and s1_active(S1_REPORT, d(2026, 11, 7))
    assert not s1_active(S1_REPORT, d(2026, 10, 31))
    assert not s1_active(S1_REPORT, d(2026, 11, 8))


def test_s1_inactive_without_amber():
    info = dict(S1_REPORT, results=[{"id": "S1", "severity": "INFO", "message": "x"}])
    none = dict(S1_REPORT, results=[])
    for report in (info, none, None):
        assert not s1_active(report, datetime.date(2026, 11, 2))


@pytest.fixture
def daily(tmp_path, monkeypatch):
    state_file = tmp_path / "plan_state.json"
    history_file = tmp_path / "history.json"
    weekly_file = tmp_path / "bodycomp" / "weekly.json"
    session_file = tmp_path / "current_session.json"
    state_file.write_text(json.dumps({"cycle_start_date": "2026-10-26", "phase": 2}))
    history_file.write_text("[]")
    for mod in (server, plan_generator, rule_engine):
        monkeypatch.setattr(mod, "PLAN_STATE_FILE", str(state_file))
    monkeypatch.setattr(server, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(rule_engine, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(server, "CURRENT_SESSION_FILE", str(session_file))
    monkeypatch.setattr(bc_store, "WEEKLY_FILE", str(weekly_file))
    monkeypatch.setattr(server, "GITHUB_TOKEN", "")

    def on(day):
        class _Fixed(datetime.date):
            @classmethod
            def today(cls):
                return day
        monkeypatch.setattr(server, "date", _Fixed)
        return server.app.test_client()

    on.files = {"state": state_file, "history": history_file, "weekly": weekly_file, "session": session_file}
    return on


def _store(daily, content):
    daily.files["weekly"].parent.mkdir(parents=True, exist_ok=True)
    daily.files["weekly"].write_text(content if isinstance(content, str) else json.dumps(content))


def test_strength_day_gets_note_and_no_jumps(daily):
    _store(daily, [S1_REPORT])
    body = daily(datetime.date(2026, 11, 2)).post("/healthkit", json=GOOD).get_json()
    names = [b["name"] for b in body["blocks"]]
    assert "Jumps" not in names
    assert {"name": "Weekly check", "notes": S1_NOTE} in body["blocks"]


def test_saturday_optional_on_low_hrv(daily):
    history = [{"session": {"date": "2026-10-2%d" % i}, "run_data": {"recovery": {"hrv_last_night": 60}}}
               for i in range(5, 8)]
    daily.files["history"].write_text(json.dumps(history))
    body = daily(datetime.date(2026, 10, 31)).post("/healthkit", json={**GOOD, "hrv_last_night": 48}).get_json()
    assert body["summary"].endswith(OPTIONAL_RUN_NOTE)


def test_daily_output_survives_corrupt_store(daily):
    _store(daily, "not json")
    assert daily(datetime.date(2026, 11, 2)).post("/healthkit", json=GOOD).status_code == 200


def test_no_bodycomp_numbers_in_daily_files(daily):
    _store(daily, [S1_REPORT])
    daily(datetime.date(2026, 11, 2)).post("/healthkit", json=GOOD)
    session_text = daily.files["session"].read_text()
    assert "bodycomp" not in json.loads(session_text)
    assert "180.0" not in session_text and "150.0" not in session_text
    ics = generate_ics(json.loads(daily.files["state"].read_text()), today=datetime.date(2026, 11, 2))
    assert S1_NOTE not in ics and "Weekly check" not in ics
