# tests/test_bodycomp_routes.py — synthetic data only
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import bodycomp.config as bc_config
import bodycomp.store as bc_store
import server

DAYS = ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31"]


def _samples(value, days=DAYS):
    return "\n".join(f"{d}={value}" for d in days)


def _weekly(week_ending="2026-10-31", weight=150, days=DAYS):
    return {"week_ending": week_ending, "weight_samples": _samples(weight, days),
            "protein_samples": _samples(128, days), "energy_samples": _samples(2100, days),
            "steps_samples": _samples(7100, days)}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("BODYCOMP_TOKEN", raising=False)
    files = {
        "weekly": tmp_path / "bodycomp" / "weekly.json",
        "measurements": tmp_path / "bodycomp" / "measurements.json",
        "config": tmp_path / "bodycomp" / "config.json",
        "state": tmp_path / "plan_state.json",
        "history": tmp_path / "history.json",
        "session": tmp_path / "current_session.json",
    }
    files["state"].write_text(json.dumps({"cycle_start_date": "2026-10-26", "phase": 2}))
    files["history"].write_text("[]")
    files["session"].write_text(json.dumps({"type": "rest"}))
    monkeypatch.setattr(bc_store, "WEEKLY_FILE", str(files["weekly"]))
    monkeypatch.setattr(bc_store, "MEASUREMENTS_FILE", str(files["measurements"]))
    monkeypatch.setattr(bc_config, "CONFIG_FILE", str(files["config"]))
    monkeypatch.setattr(server, "PLAN_STATE_FILE", str(files["state"]))
    monkeypatch.setattr(server, "HISTORY_FILE", str(files["history"]))
    monkeypatch.setattr(server, "CURRENT_SESSION_FILE", str(files["session"]))
    files["client"] = server.app.test_client()
    return files


def test_weekly_returns_banner_and_stores_report(env):
    resp = env["client"].post("/bodycomp/weekly", json=_weekly())
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["notification"].startswith("Weekly: weight")
    assert len(json.loads(env["weekly"].read_text())) == 1


def test_weekly_rerun_same_week_replaces(env):
    prior_days = ["2026-10-18", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]
    c = env["client"]
    c.post("/bodycomp/weekly", json=_weekly("2026-10-24", 149.0, prior_days))
    c.post("/bodycomp/weekly", json=_weekly(weight=150.0))
    c.post("/bodycomp/weekly", json=_weekly(weight=150.5))
    weeks = json.loads(env["weekly"].read_text())
    assert [w["week_ending"] for w in weeks] == ["2026-10-24", "2026-10-31"]
    assert weeks[-1]["metrics"]["delta_lb"] == 1.5   # vs the prior week, not vs the first post


def test_weekly_rejects_bad_week_ending(env):
    c = env["client"]
    assert c.post("/bodycomp/weekly", json=_weekly("2026-10-30")).status_code == 400
    body = _weekly()
    del body["week_ending"]
    assert c.post("/bodycomp/weekly", json=body).status_code == 400


def test_weekly_requires_token_when_configured(env, monkeypatch):
    monkeypatch.setenv("BODYCOMP_TOKEN", "abc")
    c = env["client"]
    assert c.post("/bodycomp/weekly", json=_weekly()).status_code == 401
    assert c.post("/bodycomp/weekly", json=_weekly(), headers={"X-Bodycomp-Token": "abc"}).status_code == 200


def test_weekly_does_not_touch_daily_files(env):
    before = (env["session"].read_bytes(), env["state"].read_bytes())
    env["client"].post("/bodycomp/weekly", json=_weekly())
    assert (env["session"].read_bytes(), env["state"].read_bytes()) == before


def test_weekly_bad_config_returns_500(env):
    env["config"].parent.mkdir(parents=True, exist_ok=True)
    env["config"].write_text(json.dumps({"bc_phase": "3"}))
    resp = env["client"].post("/bodycomp/weekly", json=_weekly())
    assert resp.status_code == 500
    assert "bc_phase must be BC-1 or BC-2" in resp.get_json()["error"]


def test_measurements_route_stores_ratio(env):
    resp = env["client"].post("/bodycomp/measurements",
                              json={"date": "2026-11-01", "shoulders_in": 46.0, "waist_in": 32.0})
    assert resp.status_code == 200
    stored = json.loads(env["measurements"].read_text())
    assert stored[0]["shoulder_waist_ratio"] == 1.44


def test_measurements_route_rejects_empty(env):
    assert env["client"].post("/bodycomp/measurements", json={"date": "2026-11-01"}).status_code == 400


def test_packet_route_markdown_and_auth(env, monkeypatch):
    c = env["client"]
    resp = c.get("/bodycomp/review-packet")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/markdown")
    monkeypatch.setenv("BODYCOMP_TOKEN", "abc")
    assert c.get("/bodycomp/review-packet").status_code == 401
