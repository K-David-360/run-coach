# tests/test_server_strength.py
"""Server-level strength-day tests: legacy state, jump skipping, no KB state."""
import datetime
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import plan_generator
import rule_engine
import server

PI_STATE = {  # shape of the real Pi file on 2026-10-15, synthetic values
    "current_week": 3, "cycle_start_date": "2026-10-26", "consecutive_suppress": 0, "total_runs": 5,
    "phase": 2, "kb_weeks_elapsed": 4, "kb_peak_rung": 15, "lthr_test_date": "2026-08-15",
    "lthr_test_tier": "urgent", "last_execution_date": "", "last_execution_decision": "",
}

GOOD = {"hrv_last_night": 60, "sleep_total_hrs": 8, "sleep_deep_hrs": 1.5, "resting_hr": 50, "load_pct": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    state_file = tmp_path / "plan_state.json"
    history_file = tmp_path / "history.json"
    state_file.write_text(json.dumps(PI_STATE))
    history_file.write_text("[]")
    for mod in (server, plan_generator, rule_engine):
        monkeypatch.setattr(mod, "PLAN_STATE_FILE", str(state_file))
    monkeypatch.setattr(server, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(rule_engine, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(server, "CURRENT_SESSION_FILE", str(tmp_path / "current_session.json"))
    monkeypatch.setattr(server, "GITHUB_TOKEN", "")

    def on(day):
        class _Fixed(datetime.date):
            @classmethod
            def today(cls):
                return day
        monkeypatch.setattr(server, "date", _Fixed)
        return server.app.test_client()

    on.state_file = state_file
    return on


def _post(c, **overrides):
    resp = c.post("/healthkit", json={**GOOD, **overrides})
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def _has_jumps(body):
    return any(b["name"] == "Jumps" for b in body["blocks"])


def test_legacy_state_with_kb_keys_loads(client):
    body = _post(client(datetime.date(2026, 10, 26)))
    assert body["type"] == "strength_mon"
    assert "KB" not in json.dumps(body)


def test_reduce_from_load_keeps_jumps(client):
    body = _post(client(datetime.date(2026, 10, 26)), load_pct=30)
    assert body["rule_fired"] == "REDUCE"
    assert _has_jumps(body)


def test_reduce_from_sleep_drops_jumps(client):
    body = _post(client(datetime.date(2026, 10, 26)), sleep_total_hrs=5.5)
    assert body["rule_fired"] == "REDUCE"
    assert not _has_jumps(body)


def test_server_no_longer_writes_kb_state(client):
    c = client(datetime.date(2026, 10, 28))  # Wednesday, HOLD: old code advanced the ladder
    body = _post(c)
    assert body["rule_fired"] == "HOLD"
    saved = json.loads(client.state_file.read_text())
    assert saved["kb_weeks_elapsed"] == 4
    assert saved["kb_peak_rung"] == 15
