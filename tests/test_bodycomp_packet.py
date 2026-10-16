# tests/test_bodycomp_packet.py — synthetic data only
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date, timedelta

from bodycomp.config import DEFAULTS
from bodycomp.review_packet import FOOTER, build_packet


def _report(week_ending, avg=180.0, results=()):
    return {"week_ending": week_ending, "bc_phase": "BC-1", "bc_week": 1,
            "metrics": {"avg_weight_lb": avg, "delta_lb": 0.1, "avg_protein_g": 150.0, "avg_kcal": 2100.0,
                        "avg_steps": 7100, "short_sleep_nights": 1},
            "results": list(results)}


def _weeks(n):
    start = date(2026, 10, 24)
    return [_report((start + timedelta(weeks=i)).isoformat()) for i in range(n)]


def _table_rows(packet):
    return [line for line in packet.splitlines() if line.startswith("| 20")]


def test_packet_limits_to_12_weeks():
    weeks = _weeks(15)
    rows = _table_rows(build_packet(weeks, [], dict(DEFAULTS), 2))
    assert len(rows) == 12
    assert rows[-1].startswith(f"| {weeks[-1]['week_ending']}")


def test_packet_tape_changes():
    tape = [{"date": "2026-10-01", "waist_in": 34.0}, {"date": "2026-11-01", "waist_in": 33.5}]
    packet = build_packet([], tape, dict(DEFAULTS), 2)
    assert any("waist_in" in line and "-0.5" in line for line in packet.splitlines())


def test_packet_lists_red_amber_only():
    results = [{"id": "P2", "severity": "RED", "message": "Protein low"},
               {"id": "S2", "severity": "INFO", "message": "Steps low"},
               {"id": "W1", "severity": "OK", "message": "Weight holding"}]
    packet = build_packet([_report("2026-10-31", results=results)], [], dict(DEFAULTS), 2)
    events = packet.split("RED/AMBER events", 1)[1]
    assert "Protein low" in events
    assert "Steps low" not in events and "Weight holding" not in events


def test_packet_footer_verbatim():
    assert build_packet(_weeks(2), [], dict(DEFAULTS), 2).endswith(FOOTER)


def test_packet_handles_no_data():
    packet = build_packet([], [], dict(DEFAULTS), 2)
    assert packet.startswith("# Body-comp review packet")
    assert packet.endswith(FOOTER)
