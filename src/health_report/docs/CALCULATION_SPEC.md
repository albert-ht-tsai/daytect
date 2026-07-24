# Health Report Calculation Spec

Backend-owned calculation reference for `POST/GET /health-reports`. This document formalizes
the formulas implemented in `report_stats_service.py` (pure functions, no DB/AI) and
`health_report_service.py` (orchestration). It is adapted from a broader product spec
("Luma Health 後端報告計算規格") to this codebase's actual data model and endpoints — see
**§0 Scope & deviations** before reading any formula below.

Responsibility boundary: the backend is the single source of truth for every number, status,
and comparison in the report. The frontend only renders `health_metrics`/`sleep_summary`/
`activity_summary`/`weekly_changes`/`priority_items` as given — it must not recompute scores,
comparisons, or statuses itself.

## 0. Scope & deviations from the source spec

- **Timezone: dropped, deprecated.** The source spec's per-user IANA-timezone report window is
  explicitly deprecated (per product decision) and is not implemented. This backend uses one
  fixed `REPORT_TZ = UTC+8` for all users (`report_stats_service.REPORT_TZ`), matching the
  convention already used elsewhere in this codebase (see
  `assistant/services/question_summary_service.py`'s `REPORT_TZ`). There is no per-request or
  per-user timezone parameter.
- **Data model: one pre-averaged value per metric per day.** Device uploads
  (`HealthAvgRecordPayload` / `SleepSummaryPayload` / `ActivityAvgRecordPayload`) contain a
  single already-averaged value per metric per day, not raw per-sample readings. Several
  formulas in the source spec assume raw samples (resting-HR isolation from low-activity
  windows, per-day RMSSD-then-median HRV, SpO2 sub-90% *duration*, ECG per-reading
  classification counts, a device cumulative step-counter with reset detection, a per-user step
  goal, per-minute activity intensity). Every such row below is marked **Simplified** (closest
  available approximation, using existing daily fields) or **Not implemented** (no data exists
  to support even an approximation) — never silently fabricated.
- **API naming: unchanged.** The source spec's example contract (`POST /v1/reports`, `job_id`,
  a 6-stage `QUEUED/AGGREGATING/COMPARING/SCORING/AI_ANALYZING/COMPLETED` lifecycle) is not
  adopted verbatim. This backend keeps its existing `/health-reports` paths, `report_id`, and
  3-stage (`collecting_data`/`ai_analysis`/`completed`) lifecycle — see `API_SPEC.md` for how
  the source spec's 6 conceptual stages map onto these 3.
- **Score weights: adopted from the source spec.** sleep 30% / health 40% / activity 20%,
  reserving 10% for a frontend-appended medication component that this backend never computes
  (see §3.1).

## 1. Report period & common rules

- Report period ("本週"): the fixed 7-day window ending on `date` (inclusive) if the caller
  passes an anchor date, otherwise ending "yesterday" in `REPORT_TZ`. See
  `report_stats_service.compute_period`.
- Comparison period ("前週"): the preceding 7-day window, immediately before the report period.
- **Common formulas** (`report_stats_service._change`):
  - `absolute_change = current_value − previous_value`
  - `change_percent = absolute_change ÷ |previous_value| × 100`
  - `previous_value` missing or `0` → `change_percent = null` (no `comparison_status` enum is
    stored separately — a `null` percent *is* the "insufficient_data" signal for that field).
  - "Stable" for a given metric = `abs(change) < that metric's threshold` — see the per-metric
    table in §3.2; there is no single global stable threshold.
  - **Completion rate**: `valid_samples ÷ expected_samples × 100` (`_completion_rate`),
    computed per metric over the 7 expected days.
- **Gating rules** (`compute_summary`):
  - If the report period has fewer than 3 valid days, **or** the comparison period has fewer
    than 3 valid days → `weekly_changes` is `[]` and a `data_quality.warnings` entry is added;
    the "vs last report" score `change` on `overall`/`category_summary` is also suppressed
    (`health_report_service.run_generation` checks the same gate before computing
    `previous_scores`).
  - A metric with a completion rate below 50% is excluded from `priority_items` ranking (it may
    still appear in `sleep_summary`/`health_summary`/`activity_summary` with a `null`/partial
    value).
- Missing data is `null`, never `0`. Records are deduplicated by `(metric, device_id, date)` at
  the upload layer (`UniqueConstraint("device_id", "date")` on `HealthRecord`/etc.) — the report
  layer only reads already-deduplicated rows.

## 2. Report generation stages

See `API_SPEC.md` §"Stage lifecycle" for the full mapping table (source spec's 6 stages onto
this backend's 3 stored `stage` values and progress checkpoints).

## 3. Summary calculation

### 3.1 Health score (`overall`)

```
score = Σ(category_score × category_weight) ÷ Σ(available_weight)
```

Weights: `sleep = 0.30`, `health = 0.40`, `activity = 0.20` (`report_stats_service._CATEGORY_WEIGHTS`).
A category with no score (no data at all that week) is excluded and the remaining weights are
renormalized over `Σ(available_weight)` — never treated as a 0.

**Medication is never computed by this backend.** The remaining 10% of the spec's suggested
weighting is reserved for a frontend-appended medication-adherence component. If a future
change makes the backend responsible for that component, `schema_version` must be bumped
(breaking change to the `overall` object shape).

`overall` also carries:
- `reason_codes`: one code per non-`good` category status, `f"{CATEGORY}_{STATUS}"`
  (e.g. `SLEEP_ATTENTION`, `HEALTH_ABNORMAL`, `ACTIVITY_INSUFFICIENT_DATA`).
- `data_completeness`: `{sleep, health, activity}`, each the % of the 7 period days that had
  *any* record for that category.

The AI never recomputes `score`/`status`/`reason_codes` — it only narrates them (see §7).

### 3.2 Weekly changes (`weekly_changes`)

One entry per metric, only when the change is significant for *that* metric and both period and
comparison have ≥3 valid days (§1). "Significant" = `abs(absolute_change) ≥ absolute_threshold`
**or** `abs(change_percent) ≥ percent_threshold` (either condition is sufficient).

| Metric (`metric` key) | Threshold | Favorable trend | Implementation |
|---|---|---|---|
| `sleep_total_minutes` | 30 min or 8% | up (see message caveat re: excessive sleep) | Implemented |
| `deep_sleep_ratio` | 5 percentage points | up | Implemented |
| `sleep_interruptions` (wake count) | 2 times or 20% | down | Implemented |
| `resting_heart_rate` | 5 bpm or 8% | down | **Simplified** — uses the day's overall averaged heart rate, not a heart rate isolated to low-activity windows (no activity-vs-heart-rate cross-referencing exists) |
| `hrv` | 10% | up | **Simplified** — uses the day's single averaged HRV value, not a per-day RMSSD computed from raw beat-to-beat samples then medianed |
| `blood_pressure_systolic` / `_diastolic` | 5 mmHg | judged by score (target-range), not raw direction | Implemented |
| `blood_oxygen` | 2 percentage points | up | Implemented |
| `steps` | 15% | up | Implemented |

Each entry: `metric, current, previous, absolute_change, change_percent, trend, health_impact,
severity, message, data_quality` (`{current_completion, previous_completion}`).
`health_impact` ∈ `positive/negative/neutral/depends`; blood pressure is judged by whether the
metric's own 0-100 score improved or worsened (`_health_impact`), everything else by whether its
trend matches that metric's known-favorable direction (`_FAVORABLE_TREND`).

### 3.3 Key metrics (`priority_items`)

```
priority_score = abnormal_score×0.40 + change_score×0.25 + persistence_score×0.20 + data_confidence×0.15
```

- `abnormal_score = 100 − metric's own 0-100 score` (worse score → higher abnormal_score).
- `change_score = min(100, abs(change) / that metric's §3.2 threshold × 100)` — percent
  threshold preferred, falling back to the absolute threshold (blood pressure uses the max of
  its systolic/diastolic absolute-threshold ratios).
- `persistence_score = abnormal_days ÷ valid_days × 100` for that metric — `abnormal_days`
  counts how many of the period's daily values individually scored `<60` when passed through
  that metric's own `health_scoring` function. This is a real formula (not a simplification):
  per-day values already exist in this codebase, they just aren't surfaced elsewhere.
- `data_confidence` = that metric's completion rate (§1).

Candidates below 50% completion are excluded entirely (§1). Sorted by `priority_score`
descending; top 5 returned (spec's "3–5" — this backend returns up to 5, fewer if fewer than 5
metrics qualify at all, and 0 if none do).

## 4. Sleep (`sleep_summary`)

`sleep_date` attribution and nap segregation: **not changed from the existing per-day upload
model** — this backend receives one summarized sleep record per date already (`SleepRecord`,
keyed by `device_id`+`date`), not individual sleep segments to attribute a `sleep_date` to. Nap
vs. main-sleep segregation is therefore **not implemented** (no data distinguishes them at the
summary level this backend stores).

| Field | Formula | Implementation |
|---|---|---|
| `time_in_bed_minutes` | `sleep_up_time − sleep_down_time` (per day, from the actual timestamps, not clock-time-of-day) | Implemented |
| `total_sleep_minutes` | `deep + light + REM` (device-reported `allSleepTime`, used as-is) | Implemented |
| `awake_duration_minutes` | `max(time_in_bed − total_sleep_time, 0)` | Implemented |
| `sleep_efficiency` | `total_sleep_time ÷ time_in_bed × 100` | Implemented |
| `deep_sleep_ratio_percent` | `deep ÷ total_sleep_time × 100` | Implemented |
| `rem_sleep_ratio_percent` | `REM ÷ total_sleep_time × 100` | Implemented |
| Weekly average | mean of valid (non-`invalid`) days | Implemented |
| `sleep_regularity_score` | circular-mean/circular-std of bedtime clock-times mapped to 0-100 | Implemented (documented as a heuristic proxy, not a clinical measure — see `_circular_regularity_score` docstring) |
| `invalid` per-day flag | `time_in_bed ≤ 0`, OR `total_sleep_time > 18h`, OR stage-minutes sum > `time_in_bed × 1.05` | Implemented — invalid days are excluded from every weekly average, not just flagged |

Cross-midnight times are never averaged as strings/clock-times — `time_in_bed` uses full
`sleep_down`/`sleep_up` timestamp subtraction, and bedtime regularity uses the circular-mean
helper (`_circular_mean_minutes`), never a naive arithmetic mean of "minutes past midnight".

The backend returns `summary` + `daily`; the frontend must not recompute weekly averages from
`daily` itself.

## 5. Health metrics (`health_summary.metrics`)

| Metric | Weekly summary | Implementation |
|---|---|---|
| Heart rate | avg / min / max of the daily averaged value | **Simplified** — no "resting" isolation (would need low-activity-window cross-referencing against activity data, which doesn't exist at that granularity); no weighted-by-sample-count average (only one value/day exists) |
| Blood pressure | systolic/diastolic avg, abnormal-day count via `health_scoring.score_blood_pressure` | Implemented (day-count instead of the source spec's abnormal-*reading*-count, since only one reading/day exists) |
| Blood oxygen | avg/min, `days_below_95`, `days_below_90` | **Simplified** — day-counts, not the source spec's per-sample reading count or cumulative low-SpO2 *duration* |
| Body temperature | avg/max, `baseline_median` + `baseline_delta` vs. a trailing 30-day personal median (`TEMPERATURE_BASELINE_DAYS`) | Implemented |
| HRV | avg of the daily averaged value | **Simplified** — not a per-day RMSSD-then-median (no raw beat-to-beat data) |
| Stress | avg, `high_stress_days` (day count where the daily average ≥ 70) | **Simplified** — day-count, not cumulative *minutes* ≥ 70 (no per-minute stress samples) |
| ECG | — | **Not implemented** — this codebase has no defined mapping from the device's `ecg.values` field to a normal/abnormal/unreadable classification; fabricating one would violate "只彙整裝置判讀，不推導疾病" |
| Respiratory rate / MET | avg only, no scoring table | Implemented (no clinical band exists for either per this codebase's existing `health_scoring.py` scope) |

Exclusion rules applied uniformly: heart rate outside a plausible device range, blood pressure
with systolic ≤ diastolic, blood oxygen outside 70–100% — these are upload-time/device concerns
already handled by whatever the device firmware sends; this report layer does not re-validate
raw device output beyond the `None`-safe averaging already shown above.

## 6. Activity (`activity_summary`)

| Field | Formula | Implementation |
|---|---|---|
| `total_steps` (weekly_steps) | `Σ daily_steps` | Implemented |
| `average_steps` | `total_steps ÷ valid_days` | Implemented |
| `goal_achievement_rate` | `goal_achieved_days ÷ valid_days × 100` | **Not implemented** — no per-user step goal is stored anywhere in this codebase |
| `active_minutes` / `moderate_vigorous_minutes` (MET ≥ 3) | minutes meeting an intensity threshold | **Not implemented** — no per-minute intensity/duration data exists, only one steps/distance/calories average per day |
| MET-minutes | `Σ(MET × duration_minutes)` | **Not implemented** — same reason |
| Cumulative device counters | `current_cumulative − previous_cumulative`, never negative on reset | **Not applicable** — this device payload (`ActivityAvgRecordPayload.stepValue`) is already a per-day value, not a raw cumulative counter the backend has to diff and reset-detect |

## 7. AI analysis rules

- AI input is exactly the deterministic JSON this document describes (`period`,
  `comparison_period`, `data_quality`, `overall`, `weekly_changes`, `category_summary`,
  `priority_items`, `sleep_summary`, `health_summary`, `activity_summary`) — never raw
  per-sample data (there isn't any to send).
- AI output is fixed: `overall_title`, `overall_summary`, `category_narratives`,
  `key_findings`, `potential_risks`, `recommendations`, `questions_for_user`, `safety_notice`
  (see `health_report_prompt.md` §3 for the exact shape).
- **Post-hoc allowlist validation**: after the AI responds, `health_report_service`
  (`_collect_allowed_numbers` / `_validate_ai_evidence`) collects every numeric value that
  appears anywhere in the evidence payload sent to the AI, then checks every
  `potential_risks[].evidence[].value`/`.change` the AI returned against that set (± a small
  tolerance for rounding). Evidence entries that don't match are dropped rather than displayed.
  This is scoped to the structured `evidence` array only — free-text fields
  (`overall_summary`/`category_narratives`/`content`/`description`) are natural language and are
  **not** scanned digit-by-digit; a number that leaks into prose is a known gap, not a validated
  guarantee. The prompt rules instruct the AI to always quote structured numbers verbatim so
  this validation actually passes rather than silently emptying every risk's evidence.
- The AI never changes a risk level, never diagnoses, never suggests medication changes — see
  `health_report_prompt.md` §2 for the full rule list (unchanged from before this update, aside
  from the new allowlist note and the new `weekly_changes`/`reason_codes`/`data_completeness`
  input fields documented in §0 there).

## 8. Final payload

See `API_SPEC.md` for the full response shape returned by `GET /health-reports/{report_id}`.
