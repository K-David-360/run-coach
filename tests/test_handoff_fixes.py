# tests/test_handoff_fixes.py — HANDOFF §5 deferred issues; synthetic values only.
import datetime
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import bodycomp.store as bc_store
import plan_generator
import rule_engine
import server
from bodycomp.config import load_config
from bodycomp.flags import S1_NOTE, S1_NOTE_LOW_DAY
from cycle import block_week, week_in_cycle

d = datetime.date
GOOD = {"hrv_last_night": 60, "sleep_total_hrs": 8, "sleep_deep_hrs": 1.5, "resting_hr": 50, "load_pct": 0}
S1_REPORT = {"week_ending": "2026-10-31", "bc_phase": "BC-1", "metrics": {},
             "results": [{"id": "S1", "severity": "AMBER", "message": "Sleep short"}]}


# ── Training rework ───────────────────────────────────────────────────────────

def test_non_monday_cycle_start_snaps_to_its_monday():
    # A Wednesday start counts from that week's Monday, matching the Monday-evaluated calendar.
    assert block_week("2026-10-28", today=d(2026, 10, 26)) == 1
    assert block_week("2026-10-28", today=d(2026, 10, 25)) == 0
    assert week_in_cycle("2026-10-28", today=d(2026, 11, 2)) == 2


def test_generate_session_uses_injected_today(monkeypatch):
    monkeypatch.setattr(plan_generator, "_load_json", lambda *a, **k: {"current_week": 1, "phase": 1})
    session = plan_generator.generate_session("HOLD", {}, today=d(2026, 10, 27))  # Tuesday
    assert session["date"] == "2026-10-27"
    assert session["slot"] == "A"


def test_count_nights_below_uses_injected_today(monkeypatch):
    history = [{"session": {"date": "2026-10-20"}, "run_data": {"sleep": {"total_hrs": 4.0}}}]
    monkeypatch.setattr(rule_engine, "_load_json", lambda *a, **k: history)
    assert rule_engine._count_nights_below(5.0, days=7, today=d(2026, 10, 22)) == 1
    assert rule_engine._count_nights_below(5.0, days=7, today=d(2026, 11, 22)) == 0


@pytest.fixture
def daily(tmp_path, monkeypatch):
    state_file = tmp_path / "plan_state.json"
    history_file = tmp_path / "history.json"
    state_file.write_text(json.dumps({"cycle_start_date": "2026-10-26", "phase": 1, "current_week": 3}))
    history_file.write_text("[]")
    for mod in (server, plan_generator, rule_engine):
        monkeypatch.setattr(mod, "PLAN_STATE_FILE", str(state_file))
    monkeypatch.setattr(server, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(rule_engine, "HISTORY_FILE", str(history_file))
    monkeypatch.setattr(server, "CURRENT_SESSION_FILE", str(tmp_path / "current_session.json"))
    monkeypatch.setattr(bc_store, "WEEKLY_FILE", str(tmp_path / "bodycomp" / "weekly.json"))
    monkeypatch.setattr(server, "GITHUB_TOKEN", "")

    def on(day):
        class _Fixed(datetime.date):
            @classmethod
            def today(cls):
                return day
        for mod in (server, plan_generator, rule_engine):
            monkeypatch.setattr(mod, "date", _Fixed)
        return server.app.test_client()

    on.state_file = state_file
    on.weekly_file = tmp_path / "bodycomp" / "weekly.json"
    return on


def test_pre_start_tuesday_is_deload_30_min(daily):
    # Tue Oct 20 is before the Oct 26 start: reads as deload, phase-1 deload run ceil(28*0.7) + 10 = 30 min.
    body = daily(d(2026, 10, 20)).post("/healthkit", json=GOOD).get_json()
    assert body["rule_fired"] == "DELOAD"
    assert "30 min" in body["summary"]


def test_legacy_run_route_recomputes_current_week(daily):
    payload = {"recovery": {"hrv_last_night": 60, "hrv_7d_avg": 60},
               "sleep": {"total_hrs": 8, "deep_hrs": 1.5}, "load": {"classification": "steady"}}
    daily(d(2026, 11, 3)).post("/run", json=payload)   # block week 2
    assert json.loads(daily.state_file.read_text())["current_week"] == 2


# ── Body-comp ─────────────────────────────────────────────────────────────────

def test_config_null_gives_clear_error(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("null")
    with pytest.raises(ValueError, match="JSON object"):
        load_config(str(p))


def test_config_string_threshold_gives_clear_error(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"protein_avg_min_g": "150"}))
    with pytest.raises(ValueError, match="protein_avg_min_g"):
        load_config(str(p))


def test_config_null_generic_threshold_gives_clear_error(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"steps_min_avg": None}))
    with pytest.raises(ValueError, match="steps_min_avg"):
        load_config(str(p))


def test_config_personal_threshold_may_be_null(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"protein_avg_min_g": None, "kcal_floor_bc1": 1234}))
    assert load_config(str(p))["kcal_floor_bc1"] == 1234


def test_s1_note_on_deload_day_drops_set_wording(daily):
    daily.weekly_file.parent.mkdir(parents=True, exist_ok=True)
    daily.weekly_file.write_text(json.dumps([S1_REPORT]))
    # Mon Nov 2 with a 'well_above' load → DELOAD; the S1 note must not say "~65% of sets".
    body = daily(d(2026, 11, 2)).post("/healthkit", json={**GOOD, "load_pct": 80}).get_json()
    assert body["debug"]["decision"] == "DELOAD"
    notes = [b["notes"] for b in body["blocks"] if b["name"] == "Weekly check"]
    assert notes == [S1_NOTE_LOW_DAY]
    assert "80%" not in S1_NOTE_LOW_DAY


def test_s1_note_on_hold_day_is_full_wording(daily):
    daily.weekly_file.parent.mkdir(parents=True, exist_ok=True)
    daily.weekly_file.write_text(json.dumps([S1_REPORT]))
    body = daily(d(2026, 11, 2)).post("/healthkit", json=GOOD).get_json()
    assert [b["notes"] for b in body["blocks"] if b["name"] == "Weekly check"] == [S1_NOTE]


def test_store_write_is_atomic(tmp_path, monkeypatch):
    path = str(tmp_path / "weekly.json")
    bc_store.save_week({"week_ending": "2026-10-31", "results": []}, path)
    before = open(path).read()

    def boom(*a, **k):
        raise RuntimeError("crash mid-write")
    monkeypatch.setattr(bc_store.json, "dump", boom)
    with pytest.raises(RuntimeError):
        bc_store.save_week({"week_ending": "2026-11-07", "results": []}, path)
    assert open(path).read() == before
    assert os.listdir(tmp_path) == ["weekly.json"]   # no temp file left behind
