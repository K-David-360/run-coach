# tests/test_bodycomp_store.py — synthetic data only
import json
import subprocess
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from bodycomp.config import DEFAULTS, load_config
from bodycomp.store import latest_report, load_weeks, save_week

REPO = os.path.join(os.path.dirname(__file__), "..")


def test_bodycomp_dir_is_gitignored():
    result = subprocess.run(["git", "check-ignore", "-q", "data/bodycomp/weekly.json"], cwd=REPO)
    assert result.returncode == 0


def test_load_config_defaults_when_missing(tmp_path):
    assert load_config(str(tmp_path / "config.json")) == DEFAULTS


def test_load_config_defaults_when_empty_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("")
    assert load_config(str(path)) == DEFAULTS


def test_load_config_overlays_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bc_phase": "BC-2", "protein_low_g": 100}))
    config = load_config(str(path))
    assert config["bc_phase"] == "BC-2"
    assert config["protein_low_g"] == 100
    assert {k: v for k, v in config.items() if k not in ("bc_phase", "protein_low_g")} == {
        k: v for k, v in DEFAULTS.items() if k not in ("bc_phase", "protein_low_g")
    }


def test_load_config_rejects_bad_phase(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bc_phase": "2"}))
    with pytest.raises(ValueError):
        load_config(str(path))


def test_save_week_replaces_same_week(tmp_path):
    path = str(tmp_path / "weekly.json")
    save_week({"week_ending": "2026-10-31", "v": 1}, path)
    save_week({"week_ending": "2026-10-31", "v": 2}, path)
    assert load_weeks(path) == [{"week_ending": "2026-10-31", "v": 2}]


def test_save_week_keeps_sorted(tmp_path):
    path = str(tmp_path / "weekly.json")
    save_week({"week_ending": "2026-11-07"}, path)
    save_week({"week_ending": "2026-10-31"}, path)
    assert [w["week_ending"] for w in load_weeks(path)] == ["2026-10-31", "2026-11-07"]


def test_latest_report_none_when_empty(tmp_path):
    assert latest_report(str(tmp_path / "weekly.json")) is None
