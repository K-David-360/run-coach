"""
bodycomp/review_packet.py — Compact markdown summary for an occasional Claude review.

Aggregates only (weekly averages, tape changes, flagged events), so a review is
cheap and raw daily logs never leave the Pi. David pastes it into a chat.
"""

from datetime import date

TAPE_SITES = ["neck_in", "shoulders_in", "chest_in", "waist_in", "arm_in", "thigh_in", "calf_in"]

FOOTER = (
    "---\n"
    "Please review: (1) interpret the weight, waist and tape trends; (2) should I hold "
    "BC-1/BC-2 or change phase; (3) any calorie change; (4) anything to bring to my doctor."
)

_THRESHOLD_KEYS = [
    "protein_avg_min_g", "protein_low_g", "protein_min_g_per_kg", "kcal_floor_bc1",
    "kcal_floor_bc2", "sleep_short_hrs", "steps_min_avg", "w1_hold_band_lb", "w2_fast_loss_lb",
]


def _fmt(value, spec=""):
    return "n/a" if value is None else format(value, spec)


def _signed(new, old):
    return "n/a" if new is None or old is None else f"{new - old:+.1f}"


def build_packet(weeks: list, measurements: list, config: dict, run_phase: int, today: date = None) -> str:
    if today is None:
        today = date.today()
    recent = weeks[-12:]
    latest_bc_week = recent[-1].get("bc_week") if recent else None
    span = f"{recent[0]['week_ending']} to {recent[-1]['week_ending']}" if recent else "no weekly data yet"
    thresholds = ", ".join(f"{k} {config[k]}" for k in _THRESHOLD_KEYS if config.get(k) is not None)

    lines = [
        "# Body-comp review packet",
        "",
        f"{config['bc_phase']}, BC week {_fmt(latest_bc_week)}, run phase {run_phase}, weeks {span} "
        f"(generated {today.isoformat()})",
        "",
        f"Thresholds: {thresholds}",
        "",
        "## Weekly",
        "",
        "| Week ending | Avg weight | Delta | Protein | kcal | Steps | Short-sleep nights | Flags |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for w in recent:
        m = w.get("metrics", {})
        flags = ", ".join(f"{r['id']} {r['severity']}" for r in w.get("results", []) if r["severity"] != "OK")
        lines.append(
            f"| {w['week_ending']} | {_fmt(m.get('avg_weight_lb'), '.1f')} | {_fmt(m.get('delta_lb'), '+.1f')} "
            f"| {_fmt(m.get('avg_protein_g'), '.0f')} | {_fmt(m.get('avg_kcal'), '.0f')} "
            f"| {_fmt(m.get('avg_steps'))} | {_fmt(m.get('short_sleep_nights'))} | {flags or '-'} |"
        )

    lines += ["", "## Tape", ""]
    if measurements:
        latest, first = measurements[-1], measurements[0]
        previous = measurements[-2] if len(measurements) > 1 else None
        lines.append(f"Latest {latest['date']} (vs previous / vs first):")
        for site in TAPE_SITES:
            if latest.get(site) is not None:
                prev = previous.get(site) if previous else None
                lines.append(f"- {site}: {latest[site]:.1f} ({_signed(latest[site], prev)} / "
                             f"{_signed(latest[site], first.get(site))})")
        if latest.get("shoulder_waist_ratio") is not None:
            lines.append(f"- shoulder_waist_ratio: {latest['shoulder_waist_ratio']:.2f}")
    else:
        lines.append("No tape measurements yet.")

    lines += ["", "## RED/AMBER events", ""]
    events = [f"- {w['week_ending']}: {r['id']} {r['severity']} — {r['message']}"
              for w in recent for r in w.get("results", []) if r["severity"] in ("RED", "AMBER")]
    lines += events or ["None."]
    lines += ["", FOOTER]
    return "\n".join(lines)
