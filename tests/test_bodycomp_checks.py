# tests/test_bodycomp_checks.py — synthetic data only (weights ~180 lb, thresholds unlike any real ones)
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from bodycomp.checks import coerce_value, summarize_week, validate_payload, week_days, weekly_check
from bodycomp.config import DEFAULTS


# ── Payload, coercion, validation ─────────────────────────────────────────────

def test_week_days_sun_to_sat():
    assert week_days("2026-10-31") == ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28",
                                       "2026-10-29", "2026-10-30", "2026-10-31"]


def test_week_days_rejects_non_saturday():
    with pytest.raises(ValueError):
        week_days("2026-10-30")


def test_coerce_treats_blank_null_zero_as_missing():
    for raw in ("", None, 0, "0", "junk", "inf", "nan"):
        assert coerce_value(raw) is None, raw


def test_coerce_keeps_zero_when_allowed():
    assert coerce_value(0, allow_zero=True) == 0.0
    assert coerce_value("", allow_zero=True) is None


def test_coerce_strips_thousands_and_units():
    assert coerce_value("1,234") == 1234.0
    assert coerce_value("12,345 steps") == 12345.0
    assert coerce_value("180.4 lb") == 180.4
    assert coerce_value("72,5") == 72.5      # decimal comma
    assert coerce_value(181) == 181.0


def _payload(weights=(180,) * 7, protein=(150,) * 7, kcal=(2100,) * 7, steps=(7100,) * 7,
             sleep=(7.5,) * 7, week_ending="2026-10-31", **extra):
    p = {"week_ending": week_ending, "weights_lb": list(weights), "protein_g_daily": list(protein),
         "energy_kcal_daily": list(kcal), "steps_daily": list(steps), "sleep_hrs_daily": list(sleep)}
    p.update(extra)
    return p


def test_validate_accepts_good_payload():
    assert validate_payload(_payload()) is None


def test_validate_rejects_wrong_length_and_missing_arrays():
    assert "weights_lb" in validate_payload(_payload(weights=(180,) * 6))
    bad = _payload()
    del bad["sleep_hrs_daily"]
    assert "sleep_hrs_daily" in validate_payload(bad)


def test_validate_rejects_non_saturday():
    assert "Saturday" in validate_payload(_payload(week_ending="2026-10-30"))
    assert "Saturday" in validate_payload(_payload(week_ending=""))


def test_summarize_counts_present_days():
    m = summarize_week(_payload(weights=(180, None, 181, "", 182, 0, None)))
    assert (m["weight_days"], m["avg_weight_lb"]) == (3, 181.0)


def test_summarize_steps_zero_is_real():
    m = summarize_week(_payload(steps=(0, 0, 0, 0, 0, 0, 7000)))
    assert (m["steps_days"], m["avg_steps"]) == (7, 1000)


def test_summarize_lift_sessions_optional():
    assert summarize_week(_payload())["lift_sessions_done"] is None
    assert summarize_week(_payload(lift_sessions_done=0))["lift_sessions_done"] == 0
    assert summarize_week(_payload(lift_sessions_done="2"))["lift_sessions_done"] == 2


# ── Rules, report and banner ──────────────────────────────────────────────────

def _past(avg, week_ending, delta=None, bc_phase="BC-1", weight_days=7):
    return {"week_ending": week_ending, "bc_phase": bc_phase,
            "metrics": {"avg_weight_lb": avg, "delta_lb": delta, "weight_days": weight_days}, "results": []}


def _check(payload=None, past=(), cycle_start="2026-10-26", **cfg):
    return weekly_check(payload or _payload(), list(past), dict(DEFAULTS, **cfg), cycle_start)


def _ids(report, severity=None):
    return {r["id"] for r in report["results"]
            if r["severity"] != "OK" and (severity is None or r["severity"] == severity)}


def _result(report, rule_id):
    return next(r for r in report["results"] if r["id"] == rule_id)


SHORT = (6.0, 6.2, 6.1, 7.5, 7.5, 7.5, 7.5)


def test_banner_matches_spec_example():
    report = _check(_payload(sleep=SHORT), past=[_past(179.8, "2026-10-24")])
    assert report["banner"] == "Weekly: weight 180.0 (+0.2), protein OK, steps 7.1k, 1 amber (sleep)."
    assert report["highest"] == "AMBER"


def test_first_week_no_delta():
    report = _check()
    assert report["metrics"]["delta_lb"] is None
    assert report["banner"].startswith("Weekly: weight 180.0 (new)")
    assert not _ids(report) & {"W2", "W3", "W4"}


def test_insufficient_week_not_used_for_delta():
    # an intro week with one weigh-in must not anchor next week's delta
    report = _check(past=[_past(185.0, "2026-10-24", weight_days=1)])
    assert report["metrics"]["delta_lb"] is None
    assert "W3" not in _ids(report)


def test_later_week_not_used_for_delta_on_backfill():
    report = _check(past=[_past(179.0, "2026-10-24"), _past(190.0, "2026-11-07")])
    assert report["metrics"]["delta_lb"] == 1.0


def test_insufficient_weight_days():
    report = _check(_payload(weights=(180, 180, 180, None, None, None, None)))
    assert any(r["message"] == "insufficient data" and r["id"] == "W" for r in report["results"])
    assert "weight n/a" in report["banner"]


def test_insufficient_nutrition_days():
    report = _check(_payload(protein=(150, 150, 150, 150, None, None, None)), protein_low_g=100, protein_avg_min_g=120)
    assert any(r["message"] == "insufficient data" and r["id"] == "P" for r in report["results"])
    assert not _ids(report) & {"P1", "P2", "P3"}


def test_unconfigured_thresholds_report_not_configured():
    report = _check()
    for rule_id in ("W1", "P1", "P2", "E1"):
        assert (_result(report, rule_id)["severity"], _result(report, rule_id)["message"]) == ("OK", "not configured")


def test_w1_uses_config_baseline():
    payload = _payload(weights=(181.2,) * 7)
    assert "W1" in _ids(_check(payload, baseline_weight_lb=180.0), "INFO")
    assert _result(_check(payload, baseline_weight_lb=181.0), "W1")["message"] == "Weight holding"


def test_w2_needs_two_consecutive_fast_weeks():
    assert "W2" in _ids(_check(past=[_past(181.1, "2026-10-24", delta=-1.2)]))
    assert "W2" not in _ids(_check(past=[_past(181.1, "2026-10-24", delta=-0.5)]))
    assert "W2" not in _ids(_check(past=[_past(181.0, "2026-10-24", delta=-1.2)]))  # exactly -1.0


def test_w3_only_after_early_window_in_bc1():
    past = [_past(180.5, "2026-10-24")]
    assert "W3" not in _ids(_check(past=past, bc_phase_start_date="2026-10-19"))           # bc_week 2
    assert "W3" in _ids(_check(past=past, bc_phase_start_date="2026-10-12"), "AMBER")      # bc_week 3
    assert "W3" not in _ids(_check(past=[_past(180.5, "2026-10-24", bc_phase="BC-2")], bc_phase="BC-2",
                                   bc_phase_start_date="2026-10-12"))


def test_w4_bc2_only_three_flat_weeks():
    past = [_past(179.9, "2026-10-17", delta=0.1, bc_phase="BC-2"), _past(180.0, "2026-10-24", delta=-0.1, bc_phase="BC-2")]
    assert "W4" in _ids(_check(past=past, bc_phase="BC-2"), "INFO")
    assert "W4" not in _ids(_check(past=past))
    past[0]["metrics"]["delta_lb"] = 0.2
    assert "W4" not in _ids(_check(past=past, bc_phase="BC-2"))


def test_p2_red_supersedes_p1():
    cfg = {"protein_low_g": 100, "protein_avg_min_g": 120}
    low = _check(_payload(protein=(95,) * 7), **cfg)
    assert "P2" in _ids(low, "RED") and "P1" not in _ids(low)
    assert "P1" in _ids(_check(_payload(protein=(110,) * 7), **cfg), "AMBER")
    at = _check(_payload(protein=(100,) * 7), **cfg)
    assert "P1" in _ids(at, "AMBER") and "P2" not in _ids(at)


def test_p3_g_per_kg():
    p3 = _result(_check(_payload(weights=(154.32,) * 7, protein=(105,) * 7)), "P3")
    assert (p3["severity"], p3["message"]) == ("INFO", "Protein 1.50 g/kg")


def test_e1_floor_by_phase():
    payload = _payload(kcal=(1950,) * 7)
    assert "E1" in _ids(_check(payload, kcal_floor_bc1=2000, kcal_floor_bc2=1900), "AMBER")
    assert "E1" not in _ids(_check(payload, bc_phase="BC-2", kcal_floor_bc1=2000, kcal_floor_bc2=1900))


def test_s1_threshold_boundary():
    assert "S1" not in _ids(_check(_payload(sleep=(6.5, 6.5, 6.5, 8, 8, 8, 8))))
    assert "S1" in _ids(_check(_payload(sleep=(6.4, 6.4, 6.4, 8, 8, 8, 8))), "AMBER")


def test_l2_optional_and_l1_gone():
    assert "L2" not in _ids(_check())
    report = _check(_payload(lift_sessions_done=2, lift_stalled=True, waist_in=33))
    assert "L2" in _ids(report, "INFO")
    assert "L1" not in {r["id"] for r in report["results"]}
    assert "waist_in" not in report["metrics"] and "lift_stalled" not in report["metrics"]


def test_d1_when_next_week_is_deload():
    assert "D1" in _ids(_check(cycle_start="2026-09-28"), "INFO")
    assert "D1" not in _ids(_check(cycle_start="2026-10-26"))


def test_severity_order_in_banner():
    report = _check(_payload(weights=(120,) * 7, protein=(100,) * 7, steps=(5000,) * 7,
                             sleep=(6.0, 6.0, 6.0, 8, 8, 8, 8)), protein_low_g=105)
    assert report["banner"] == ("Weekly: weight 120.0 (new), protein red, steps 5.0k, "
                                "1 red (protein low), 1 amber (sleep), 1 info (steps).")
    assert report["highest"] == "RED"


def test_bc_phase_never_changes():
    for phase in ("BC-1", "BC-2"):
        assert _check(bc_phase=phase)["bc_phase"] == phase
