# Health Report API Spec

Formal contract for the 3 endpoints in `src/health_report/api.py`. See `CALCULATION_SPEC.md`
for how every field in the final payload is computed. Paths, field names (`report_id` not
`job_id`, `stage` values, etc.) intentionally keep this backend's existing naming rather than
adopting the source spec's example `/v1/reports`/`job_id` contract — no breaking rename.

Base path: `/health-reports` (requires an authenticated user — `CurrentUserId`).

## POST /health-reports

Creates a report-generation job for the caller's most-recently-synced bound device and starts
background generation (`FastAPI BackgroundTasks`).

**Request body** (`HealthReportCreateRequest`):

```json
{
  "report_type": "latest_health_summary",
  "language": "zh-TW",
  "include_ai_analysis": true,
  "date": "2026-07-23"
}
```

- `report_type`: fixed to `"latest_health_summary"` for now (no other report types exist).
- `language`: `"zh-TW"` or `"en"`.
- `include_ai_analysis`: when `false`, skips the AI call entirely — `ai_analysis` is `null` in
  the final payload and narrative fields (`overall.title`/`overall.summary`/category
  `summary`) fall back to fixed status-label strings (`_default_ai_fallback`), never invented.
- `date`: optional anchor date (`YYYY-MM-DD`). The 7-day period ends on this date (inclusive).
  Omit to default to "yesterday" in the fixed `REPORT_TZ` (UTC+8 — see CALCULATION_SPEC.md §0,
  timezone is not configurable per request).

**Response — 200**

```json
{
  "success": true,
  "data": {
    "report_id": "rpt_...",
    "job_id": "rpt_...",
    "status": "queued",
    "progress": 0,
    "poll_interval_seconds": 10
  }
}
```

`job_id` is an alias of `report_id` kept for client compatibility; both are the same string.

**Errors** — `{"success": false, "error": {"code": ..., "message": ...}}` with HTTP status:

| HTTP | `code` | Cause |
|---|---|---|
| 400 | `NO_DEVICE_BOUND` | Caller has no bound device to report on |
| 400 | `INVALID_DATE` | `date` is malformed or in the future |

## GET /health-reports/{report_id}/status

Polling endpoint while a report is generating. **Always HTTP 200** — failure is signaled via
`success: false` in the body, not an HTTP error status (unlike the ownership/lookup errors
below, which do use `_error_response` with a real HTTP status).

**Response — in progress / queued**

```json
{
  "success": true,
  "data": {
    "report_id": "rpt_...",
    "status": "processing",
    "stage": "collecting_data",
    "stage_label": "正在彙整穿戴裝置數據",
    "progress": 75,
    "poll_interval_seconds": 10
  }
}
```

**Response — completed**

```json
{
  "success": true,
  "data": {
    "report_id": "rpt_...",
    "status": "completed",
    "stage": "completed",
    "stage_label": "健康摘要已完成",
    "progress": 100,
    "result_available": true
  }
}
```

**Response — failed**

```json
{
  "success": false,
  "error": {
    "code": "REPORT_GENERATION_FAILED",
    "message": "健康摘要產生失敗，請稍後重新嘗試。",
    "retryable": true
  }
}
```

**Errors using the ownership/lookup path** (`_error_response`, real HTTP status):

| HTTP | `code` | Cause |
|---|---|---|
| 404 | `REPORT_NOT_FOUND` | No report with that id |
| 403 | `FORBIDDEN` | Report belongs to a different user |

### Stage lifecycle

The source spec describes 6 conceptual stages with progress bands; this backend stores only 3
`stage` values (`status`/`stage`/`progress` columns on `HealthReportRecord`). The table below is
the mapping — clients should treat `progress` as coarse/monotonic, not a precise ETA.

| Source-spec stage | Source-spec progress | Stored `status` | Stored `stage` | `progress` set here | What happens |
|---|---|---|---|---|---|
| QUEUED | 0–10% | `queued` | `null` | `0` | Job row created, `POST` returns |
| AGGREGATING | 11–45% | `processing` | `collecting_data` | `20` | Background task starts; device/date rows about to be fetched |
| COMPARING | 46–65% | `processing` | `collecting_data` | `20` (no separate checkpoint) | `report_stats_service.compute_summary` runs (period + comparison + trailing temperature-baseline queries) |
| SCORING | 66–78% | `processing` | `collecting_data` | `75` | Stats/scores/`weekly_changes`/`priority_items` finished; about to call the AI (or skip it) |
| AI_ANALYZING | 79–95% | `processing` | `ai_analysis` | `85` | AI call + evidence-allowlist validation (skipped if `include_ai_analysis=false`, this stage still runs but the AI call itself is skipped) |
| COMPLETED | 100% | `completed` | `completed` | `100` | `payload` column populated, terminal state |

On any exception, the job moves to the terminal `status="failed"` (see `GET .../status`
"failed" response above) — there is no intermediate "retrying" state; the client re-issues a
new `POST /health-reports` to retry.

## GET /health-reports/{report_id}

Returns the completed report. Requires `status == "completed"` (409 otherwise).

**Errors:**

| HTTP | `code` | Cause |
|---|---|---|
| 404 | `REPORT_NOT_FOUND` | No report with that id |
| 403 | `FORBIDDEN` | Report belongs to a different user |
| 409 | `REPORT_NOT_READY` | Report exists but hasn't finished generating |

**Response — 200**, `{"success": true, "data": <final payload>}`:

```json
{
  "report_id": "rpt_...",
  "user_id": 123,
  "report_type": "latest_health_summary",
  "status": "completed",
  "language": "zh-TW",
  "period": {"start_date": "2026-07-17", "end_date": "2026-07-23", "days": 7, "label": "2026-07-17–2026-07-23"},
  "comparison_period": {"start_date": "2026-07-10", "end_date": "2026-07-16", "days": 7},
  "data_quality": {
    "coverage_percentage": 100,
    "valid_days": 7,
    "comparison_valid_days": 7,
    "expected_days": 7,
    "last_synced_at": "2026-07-23T08:00:00",
    "device_name": "...",
    "warnings": []
  },
  "overall": {
    "score": 82,
    "score_max": 100,
    "status": "good",
    "reason_codes": [],
    "data_completeness": {"sleep": 100, "health": 100, "activity": 100},
    "status_label": "表現良好",
    "change": {"value": 3, "unit": "point", "direction": "up", "comparison_label": "較前 7 天上升 3 分"},
    "title": "整體狀態穩定向上",
    "summary": "..."
  },
  "weekly_changes": [
    {
      "metric": "resting_heart_rate",
      "current": 76.3,
      "previous": 70.1,
      "absolute_change": 6.2,
      "change_percent": 8.8,
      "trend": "up",
      "health_impact": "negative",
      "severity": "warning",
      "message": "靜息心率較前期上升 6.2bpm",
      "data_quality": {"current_completion": 100.0, "previous_completion": 100.0}
    }
  ],
  "priority_items": [
    {
      "id": "priority_heart_rate",
      "metric": "heart_rate",
      "severity": "warning",
      "title": "平均心率",
      "value": 76.3,
      "unit": "bpm",
      "change_value": 6.2,
      "change_percentage": 8.8,
      "occurred_at": null,
      "action_label": "查看健康詳情"
    }
  ],
  "category_summary": {
    "sleep": {"score": 88, "score_max": 100, "status": "good", "change": 2, "change_direction": "up", "summary": "..."},
    "health": {"score": 74, "score_max": 100, "status": "attention", "change": -4, "change_direction": "down", "summary": "..."},
    "activity": {"score": 80, "score_max": 100, "status": "good", "change": 0, "change_direction": "stable", "summary": "..."}
  },
  "sleep_summary": {
    "average_total_sleep_minutes": 430,
    "average_deep_sleep_minutes": 80,
    "average_light_sleep_minutes": 260,
    "average_rem_sleep_minutes": 90,
    "average_wake_count": 1.4,
    "average_bedtime": "23:12",
    "average_wake_time": "06:58",
    "sleep_regularity_score": 82,
    "average_time_in_bed_minutes": 455,
    "average_sleep_efficiency": 94.5,
    "average_awake_duration_minutes": 25,
    "deep_sleep_ratio_percent": 18.6,
    "rem_sleep_ratio_percent": 20.9,
    "completion_rate": 100.0,
    "invalid_days_excluded": 0,
    "change": {"total_sleep_minutes": 12, "deep_sleep_minutes": 5, "rem_sleep_minutes": -2, "wake_count": -0.3},
    "daily": []
  },
  "health_summary": {
    "metrics": [
      {
        "key": "heart_rate", "label": "平均心率", "value": 76.3, "unit": "bpm", "status": "attention", "score": 65,
        "change_value": 6.2, "change_percentage": 8.8, "change_direction": "up",
        "completion_rate": 100.0, "persistence_score": 42.9,
        "minimum": 62.0, "maximum": 88.0, "reference_min": 60, "reference_max": 100
      }
    ]
  },
  "activity_summary": {
    "average_steps": 8200,
    "average_distance_km": 5.6,
    "average_calories_kcal": 2100,
    "total_steps": 57400,
    "total_distance_km": 39.2,
    "total_calories_kcal": 14700,
    "completion_rate": 100.0,
    "change": {"steps_percentage": 12.4, "distance_km": 0.6, "calories_percentage": 3.1},
    "daily": []
  },
  "ai_analysis": {
    "model": "...",
    "generated_at": "2026-07-24T02:00:00+00:00",
    "key_findings": [],
    "potential_risks": [],
    "recommendations": [],
    "questions_for_user": [],
    "safety_notice": {"level": "informational", "message": "..."}
  },
  "created_at": "2026-07-24T01:55:00+00:00",
  "completed_at": "2026-07-24T02:00:10+00:00"
}
```

Notes on fields new in this update (see CALCULATION_SPEC.md for formulas):
- `overall.reason_codes`, `overall.data_completeness` — §3.1.
- `weekly_changes` (top-level array, sibling of `priority_items`) — §3.2.
- `health_summary.metrics[].score`, `.completion_rate`, `.persistence_score` — §3.3/§5.
- `health_summary.metrics[]` blood-oxygen entries additionally carry `days_below_95`/
  `days_below_90`; the stress entry carries `high_stress_days`; the body-temperature entry
  carries `baseline_median`/`baseline_delta` when a 30-day trailing baseline exists — §5.
- `sleep_summary.average_time_in_bed_minutes`, `.average_sleep_efficiency`,
  `.average_awake_duration_minutes`, `.deep_sleep_ratio_percent`, `.rem_sleep_ratio_percent`,
  `.completion_rate`, `.invalid_days_excluded` — §4.
- `data_quality.comparison_valid_days` and a `warnings` entry when weekly comparison is
  suppressed for having fewer than 3 valid days — §1.

All of the above are additive to the previously-existing payload shape — no field was renamed
or removed, so existing consumers reading only the old keys are unaffected.
