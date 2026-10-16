# tests/test_bodycomp_telegram.py — synthetic data only
import re
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from bodycomp.checks import weekly_check
from bodycomp.config import DEFAULTS
from bodycomp.telegram import allowed_fields, build_message, send

CONFIG = dict(DEFAULTS, protein_low_g=101, protein_avg_min_g=121, kcal_floor_bc1=2001, kcal_floor_bc2=1901,
              baseline_weight_lb=183.0)


def _report(delta_week=True):
    payload = {"week_ending": "2026-10-31", "weights_lb": [180.0] * 7, "protein_g_daily": [150] * 7,
               "energy_kcal_daily": [2100] * 7, "steps_daily": [7100] * 7,
               "sleep_hrs_daily": [6.0, 6.2, 6.1, 7.9, 7.9, 7.9, 7.9]}
    past = [{"week_ending": "2026-10-24", "bc_phase": "BC-1",
             "metrics": {"avg_weight_lb": 179.8, "delta_lb": None, "weight_days": 7}, "results": []}]
    return weekly_check(payload, past if delta_week else [], CONFIG, "2026-10-26")


def test_flags_tier_has_no_numbers():
    text = build_message(allowed_fields(_report()), "flags")
    assert text.startswith("Weekly check:")
    assert "amber (sleep" in text
    assert not re.search(r"\d", text), text


def test_trends_tier_contents():
    text = build_message(allowed_fields(_report()), "trends")
    assert text.startswith("Weekly check (w/e Oct 31):")
    for part in ("weight +0.2 lb", "protein 150 g avg", "steps 7.1k", "sleep 7.1 h", "amber (sleep"):
        assert part in text, (part, text)


@pytest.mark.parametrize("detail", ["flags", "trends", "full"])
def test_no_absolute_or_config_values_at_any_tier(detail):
    text = build_message(allowed_fields(_report()), detail)
    for secret in ("180", "179.8", "183", "2100", "2,100", "2.1k", "101", "121", "2001", "1901"):
        assert secret not in text, (secret, text)


def test_full_falls_back_to_trends_with_warning(caplog):
    fields = allowed_fields(_report())
    with caplog.at_level("WARNING"):
        assert build_message(fields, "full") == build_message(fields, "trends")
    assert "full" in caplog.text


def test_missing_prior_week_omits_delta():
    text = build_message(allowed_fields(_report(delta_week=False)), "trends")
    assert "weight change n/a" in text


def test_builder_accepts_only_allowlisted_fields():
    fields = allowed_fields(_report())
    assert set(fields) == {"week_ending", "flags", "protein_status", "weight_delta_lb",
                           "protein_avg_g", "steps_avg", "sleep_avg_hrs"}
    with pytest.raises(ValueError):
        build_message({**fields, "avg_weight_lb": 180.0}, "trends")


def test_send_without_credentials_does_nothing():
    calls = []
    assert send("hi", "", "123", post=lambda *a, **k: calls.append(1)) is False
    assert send("hi", "tok", "", post=lambda *a, **k: calls.append(1)) is False
    assert calls == []


def test_send_failure_is_swallowed():
    def boom(*a, **k):
        raise ConnectionError("down")
    assert send("hi", "tok", "123", post=boom) is False


def test_send_success_posts_to_chat():
    seen = {}

    class _Resp:
        ok = True

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, json=json)
        return _Resp()

    assert send("hi", "tok", "123", post=fake_post) is True
    assert seen["url"].endswith("/bottok/sendMessage")
    assert seen["json"] == {"chat_id": "123", "text": "hi"}
