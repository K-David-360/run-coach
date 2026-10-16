"""
bodycomp/config.py — Weekly-check thresholds.

Code defaults are generic. Personal values (absolute protein/calorie targets,
baseline weight) live only in the gitignored data/bodycomp/config.json.
A missing personal threshold (None) makes its rule report "not configured".
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODYCOMP_DIR = os.path.join(BASE_DIR, "data", "bodycomp")
CONFIG_FILE = os.path.join(BODYCOMP_DIR, "config.json")

DEFAULTS = {
    "bc_phase": "BC-1",            # "BC-1" maintenance build / "BC-2" deficit; never advanced by code
    "bc_phase_start_date": "",
    "baseline_weight_lb": None,    # personal; None → W1 reports "not configured"
    "w1_hold_band_lb": 1.0,
    "w1_max_bc_week": 12,
    "w2_fast_loss_lb": 1.0,
    "w2_weeks": 2,
    "w3_early_rise_weeks": 2,
    "w3_loss_lb": 0.2,
    "w4_flat_lb": 0.2,
    "w4_weeks": 3,
    "protein_avg_min_g": None,
    "protein_low_g": None,
    "protein_min_g_per_kg": 1.6,
    "kcal_floor_bc1": None,
    "kcal_floor_bc2": None,
    "sleep_short_hrs": 6.5,
    "sleep_short_nights": 3,
    "steps_min_avg": 6000,
    "lift_sessions_min": 3,
    "min_weight_days": 4,
    "min_nutrition_days": 5,
    "telegram_detail": "trends",   # "flags" | "trends" | "full" (not built; falls back to trends)
}

_PHASES = {"BC-1", "BC-2"}


def load_config(path: str = CONFIG_FILE) -> dict:
    config = dict(DEFAULTS)
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    if text.strip():
        config.update(json.loads(text))
    if config["bc_phase"] not in _PHASES:
        raise ValueError("bc_phase must be BC-1 or BC-2")
    return config
