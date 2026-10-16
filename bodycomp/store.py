"""
bodycomp/store.py — Read/write the gitignored body-comp data files.
"""

import json
import os

from bodycomp.config import BODYCOMP_DIR

WEEKLY_FILE = os.path.join(BODYCOMP_DIR, "weekly.json")
MEASUREMENTS_FILE = os.path.join(BODYCOMP_DIR, "measurements.json")
REPORTS_DIR = os.path.join(BODYCOMP_DIR, "reports")


def _load_list(path: str) -> list:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def _save_replacing(entry: dict, key: str, path: str) -> None:
    rows = [r for r in _load_list(path) if r.get(key) != entry.get(key)]
    rows.append(entry)
    rows.sort(key=lambda r: r.get(key, ""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)


def load_weeks(path: str = WEEKLY_FILE) -> list:
    return sorted(_load_list(path), key=lambda r: r.get("week_ending", ""))


def save_week(report: dict, path: str = WEEKLY_FILE) -> None:
    _save_replacing(report, "week_ending", path)


def save_report_file(report: dict, reports_dir: str = REPORTS_DIR) -> None:
    """Full per-rule report as reports/<week_ending>.json (overwritten on re-post)."""
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, f"{report['week_ending']}.json"), "w") as f:
        json.dump(report, f, indent=2)


def latest_report(path: str = WEEKLY_FILE):
    weeks = load_weeks(path)
    return weeks[-1] if weeks else None


def load_measurements(path: str = MEASUREMENTS_FILE) -> list:
    return sorted(_load_list(path), key=lambda r: r.get("date", ""))


def append_measurement(entry: dict, path: str = MEASUREMENTS_FILE) -> None:
    _save_replacing(entry, "date", path)
