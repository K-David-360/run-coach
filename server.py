"""
server.py — Personal Running Coach: Flask API server.

─────────────────────────────────────────────────────────────────────────────
QUICK-START CURL EXAMPLES
─────────────────────────────────────────────────────────────────────────────

pip install:
    pip3 install flask

Start server:
    cd ~/run-coach && python3 server.py

──────────────────────
GET /test  (smoke test)
──────────────────────
curl http://localhost:5000/test

──────────────────────
GET /session  (last generated session)
──────────────────────
curl http://localhost:5000/session

──────────────────────
POST /run  (simulate a real HealthKit payload)
──────────────────────
curl -X POST http://localhost:5000/run \
  -H "Content-Type: application/json" \
  -d '{
    "recovery": {
      "hrv_last_night": 58.0,
      "hrv_7d_avg": 52.0
    },
    "sleep": {
      "deep_hrs": 1.8,
      "total_hrs": 7.5
    },
    "load": {
      "classification": "steady"
    },
    "effort_score": 6
  }'
"""

import base64
import json
import os
from datetime import date, timedelta

import requests as http_requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, make_response

from calendar_generator import generate_ics
from plan_generator import generate_session, generate_strength_session, kb_peak_from_weeks
from rule_engine import rule_engine

load_dotenv()

# ── GitHub calendar config ────────────────────────────────────────────────────

GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO     = "K-David-360/run-coach"
CALENDAR_FILE   = "calendar-rc7f4a2b.ics"
GITHUB_API_BASE = "https://api.github.com"

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
PLAN_STATE_FILE = os.path.join(DATA_DIR, "plan_state.json")
CURRENT_SESSION_FILE = os.path.join(DATA_DIR, "current_session.json")

_NOTIFICATIONS = {
    "SUPPRESS": "⛔️ Rest day — your body needs recovery. Skip training today.",
    "DELOAD":   "⛔️ Deload week — reduced load across all sessions. Keep it easy.",
    "REDUCE":   "⬇️ Pull back today — do a shorter, easier version of your session.",
    "HOLD":     "✅ On track — follow today's plan as scheduled.",
    "BUILD":    "⬆️ Good recovery — you can push a little harder today.",
}

_DEFAULT_PLAN_STATE = {
    "current_week": 1,
    "run_in_week": 0,
    "consecutive_suppress": 0,
    "total_runs": 0,
    "phase": 1,
    "last_session_date": "",
    "last_session_type": "",
    "last_session_decision": "",
    "kb_weeks_elapsed": 0,
    "kb_peak_rung": 10,
}

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)


# ── File helpers ──────────────────────────────────────────────────────────────

def _safe_float(value, default=0.0):
    """Convert value to float, returning default for None, '', or unconvertible values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _most_recent_monday(today: date = None) -> date:
    if today is None:
        today = date.today()
    # weekday(): Mon=0, Tue=1, ..., Sun=6
    # For Mon (0): subtract 0 days → same day
    # For Wed (2): subtract 2 days → previous Monday
    # For Sun (6): subtract 6 days → previous Monday
    return today - timedelta(days=today.weekday())


def _week_from_cycle_start(cycle_start_str: str, today: date = None) -> int:
    """Return training week (1–4) given the ISO date of the cycle's first Monday."""
    if today is None:
        today = date.today()
    try:
        start = date.fromisoformat(cycle_start_str)
    except (ValueError, TypeError):
        return 1
    if today < start:
        return 1
    weeks_elapsed = (today - start).days // 7
    return weeks_elapsed % 4 + 1


def _load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_data_files():
    """Create data/ directory and seed files if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        _save_json(HISTORY_FILE, [])

    if not os.path.exists(PLAN_STATE_FILE):
        _save_json(PLAN_STATE_FILE, _DEFAULT_PLAN_STATE)


# ── Calendar helpers ──────────────────────────────────────────────────────────

def _push_calendar_to_github(plan_state: dict):
    """Generate ICS from current plan state and push to GitHub Pages repo."""
    if not GITHUB_TOKEN:
        return

    ics_content = generate_ics(plan_state)
    encoded = base64.b64encode(ics_content.encode()).decode()

    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/contents/{CALENDAR_FILE}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }

    # Fetch current SHA so GitHub accepts the update (required for existing files)
    sha = None
    get_resp = http_requests.get(url, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")

    payload = {
        "message": "Update run coach calendar",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha

    http_requests.put(url, headers=headers, json=payload)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/run", methods=["POST"])
def post_run():
    """
    Receive a HealthKit JSON payload, run the rule engine, generate a session,
    persist everything, and return the session JSON.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid or missing JSON body."}), 400

    # 1. Extract HRV values
    recovery = data.get("recovery", {})
    hrv_last_night = float(recovery.get("hrv_last_night", 0))
    hrv_7d_avg = float(recovery.get("hrv_7d_avg", 1) or 1)  # guard /0

    # 2. Compute HRV ratio
    hrv_ratio = hrv_last_night / hrv_7d_avg

    # 3. Rule engine → decision
    decision = rule_engine(data, hrv_ratio)

    # 4. Generate session
    session = generate_session(decision["decision"], data)

    # 5. Append to history
    history = _load_json(HISTORY_FILE, default=[])
    history.append({
        "run_data": data,
        "decision": decision,
        "session": session,
    })
    _save_json(HISTORY_FILE, history)

    # 6. Write current session
    _save_json(CURRENT_SESSION_FILE, session)

    # 7. Update plan_state
    plan_state = _load_json(PLAN_STATE_FILE, default=dict(_DEFAULT_PLAN_STATE))

    plan_state["total_runs"] = plan_state.get("total_runs", 0) + 1

    # Track consecutive suppresses
    if decision["decision"] == "SUPPRESS":
        plan_state["consecutive_suppress"] = plan_state.get("consecutive_suppress", 0) + 1
    else:
        plan_state["consecutive_suppress"] = 0

    # Advance run count within week; roll week after 2 runs
    run_in_week = plan_state.get("run_in_week", 0) + 1
    if run_in_week >= 2:
        run_in_week = 0
        current_week = plan_state.get("current_week", 1)
        plan_state["current_week"] = 1 if current_week >= 4 else current_week + 1

    plan_state["run_in_week"] = run_in_week
    _save_json(PLAN_STATE_FILE, plan_state)

    return jsonify(session), 200


@app.route("/session", methods=["GET"])
def get_session():
    """Return the most recently generated session."""
    if not os.path.exists(CURRENT_SESSION_FILE):
        return jsonify({"error": "No session found. POST to /run first."}), 404
    return jsonify(_load_json(CURRENT_SESSION_FILE)), 200


@app.route("/test", methods=["GET"])
def get_test():
    """Return a static dummy session to verify the server is alive."""
    dummy = {
        "session_id": "test-0000-0000-0000-000000000000",
        "date": "2026-05-08",
        "type": "easy",
        "rule_fired": "HOLD",
        "flag": "none",
        "week": 1,
        "slot": "A",
        "summary": (
            "Easy run — 28 min total. "
            "Follow the plan — steady zone 2 effort. (This is a test response.)"
        ),
        "blocks": [
            {
                "name": "Warmup",
                "duration_min": 5,
                "zone": "zone1",
                "notes": "Easy walk or very light jog — just get the blood moving.",
            },
            {
                "name": "Work",
                "duration_min": 18,
                "zone": "zone2",
                "notes": "Conversational pace. You should be able to speak in full sentences.",
            },
            {
                "name": "Cooldown",
                "duration_min": 5,
                "zone": "zone1",
                "notes": "Slow to a walk, let heart rate drop naturally.",
            },
        ],
    }
    return jsonify(dummy), 200


@app.route("/calendar.ics", methods=["GET"])
def get_calendar():
    """Return the current rolling 4-week training calendar as an ICS file."""
    plan_state = _load_json(PLAN_STATE_FILE, default=dict(_DEFAULT_PLAN_STATE))
    ics = generate_ics(plan_state)
    resp = make_response(ics)
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{CALENDAR_FILE}"'
    return resp


@app.route("/calendar/push", methods=["POST"])
def post_calendar_push():
    """Regenerate ICS from current plan state and push to GitHub. No health data needed."""
    plan_state = _load_json(PLAN_STATE_FILE, default=dict(_DEFAULT_PLAN_STATE))
    _push_calendar_to_github(plan_state)
    return jsonify({"status": "ok", "message": "Calendar pushed to GitHub."}), 200


@app.route("/note", methods=["POST"])
def post_note():
    """Stub — note-taking endpoint, not yet implemented."""
    return jsonify({"status": "not_implemented", "message": "POST /note is a future feature."}), 501


# ── HealthKit flat-payload endpoint ───────────────────────────────────────────

def _classify_load(energy_7d: float, energy_28d: float) -> str:
    """
    Classify training load from raw active-energy totals.

    Computes daily averages for the 7-day and 28-day windows, then returns a
    load label based on how the recent week compares to the longer baseline.

    Args:
        energy_7d:  Total active calories (kcal) burned in the last 7 days.
        energy_28d: Total active calories (kcal) burned in the last 28 days.

    Returns:
        One of: "well_below" | "below" | "steady" | "above" | "well_above"
    """
    if energy_28d <= 0 or energy_7d <= 0:
        return "steady"  # no data yet — default safe

    daily_7d  = energy_7d  / 7
    daily_28d = energy_28d / 28
    ratio     = daily_7d / daily_28d

    if ratio < 0.60:
        return "well_below"
    elif ratio < 0.85:
        return "below"
    elif ratio <= 1.15:
        return "steady"
    elif ratio <= 1.40:
        return "above"
    else:
        return "well_above"


def _classify_load_pct(pct: float) -> str:
    """Map Apple's training load percentage to an internal load label."""
    if pct > 50:
        return "well_above"
    elif pct > 20:
        return "above"
    elif pct >= -20:
        return "steady"
    elif pct >= -50:
        return "below"
    else:
        return "well_below"


@app.route("/healthkit", methods=["POST"])
def post_healthkit():
    """
    Accept a flat HealthKit payload from an iOS Shortcut.

    Deduplication: the Shortcut sends `last_workout_date` (ISO 8601 string,
    e.g. "2026-05-08T07:30:00"). The server compares this against
    `last_processed_workout_date` stored in plan_state.json.

    - New workout date → full pipeline: log to history, advance plan counters.
    - Same date (rest day) → rule engine still runs with fresh data so load
      and recovery are current, but nothing is logged and plan state is
      unchanged. `debug.rest_day` will be true in the response.

    Expected JSON body:
    {
        "last_workout_date": str,   # ISO 8601 start date of last workout
        "hrv_last_night":   float,  # ms SDNN from last night's sleep
        "hrv_7d_samples":   [float],# list of nightly HRV readings, last 7 days
        "sleep_deep_hrs":   float,  # hours of deep (slow-wave) sleep last night
        "sleep_total_hrs":  float,  # total hours asleep last night
        "active_energy_7d":  float, # kcal active energy burned, last 7 days
        "active_energy_28d": float, # kcal active energy burned, last 28 days
        "effort_score":     float   # perceived exertion 1–10 from last workout
    }
    """
    body = request.get_json(force=True, silent=True)
    if not body:
        return jsonify({"error": "Invalid or missing JSON body."}), 400

    # ── Day-of-week routing ───────────────────────────────────────────────────
    _REST_DAYS     = {3, 6}                          # Thursday=3, Sunday=6
    _STRENGTH_DAYS = {0: "mon", 2: "wed", 4: "fri"}

    today_dow = date.today().weekday()
    today_str = date.today().isoformat()

    plan_state = _load_json(PLAN_STATE_FILE, default=dict(_DEFAULT_PLAN_STATE))

    # ── Calendar-week anchoring: set cycle_start_date if absent (first deploy) ──
    if not plan_state.get("cycle_start_date"):
        plan_state["cycle_start_date"] = _most_recent_monday().isoformat()

    # Recompute current_week from calendar date — this is now the source of truth.
    plan_state["current_week"] = _week_from_cycle_start(plan_state["cycle_start_date"])
    _save_json(PLAN_STATE_FILE, plan_state)

    # Rest days: skip health processing entirely
    if today_dow in _REST_DAYS:
        rest_session = {
            "session_id": f"rest-{today_str}",
            "date": today_str,
            "type": "rest",
            "rule_fired": "REST",
            "summary": "Rest Day — No Session",
            "blocks": [],
        }
        _save_json(CURRENT_SESSION_FILE, rest_session)
        return jsonify({**rest_session, "notification": "🛌 Rest day — no training today.", "decision_reason": "Rest day"}), 200

    # ── Deduplication check (run days only) ───────────────────────────────────
    last_workout_date = body.get("last_workout_date", "")
    last_processed = plan_state.get("last_processed_workout_date", "")
    is_rest_day = bool(last_workout_date and last_workout_date == last_processed)

    # ── Extract flat fields ───────────────────────────────────────────────────
    hrv_last_night  = _safe_float(body.get("hrv_last_night"),  0.0)
    hrv_7d_samples  = [_safe_float(x) for x in body.get("hrv_7d_samples", [])]  # legacy, ignored if empty
    sleep_deep_hrs  = _safe_float(body.get("sleep_deep_hrs"),  0.0)
    sleep_total_hrs = _safe_float(body.get("sleep_total_hrs"), 0.0)
    resting_hr      = _safe_float(body.get("resting_hr"),      0.0)

    # ── Compute derived values ────────────────────────────────────────────────
    # Use last 7 hrv_last_night values from history as baseline (clean nightly readings)
    history = _load_json(HISTORY_FILE, default=[])
    past_hrv = [
        e["run_data"]["recovery"]["hrv_last_night"]
        for e in history[-7:]
        if e.get("run_data", {}).get("recovery", {}).get("hrv_last_night")
    ]
    if past_hrv:
        hrv_7d_avg = sum(past_hrv) / len(past_hrv)
    elif hrv_7d_samples:
        hrv_7d_avg = sum(hrv_7d_samples) / len(hrv_7d_samples)
    else:
        hrv_7d_avg = hrv_last_night or 1  # no history yet — treat tonight as baseline

    hrv_ratio = hrv_last_night / (hrv_7d_avg or 1)

    # ── Load classification: accept % directly, or fall back to label/energy ────
    _VALID_LOAD = {"well_below", "below", "steady", "above", "well_above"}
    load_classification = body.get("load_classification", "")

    if "load_pct" in body:
        load_classification = _classify_load_pct(_safe_float(body.get("load_pct"), 0.0))
    elif load_classification not in _VALID_LOAD:
        active_energy_7d  = _safe_float(body.get("active_energy_7d"),  0.0)
        active_energy_28d = _safe_float(body.get("active_energy_28d"), 0.0)
        load_classification = _classify_load(active_energy_7d, active_energy_28d)

    # ── Normalise into the standard internal format ───────────────────────────
    data = {
        "recovery": {
            "hrv_last_night": hrv_last_night,
            "hrv_7d_avg":     hrv_7d_avg,
            "resting_hr":     resting_hr,
        },
        "sleep": {
            "deep_hrs":  sleep_deep_hrs,
            "total_hrs": sleep_total_hrs,
        },
        "load": {
            "classification": load_classification,
        },
        "last_workout_date": last_workout_date,
        "source":            "healthkit",
    }

    # ── Rule engine ───────────────────────────────────────────────────────────
    decision = rule_engine(data, hrv_ratio)

    # ── Strength days (Mon / Wed / Fri) ───────────────────────────────────────
    if today_dow in _STRENGTH_DAYS:
        day_key   = _STRENGTH_DAYS[today_dow]
        bell_reset = False

        if day_key == "wed" and decision["decision"] in ("BUILD", "HOLD"):
            if plan_state.get("last_session_date", "") != today_str:
                new_kb_weeks = plan_state.get("kb_weeks_elapsed", 0) + 1
                if new_kb_weeks >= 9:
                    new_kb_weeks = 0
                    bell_reset   = True
                plan_state["kb_weeks_elapsed"] = new_kb_weeks
                plan_state["kb_peak_rung"]     = kb_peak_from_weeks(new_kb_weeks)

        session = generate_strength_session(decision["decision"], day_key, bell_reset=bell_reset)
        _save_json(CURRENT_SESSION_FILE, session)
        plan_state["last_session_date"]     = today_str
        plan_state["last_session_type"]     = session["type"]
        plan_state["last_session_decision"] = decision["decision"]
        _save_json(PLAN_STATE_FILE, plan_state)
        _push_calendar_to_github(plan_state)
        return jsonify({
            **session,
            "notification": _NOTIFICATIONS.get(decision["decision"], "✅ On track — follow today's plan as scheduled."),
            "decision_reason": decision["reason"],
            "debug": {
                "rest_day":            False,
                "hrv_ratio":           round(hrv_ratio, 3),
                "hrv_7d_avg":          round(hrv_7d_avg, 1),
                "resting_hr":          resting_hr,
                "load_classification": load_classification,
                "decision":            decision["decision"],
            },
        }), 200

    # ── Run days (Tue / Sat) ──────────────────────────────────────────────────
    session = generate_session(decision["decision"], data)
    _save_json(CURRENT_SESSION_FILE, session)

    if is_rest_day:
        # Rest day: fresh recommendation based on today's recovery and load,
        # but don't log to history or advance any plan counters.
        plan_state["last_session_date"] = date.today().isoformat()
        plan_state["last_session_type"] = session["type"]
        plan_state["last_session_decision"] = decision["decision"]
        _save_json(PLAN_STATE_FILE, plan_state)
        _push_calendar_to_github(plan_state)
        return jsonify({
            **session,
            "notification": _NOTIFICATIONS.get(decision["decision"], "✅ On track — follow today's plan as scheduled."),
            "decision_reason": decision["reason"],
            "debug": {
                "rest_day":            True,
                "hrv_ratio":           round(hrv_ratio, 3),
                "hrv_7d_avg":          round(hrv_7d_avg, 1),
                "resting_hr":          resting_hr,
                "load_classification": load_classification,
                "decision":            decision["decision"],
                "last_workout_date":   last_workout_date,
            },
        }), 200

    # ── New workout — log to history and advance plan state ───────────────────
    history.append({"run_data": data, "decision": decision, "session": session})
    _save_json(HISTORY_FILE, history)

    plan_state["total_runs"] = plan_state.get("total_runs", 0) + 1
    plan_state["last_processed_workout_date"] = last_workout_date
    plan_state["last_session_date"] = date.today().isoformat()
    plan_state["last_session_type"] = session["type"]
    plan_state["last_session_decision"] = decision["decision"]

    if decision["decision"] == "SUPPRESS":
        plan_state["consecutive_suppress"] = plan_state.get("consecutive_suppress", 0) + 1
    else:
        plan_state["consecutive_suppress"] = 0

    run_in_week = plan_state.get("run_in_week", 0) + 1
    if run_in_week >= 2:
        run_in_week  = 0
        current_week = plan_state.get("current_week", 1)
        plan_state["current_week"] = 1 if current_week >= 4 else current_week + 1
    plan_state["run_in_week"] = run_in_week
    _save_json(PLAN_STATE_FILE, plan_state)

    _push_calendar_to_github(plan_state)

    return jsonify({
        **session,
        "notification": _NOTIFICATIONS.get(decision["decision"], "✅ On track — follow today's plan as scheduled."),
        "decision_reason": decision["reason"],
        "debug": {
            "rest_day":            False,
            "hrv_ratio":           round(hrv_ratio, 3),
            "hrv_7d_avg":          round(hrv_7d_avg, 1),
            "resting_hr":          resting_hr,
            "load_classification": load_classification,
            "decision":            decision["decision"],
            "last_workout_date":   last_workout_date,
        },
    }), 200


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _ensure_data_files()
    port = int(os.environ.get("PORT", 5001))
    print(f"Run Coach server starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
