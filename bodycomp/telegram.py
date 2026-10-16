"""
bodycomp/telegram.py — Weekly-check message for a dedicated Telegram bot.

Telegram bot chats are cloud chats (readable by Telegram), so the message is
built from an allowlist of relative/aggregate fields only: never absolute body
weight, calories, baseline, height or config thresholds. `build_message` refuses
any other field, so a leak cannot happen by passing the wrong object.
"""

import logging
from datetime import date

import requests

from bodycomp.checks import RULE_LABELS, SEVERITY_ORDER

log = logging.getLogger(__name__)

ALLOWED_FIELDS = {"week_ending", "flags", "protein_status", "weight_delta_lb",
                  "protein_avg_g", "steps_avg", "sleep_avg_hrs"}


def allowed_fields(report: dict) -> dict:
    """Extract only the allowlisted fields from a stored report."""
    m = report["metrics"]
    fired = [(r["id"], r["severity"]) for r in report["results"] if r["severity"] != "OK"]
    status = next((sev.lower() for rid, sev in fired if rid in ("P2", "P1")), "OK")
    if m.get("protein_days", 0) < 1 or any(rid == "P" for rid, _ in fired):
        status = "n/a"
    return {
        "week_ending": report["week_ending"],
        "flags": [{"label": RULE_LABELS[rid], "severity": sev} for rid, sev in fired],
        "protein_status": status,
        "weight_delta_lb": m.get("delta_lb"),
        "protein_avg_g": m.get("avg_protein_g"),
        "steps_avg": m.get("avg_steps"),
        "sleep_avg_hrs": m.get("avg_sleep_hrs"),
    }


def _flag_groups(flags: list, with_counts: bool) -> str:
    groups = []
    for sev in SEVERITY_ORDER[:-1]:
        labels = [f["label"] for f in flags if f["severity"] == sev]
        if labels:
            prefix = f"{len(labels)} " if with_counts else ""
            groups.append(f"{prefix}{sev.lower()} ({', '.join(labels)})")
    return ", ".join(groups) if groups else "all OK"


def build_message(fields: dict, detail: str) -> str:
    extra = set(fields) - ALLOWED_FIELDS
    if extra:
        raise ValueError(f"fields not allowed in Telegram message: {sorted(extra)}")
    if detail == "full":
        log.warning("telegram_detail 'full' is not built; using 'trends'")
        detail = "trends"
    if detail == "flags":
        return f"Weekly check: {_flag_groups(fields['flags'], False)}, protein {fields['protein_status']}."

    week = date.fromisoformat(fields["week_ending"]).strftime("%b %-d")
    delta = fields["weight_delta_lb"]
    parts = [
        "weight change n/a" if delta is None else f"weight {delta:+.1f} lb",
        "protein n/a" if fields["protein_avg_g"] is None else f"protein {fields['protein_avg_g']:.0f} g avg",
        "steps n/a" if fields["steps_avg"] is None else f"steps {fields['steps_avg'] / 1000:.1f}k",
        "sleep n/a" if fields["sleep_avg_hrs"] is None else f"sleep {fields['sleep_avg_hrs']:.1f} h",
        _flag_groups(fields["flags"], True),
    ]
    return f"Weekly check (w/e {week}): " + ", ".join(parts) + "."


def send(text: str, token: str, chat_id: str, post=requests.post) -> bool:
    """Send to the single configured chat. Never raises; returns whether it was delivered."""
    if not token or not chat_id:
        return False
    try:
        resp = post(f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text}, timeout=10)
        return bool(resp.ok)
    except Exception:
        log.exception("Telegram send failed")
        return False
