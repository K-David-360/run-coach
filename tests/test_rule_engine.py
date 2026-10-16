# tests/test_rule_engine.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch

from rule_engine import rule_engine


def _run(current_week=1, load="steady", hrv_ratio=1.0, sleep_total=8.0, sleep_deep=1.5):
    state = {"current_week": current_week, "consecutive_suppress": 0, "phase": 2}

    def fake_load(path, default=None):
        return dict(state) if path.endswith("plan_state.json") else []

    data = {
        "recovery": {"hrv_last_night": 60.0, "hrv_7d_avg": 60.0, "resting_hr": 0},
        "sleep": {"total_hrs": sleep_total, "deep_hrs": sleep_deep},
        "load": {"classification": load},
    }
    with patch("rule_engine._load_json", side_effect=fake_load):
        return rule_engine(data, hrv_ratio)


def test_week6_is_scheduled_deload():
    result = _run(current_week=6)
    assert result["decision"] == "DELOAD"
    assert result["trigger"] == "deload_week"


def test_week4_is_no_longer_deload():
    assert _run(current_week=4)["decision"] == "HOLD"


def test_reduce_from_load_has_load_trigger():
    result = _run(load="above")
    assert result["decision"] == "REDUCE"
    assert result["trigger"] == "load"


def test_reduce_from_sleep_has_sleep_trigger():
    result = _run(sleep_total=5.5)
    assert result["decision"] == "REDUCE"
    assert result["trigger"] == "sleep"


def test_reduce_from_hrv_has_hrv_trigger():
    result = _run(hrv_ratio=0.65)
    assert result["decision"] == "REDUCE"
    assert result["trigger"] == "hrv"


def test_action_text_uses_galpin_wording():
    for result in (_run(current_week=6), _run(load="above")):
        action = result["action"].lower()
        assert "lower body" not in action, action
        assert "same weight" in action, action
