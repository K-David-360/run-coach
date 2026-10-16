# tests/test_bodycomp_routes.py — synthetic data only
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import bodycomp.config as bc_config
import bodycomp.store as bc_store
import bodycomp.telegram as bc_telegram
import server

SECRET = {"X-Bodycomp-Secret": "s3cret"}


def _weekly(week_ending="2026-10-31", weight=180):
    return {"week_ending": week_ending, "weights_lb": [weight] * 7, "protein_g_daily": [150] * 7,
            "energy_kcal_daily": [2100] * 7, "steps_daily": [7100] * 7, "sleep_hrs_daily": [7.5] * 7}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BODYCOMP_SECRET", "s3cret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    files = {
        "weekly": tmp_path / "bodycomp" / "weekly.json",
        "reports": tmp_path / "bodycomp" / "reports",
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
    monkeypatch.setattr(bc_store, "REPORTS_DIR", str(files["reports"]))
    monkeypatch.setattr(bc_store, "MEASUREMENTS_FILE", str(files["measurements"]))
    monkeypatch.setattr(bc_config, "CONFIG_FILE", str(files["config"]))
    monkeypatch.setattr(server, "PLAN_STATE_FILE", str(files["state"]))
    monkeypatch.setattr(server, "HISTORY_FILE", str(files["history"]))
    monkeypatch.setattr(server, "CURRENT_SESSION_FILE", str(files["session"]))
    sent = []
    monkeypatch.setattr(bc_telegram, "send", lambda text, token, chat_id, **k: sent.append((text, token, chat_id)) or True)
    files["sent"] = sent
    files["client"] = server.app.test_client()
    return files


def _post(env, body, headers=SECRET):
    return env["client"].post("/bodycomp/weekly", json=body, headers=headers)


def test_weekly_returns_banner_and_stores_report(env):
    resp = _post(env, _weekly())
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["notification"].startswith("Weekly: weight")
    assert len(json.loads(env["weekly"].read_text())) == 1
    assert json.loads((env["reports"] / "2026-10-31.json").read_text())["week_ending"] == "2026-10-31"


def test_weekly_rerun_same_week_replaces(env):
    _post(env, _weekly("2026-10-24", 179.0))
    _post(env, _weekly(weight=180.0))
    _post(env, _weekly(weight=180.5))
    weeks = json.loads(env["weekly"].read_text())
    assert [w["week_ending"] for w in weeks] == ["2026-10-24", "2026-10-31"]
    assert weeks[-1]["metrics"]["delta_lb"] == 1.5   # vs the prior week, not vs the first post


def test_weekly_rejects_bad_week_ending(env):
    assert _post(env, _weekly("2026-10-30")).status_code == 400
    body = _weekly()
    del body["week_ending"]
    assert _post(env, body).status_code == 400


def test_weekly_rejects_more_than_7_values(env):
    body = _weekly()
    body["steps_daily"] = [7100] * 8
    resp = _post(env, body)
    assert resp.status_code == 400
    assert "steps_daily" in resp.get_json()["error"]


def test_weekly_requires_secret(env, monkeypatch):
    assert _post(env, _weekly(), headers={}).status_code == 401
    assert _post(env, _weekly(), headers={"X-Bodycomp-Secret": "nope"}).status_code == 401
    monkeypatch.delenv("BODYCOMP_SECRET")
    assert _post(env, _weekly()).status_code == 503


def test_weekly_does_not_touch_daily_files(env):
    before = (env["session"].read_bytes(), env["state"].read_bytes())
    _post(env, _weekly())
    assert (env["session"].read_bytes(), env["state"].read_bytes()) == before


def test_weekly_bad_config_returns_500(env):
    env["config"].parent.mkdir(parents=True, exist_ok=True)
    env["config"].write_text(json.dumps({"bc_phase": "3"}))
    resp = _post(env, _weekly())
    assert resp.status_code == 500
    assert "bc_phase must be BC-1 or BC-2" in resp.get_json()["error"]


def test_weekly_sends_trends_message_to_configured_chat(env):
    _post(env, _weekly())
    (text, token, chat_id), = env["sent"]
    assert (token, chat_id) == ("tok", "42")
    assert text.startswith("Weekly check (w/e Oct 31):")
    assert "180" not in text and "2100" not in text


def test_weekly_survives_telegram_failure(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(bc_telegram, "send", boom)
    assert _post(env, _weekly()).status_code == 200
    assert len(json.loads(env["weekly"].read_text())) == 1


def test_report_latest(env):
    c = env["client"]
    assert c.get("/bodycomp/report/latest", headers=SECRET).status_code == 404
    _post(env, _weekly("2026-10-24"))
    _post(env, _weekly())
    resp = c.get("/bodycomp/report/latest", headers=SECRET)
    assert resp.status_code == 200 and resp.get_json()["week_ending"] == "2026-10-31"
    assert c.get("/bodycomp/report/latest").status_code == 401


def test_measurements_route_stores_ratio(env):
    resp = env["client"].post("/bodycomp/measurements", headers=SECRET,
                              json={"date": "2026-11-01", "shoulders_in": 46.0, "waist_in": 32.0})
    assert resp.status_code == 200
    stored = json.loads(env["measurements"].read_text())
    assert stored[0]["shoulder_waist_ratio"] == 1.44


def test_measurements_route_rejects_empty(env):
    assert env["client"].post("/bodycomp/measurements", headers=SECRET, json={"date": "2026-11-01"}).status_code == 400


def test_packet_route_markdown_and_auth(env):
    c = env["client"]
    resp = c.get("/bodycomp/review-packet", headers=SECRET)
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/markdown")
    assert c.get("/bodycomp/review-packet").status_code == 401
