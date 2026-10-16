# tests/test_bodycomp_checks.py — synthetic data only
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from bodycomp.checks import parse_samples, sleep_nights, summarize_week, week_days

DAYS = week_days("2026-10-31")


def _samples(values, days=DAYS):
    """7 per-day values (None = no sample) -> Shortcut-style 'date=value' text."""
    return "\n".join(f"{d}={v}" for d, v in zip(days, values) if v is not None)


def _history(nights):
    """[(date, total_hrs)] -> history.json-shaped entries."""
    return [{"session": {"date": d}, "run_data": {"sleep": {"total_hrs": h}}} for d, h in nights]


def test_week_days_sun_to_sat():
    assert DAYS == ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28",
                    "2026-10-29", "2026-10-30", "2026-10-31"]


def test_week_days_rejects_non_saturday():
    with pytest.raises(ValueError):
        week_days("2026-10-30")


def test_parse_mean_ignores_blanks_zero_junk_and_out_of_window():
    text = "2026-10-25=180.0\n2026-10-25=181.0\n2026-10-26=\n2026-10-27=0\nbad line\n2026-11-01=179\n2026-10-28=179.5"
    assert parse_samples(text, DAYS, "mean") == [180.5, None, None, 179.5, None, None, None]


def test_parse_sum_adds_meals_per_day():
    assert parse_samples("2026-10-25=40\n2026-10-25=60\n2026-10-25=50", DAYS, "sum")[0] == 150.0


def test_sleep_nights_from_history():
    hist = _history([("2026-10-26", 6.0), ("2026-10-27", 7.2), ("2026-10-28", 0), ("2026-11-01", 5.0)])
    assert sleep_nights(hist, DAYS) == [6.0, 7.2]


def test_summarize_counts_present_days():
    payload = {"week_ending": "2026-10-31", "weight_samples": _samples([180, None, 181, None, 182, None, None])}
    m = summarize_week(payload, [])
    assert m["weight_days"] == 3
    assert m["avg_weight_lb"] == 181.0


def test_summarize_optional_fields_blank():
    m = summarize_week({"week_ending": "2026-10-31", "waist_in": "", "lift_sessions_done": "", "lift_stalled": ""}, [])
    assert (m["waist_in"], m["lift_sessions_done"], m["lift_stalled"]) == (None, None, None)


# ── Task 3: rules, report and banner ──────────────────────────────────────────

from bodycomp.checks import weekly_check
from bodycomp.config import DEFAULTS

_GOOD_SLEEP = [("2026-10-26", 7.5), ("2026-10-27", 7.5), ("2026-10-28", 7.5)]


def _payload(weights=(180,) * 7, protein=(150,) * 7, kcal=(2100,) * 7, steps=(7100,) * 7, **extra):
    p = {"week_ending": "2026-10-31", "weight_samples": _samples(list(weights)),
         "protein_samples": _samples(list(protein)), "energy_samples": _samples(list(kcal)),
         "steps_samples": _samples(list(steps))}
    p.update(extra)
    return p


def _past(avg, week_ending, delta=None, bc_phase="BC-1"):
    return {"week_ending": week_ending, "bc_phase": bc_phase,
            "metrics": {"avg_weight_lb": avg, "delta_lb": delta}, "results": []}


def _check(payload=None, past=(), history=_GOOD_SLEEP, cycle_start="2026-10-26", **cfg):
    config = dict(DEFAULTS, **cfg)
    return weekly_check(payload or _payload(), _history(list(history)), list(past), config, cycle_start)


def _ids(report, severity=None):
    return {r["id"] for r in report["results"] if r["severity"] != "OK" and (severity is None or r["severity"] == severity)}


def test_banner_matches_spec_example():
    sleep = [("2026-10-25", 6.0), ("2026-10-26", 6.2), ("2026-10-27", 6.1), ("2026-10-28", 7.5), ("2026-10-29", 7.5)]
    report = _check(past=[_past(179.8, "2026-10-24")], history=sleep)
    assert report["banner"] == "Weekly: weight 180.0 (+0.2), protein 150 g OK, steps 7.1k, 1 amber (sleep)."
    assert report["highest"] == "AMBER"


def test_first_week_no_delta():
    report = _check()
    assert report["metrics"]["delta_lb"] is None
    assert report["banner"].startswith("Weekly: weight 180.0 (new)")
    assert not _ids(report) & {"W2", "W3", "W4"}


def test_insufficient_weight_days():
    report = _check(_payload(weights=(180, 180, 180, None, None, None, None)))
    assert any(r["severity"] == "INFO" and r["message"] == "insufficient data" and r["id"].startswith("W")
               for r in report["results"])
    assert "weight n/a" in report["banner"]


def test_insufficient_nutrition_days():
    report = _check(_payload(protein=(150, 150, 150, 150, None, None, None)), protein_low_g=100, protein_avg_min_g=120)
    assert any(r["message"] == "insufficient data" and r["id"].startswith("P") for r in report["results"])
    assert not _ids(report) & {"P1", "P2", "P3"}


def test_w2_needs_two_consecutive_fast_weeks():
    assert "W2" in _ids(_check(past=[_past(181.1, "2026-10-24", delta=-1.2)]))
    assert "W2" not in _ids(_check(past=[_past(181.1, "2026-10-24", delta=-0.5)]))
    assert "W2" not in _ids(_check(past=[_past(181.0, "2026-10-24", delta=-1.2)]))  # exactly -1.0


def test_w3_only_after_early_window_in_bc1():
    past = [_past(180.5, "2026-10-24")]
    assert "W3" not in _ids(_check(past=past, bc_phase_start_date="2026-10-19"))   # bc_week 2
    assert "W3" in _ids(_check(past=past, bc_phase_start_date="2026-10-12"), "AMBER")  # bc_week 3
    assert "W3" not in _ids(_check(past=[_past(180.5, "2026-10-24", bc_phase="BC-2")], bc_phase="BC-2",
                                   bc_phase_start_date="2026-10-12"))


def test_w4_bc2_only_three_flat_weeks():
    past = [_past(179.9, "2026-10-17", delta=0.1, bc_phase="BC-2"), _past(180.0, "2026-10-24", delta=-0.1, bc_phase="BC-2")]
    assert "W4" in _ids(_check(past=past, bc_phase="BC-2"), "INFO")
    assert "W4" not in _ids(_check(past=past))
    past[0]["metrics"]["delta_lb"] = 0.2
    assert "W4" not in _ids(_check(past=past, bc_phase="BC-2"))


def test_w1_uses_config_or_first_bc1_week():
    payload = _payload(weights=(181.2,) * 7)
    assert "W1" in _ids(_check(payload, past=[_past(180.0, "2026-10-24")]), "INFO")
    assert "W1" not in _ids(_check(payload, past=[_past(180.0, "2026-10-24")], baseline_weight_lb=181.0))


def test_p2_red_supersedes_p1():
    cfg = {"protein_low_g": 100, "protein_avg_min_g": 120}
    low = _check(_payload(protein=(95,) * 7), **cfg)
    assert "P2" in _ids(low, "RED") and "P1" not in _ids(low)
    assert "P1" in _ids(_check(_payload(protein=(110,) * 7), **cfg), "AMBER")
    at = _check(_payload(protein=(100,) * 7), **cfg)
    assert "P1" in _ids(at, "AMBER") and "P2" not in _ids(at)


def test_protein_rules_skipped_without_thresholds():
    report = _check(_payload(protein=(60,) * 7))
    assert not _ids(report) & {"P1", "P2"}
    assert "P3" in _ids(report)


def test_p3_g_per_kg():
    report = _check(_payload(weights=(154.32,) * 7, protein=(105,) * 7))
    p3 = next(r for r in report["results"] if r["id"] == "P3")
    assert (p3["severity"], p3["message"]) == ("INFO", "Protein 1.50 g/kg")


def test_e1_floor_by_phase():
    payload = _payload(kcal=(1950,) * 7)
    assert "E1" in _ids(_check(payload, kcal_floor_bc1=2000, kcal_floor_bc2=1900), "AMBER")
    assert "E1" not in _ids(_check(payload, bc_phase="BC-2", kcal_floor_bc1=2000, kcal_floor_bc2=1900))


def test_s1_threshold_boundary():
    at = [("2026-10-25", 6.5), ("2026-10-26", 6.5), ("2026-10-27", 6.5)]
    under = [("2026-10-25", 6.4), ("2026-10-26", 6.4), ("2026-10-27", 6.4)]
    assert "S1" not in _ids(_check(history=at))
    assert "S1" in _ids(_check(history=under), "AMBER")


def test_l1_l2_optional():
    assert not _ids(_check()) & {"L1", "L2"}
    report = _check(_payload(lift_stalled=True, lift_sessions_done=2))
    assert {"L1", "L2"} <= _ids(report, "INFO")


def test_d1_when_next_week_is_deload():
    assert "D1" in _ids(_check(cycle_start="2026-09-28"), "INFO")
    assert "D1" not in _ids(_check(cycle_start="2026-10-26"))


def test_severity_order_in_banner():
    sleep = [("2026-10-25", 6.0), ("2026-10-26", 6.0), ("2026-10-27", 6.0)]
    report = _check(_payload(weights=(120,) * 7, protein=(100,) * 7, steps=(5000,) * 7),
                    history=sleep, protein_low_g=105)
    assert report["banner"] == ("Weekly: weight 120.0 (new), protein 100 g red, steps 5.0k, "
                                "1 red (protein low), 1 amber (sleep), 1 info (steps).")
    assert report["highest"] == "RED"


def test_bc_phase_never_changes():
    for phase in ("BC-1", "BC-2"):
        assert _check(bc_phase=phase)["bc_phase"] == phase
