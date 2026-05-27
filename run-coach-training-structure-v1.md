# Run Coach App — Training Structure Knowledge Base (v1)
*Last updated: May 10, 2026*
*Source: Runna Training Hub research + HealthKit data analysis*

---

## Athlete Baseline (as of May 7, 2026)

| Metric | Value |
|--------|-------|
| 5K time (extrapolated) | ~39:04 |
| Current pace | 12:35/mile (7:49/km) |
| Target pace | 10:00/mile (31:03 5K) |
| Gap | ~8 min / ~20% pace improvement |
| Max HR (recorded) | 177 bpm |
| Resting HR (avg) | ~58 bpm |
| LTHR (estimated) | ~162 bpm |
| Training frequency | 2 runs/week + 2–3 strength sessions |
| Goal | Hybrid athlete — muscle gain, fat loss, 5K improvement |

---

## Heart Rate Zones (Lactate Threshold-Based)

Estimated LTHR = 162 bpm (based on May 7 5K effort). To be refined with a proper field test at week 6–8 (30-min all-out effort; average HR of final 20 min = LTHR).

| Zone | BPM Range | Feel |
|------|-----------|------|
| 1 | <115 | Walking, fully conversational |
| 2 | 115–145 | Slow jog, full sentences — **primary training zone** |
| 3 | 145–155 | Comfortably hard, short sentences |
| 4 | 155–165 | Very hard, 1–2 words only |
| 5 | 165–177 | All out, unsustainable |

**Apple custom zone breakpoints:** 115 / 145 / 155 / 165

**Easy run target:** 125–140 bpm (middle of Zone 2)

**Current reality:** At 12:35/mile pace, athlete hits Zone 4–5. Zone 2 running currently requires ~13–15 min/mile pace, with walk intervals as needed to stay sub-145 bpm. This is expected and correct at this fitness level.

**Progress signal:** When 12:35/mile begins feeling like Zone 2–3 instead of Zone 4–5, the aerobic base is developing. That is the green light to introduce intensity.

---

## Weekly Schedule Structure

Hybrid athlete template: 2 runs + 2–3 strength sessions per week.

| Day | Session | Notes |
|-----|---------|-------|
| Monday | Strength A — Lower Body | Squats, deadlifts, lunges, glutes |
| Tuesday | Easy Run (Zone 2) | 30–40 min, HR 125–140 target |
| Wednesday | Strength B — Upper Body + Core | No leg fatigue before Thursday rest |
| Thursday | Rest or mobility | |
| Friday | Strength C — Full Body | Optional; skip if only doing 2x strength |
| Saturday | Run 2 (Zone 2, longer) | 35–45 min, same HR target |
| Sunday | Full rest | |

---

## Hard Scheduling Rules (Non-Negotiable)

1. **Never schedule heavy lower body strength the day before a quality run.** Flag as conflict and propose resolution before finalizing the week.
2. **Upper body sessions can go anywhere** — minimal interference with running legs.
3. **Deload every 3–4 build weeks** regardless of ACWR. ACWR can trigger an earlier deload but cannot delay a scheduled one.
4. **Never ramp running and strength simultaneously.** Running volume increases first. Strength only increases after 3+ weeks at the same level with consistently good sleep.

---

## Training Intensity Distribution

Standard 80:20 rule does not apply cleanly at 2 runs/week. Adjusted framework:

- **Phase 1 (base building):** Both runs Zone 2 only. No intensity. Closer to 100:0.
- **Phase 2 onward:** One easy run (Zone 2), one quality run. Closer to 60:40.

At 2 runs/week with any intensity session, recovery between sessions matters more than ratio orthodoxy.

---

## Phased Path to 10:00/mile

### Phase 1 — Base Building (Weeks 1–6)
- Both runs Zone 2 only
- HR is the target metric, not pace
- Walk intervals are expected and correct
- Pace will feel embarrassingly slow (~13–15 min/mile) — that is the right output
- No speed work, no tempo

### Phase 2 — Introduce Quality (Weeks 7–12)
- Run 1: stays Zone 2 easy
- Run 2: progression run — easy start, 5–10 min at Zone 3 (145–155 bpm) toward the end
- Still no formal intervals

### Phase 3 — Speed Work (Weeks 13–20)
- Run 1: stays Zone 2 easy
- Run 2: short intervals — 400m–800m repeats at target 10:00/mile pace (6:13/km)
- Extend interval volume week over week following 10% load cap

**Estimated timeline to 10:00/mile:** 4–6 months of consistent execution. Phase 1 is the bottleneck — do not compress it.

---

## Session Types Reference

| Session Type | Description | HR Target | When Used |
|-------------|-------------|-----------|-----------|
| Walk-Run | Alternating run/walk intervals | Stay sub-145 | Phase 1 if needed |
| Easy Run | Continuous slow jog | 125–140 bpm | All phases |
| Progression Run | Easy start, Zone 3 finish | 125–155 bpm | Phase 2+ |
| Tempo | Sustained Zone 3 effort, no rest | 145–155 bpm | Phase 3 |
| Intervals | Short hard repeats with walk rest | 155–177 bpm | Phase 3 |
| Long Run | Easy pace, extended duration | 125–140 bpm | Future (3+ runs/week) |

---

## Training Load Logic

### Data Inputs (all auto-pulled from HealthKit, zero friction)

| Input | Source | Notes |
|-------|--------|-------|
| Apple Training Load | HealthKit (`HKQuantityTypeIdentifierTrainingLoad`) | Hybrid HR + RPE, covers all logged workouts |
| Sleep duration | HealthKit sleep | 7-day rolling average |
| HRV | HealthKit HRV | Trend vs personal baseline |
| Resting HR | HealthKit resting HR | Trend vs personal baseline |

**Note:** HRV and resting HR baselines require ~4 weeks of data before their modifiers activate. Treat as dormant until then.

### Strength Session Load Weighting

| Session Type | Load Weight | Rationale |
|-------------|-------------|-----------|
| Lower body / full body | 1.0× | High interference with running recovery |
| Upper body | 0.3× | Minimal leg fatigue |
| Mobility / stretching | 0× | No meaningful training stress |

Apple Training Load handles running load natively. Strength weighting is applied on top when computing ACWR if strength sessions are underrepresented in Apple's output.

### ACWR Calculation

```
acute_load   = sum of Apple Training Load over last 7 days
chronic_load = rolling average of weekly load over last 28 days
ACWR         = acute_load / chronic_load
```

**Safe zone:** 0.8–1.3
**Danger zone:** >1.5

### Primary Decision Table

| ACWR | Base Decision |
|------|--------------|
| >1.5 | DELOAD — overrides all modifiers |
| 1.3–1.5 | REDUCE |
| 1.0–1.3 | BUILD |
| 0.8–1.0 | HOLD |
| <0.8 | BUILD (undertraining) |

### Recovery Modifiers

Modifiers can only make the recommendation **more conservative**, never more aggressive. Most conservative signal wins — modifiers do not stack additively.

| Input | Condition | Effect |
|-------|-----------|--------|
| Sleep | 7.5h+ avg | No change |
| Sleep | 6–7.5h avg | Cap at HOLD |
| Sleep | <6h avg | Shift one level more conservative |
| Sleep | 2+ nights <5h | Force DELOAD regardless of ACWR |
| HRV | >10% below personal baseline | Cap at HOLD |
| Resting HR | 5+ bpm above baseline for 2+ days | Cap at HOLD |

### Four Possible Outputs

**DELOAD**
- Running: cut volume ~30%, all runs Zone 2 easy, no quality sessions
- Strength: one short full-body session max, remove all lower body work

**REDUCE**
- Running: cut one session or drop intensity to easy on all runs
- Strength: swap lower body sessions to upper body only

**HOLD**
- Running: repeat last week's structure exactly
- Strength: no changes

**BUILD**
- Running: add ~10% volume OR introduce/increase one quality session (not both)
- Strength: only increases if held steady 3+ weeks AND sleep consistently 7.5h+

### Coach Output Format

Every weekly recommendation must include:
1. The decision (Deload / Reduce / Hold / Build)
2. Plain language reason citing which signals drove it
3. Full week structure with each day labeled
4. Any scheduling conflicts flagged and resolved

**Example:**
> "Your training load spiked relative to your 28-day baseline (ACWR 1.4) and sleep averaged 5.9 hours this week. Recommendation: **Reduce**. Both runs stay Zone 2 easy, no intensity. Strength shifts to upper body only on Wednesday — no lower body until next week."

---

## Key Coaching Principles (Encode in System Prompt)

1. Zone 2 ceiling is 145 bpm. If HR exceeds this, slow down or walk — no exceptions.
2. HR is the target metric during Phase 1, not pace. Pace is an output, not an input.
3. Walk intervals are not failure. They are the correct tool for staying in Zone 2 at current fitness.
4. The 10% weekly load cap applies to running volume. Never exceed it.
5. Deload weeks are not optional. Athletes often feel fine and want to skip them — do not allow it.
6. Never increase both running volume and strength load in the same week.
7. The aerobic base phase (Phase 1) must not be compressed. Rushing to intervals before the base exists produces slower long-term results and higher injury risk.
8. A DELOAD recommendation overrides athlete preference. Always explain why.

---

## Open Items (Future Refinement)

- [ ] LTHR field test at week 6–8 to replace estimated zones with measured ones
- [ ] Establish personal HRV and resting HR baselines (4+ weeks data needed)
- [ ] Confirm Apple Training Load (`HKQuantityTypeIdentifierTrainingLoad`) is populating correctly in HealthKit
- [ ] Confirm strength sessions are being RPE-rated in Apple Health after workouts
- [ ] Consider adding manual "rough week" trigger via Telegram to shift recommendation one level more conservative (life stress signal Runna identifies but no app can auto-detect)
- [ ] Revisit zone boundaries after LTHR field test
- [ ] Evaluate adding 3rd run/week once Phase 1 base is established
