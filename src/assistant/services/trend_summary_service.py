import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.assistant.models.trend_summary_model import TrendSummaryRecord
from src.assistant.services.errors import AssistantError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.activity_model import ActivityRecord
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord

LOOKBACK_DAYS = 7
# A longer personal baseline so the AI can compare today against "normal for this specific user"
# rather than only a generic clinical range — see trend_prompt.md's baseline-priority rule.
BASELINE_DAYS = 30
TREND_SUMMARY_MAX_TOKENS = int(os.getenv("ASSISTANT_TREND_MAX_TOKENS", 3000))

# No per-device timezone is stored anywhere in this codebase; matches data_summary_service's
# fixed +08:00 treatment of "today" for every device.
REPORT_TZ = timezone(timedelta(hours=8))

_PROMPT_RULES = (Path(__file__).parent / "trend_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object containing the overall summary, today's recommendations, and the
per-metric assessment described above. The exact field names are up to you; the content and
rules above are not."""


def _numeric_stats(values: list[float | None]) -> dict:
    present = [v for v in values if v is not None]
    if not present:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": round(sum(present) / len(present), 1),
        "min": round(min(present), 1),
        "max": round(max(present), 1),
    }


def _time_of_day_minutes(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    return dt.hour * 60 + dt.minute + dt.second / 60


def _minutes_to_clock(minutes: float) -> str:
    minutes = int(round(minutes)) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _circular_mean_minutes(minutes: list[float]) -> float:
    """Averages clock times as points on a 24h circle so a set of times like 23:41 and 00:15
    averages to ~23:58, not ~12:xx as a naive numeric mean would (see data_summary_service's
    identical rationale)."""
    angles = [m / 1440 * 2 * math.pi for m in minutes]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)
    mean_angle = math.atan2(sin_sum, cos_sum) % (2 * math.pi)
    return mean_angle / (2 * math.pi) * 1440


def _clock_stats(iso_strings: list[str | None]) -> dict:
    """min/max are plain min/max of the day's minute-of-day values (not circular-aware) — a
    reasonable simplification for a 7-day bedtime/wake-up window that rarely spans midnight
    both ways within the same week."""
    minutes = [m for m in (_time_of_day_minutes(s) for s in iso_strings) if m is not None]
    if not minutes:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": _minutes_to_clock(_circular_mean_minutes(minutes)),
        "min": _minutes_to_clock(min(minutes)),
        "max": _minutes_to_clock(max(minutes)),
    }


def _stats_with_today(stats_fn, all_values: list, today_values: list) -> dict:
    """Adds a `today` key — computed via the same stats_fn so it's formatted identically to
    avg/min/max (e.g. a clock string, not a raw ISO timestamp) — holding the most recent day's
    own reading alongside the trailing-7-day avg/min/max baseline. Falls back to `None` (never to
    the 7-day avg) when today hasn't synced any data yet, so the AI can tell the two cases apart
    instead of silently treating "no data" as "unchanged from average"."""
    stats = stats_fn(all_values)
    present_today = [v for v in today_values if v is not None]
    stats["today"] = stats_fn(present_today)["avg"] if present_today else None
    return stats


def _stats_with_today_and_baseline(stats_fn, values_7: list, today_values: list, values_30: list) -> dict:
    """Like `_stats_with_today`, plus a `baseline30` avg/min/max computed over the trailing 30
    days — this user's own longer-run normal, for comparisons a 7-day window is too short/noisy
    to anchor (see trend_prompt.md)."""
    stats = _stats_with_today(stats_fn, values_7, today_values)
    stats["baseline30"] = stats_fn(values_30)
    return stats


def _aggregate_sleep_trend(rows_7: list[SleepRecord], rows_30: list[SleepRecord], today_date: str) -> dict:
    summaries_7 = [row.sleep_summary or {} for row in rows_7]
    summaries_30 = [row.sleep_summary or {} for row in rows_30]
    today_summaries = [row.sleep_summary or {} for row in rows_7 if row.date == today_date]

    def numeric(field: str) -> dict:
        return _stats_with_today_and_baseline(
            _numeric_stats,
            [s.get(field) for s in summaries_7],
            [s.get(field) for s in today_summaries],
            [s.get(field) for s in summaries_30],
        )

    def clock(field: str) -> dict:
        return _stats_with_today_and_baseline(
            _clock_stats,
            [s.get(field) for s in summaries_7],
            [s.get(field) for s in today_summaries],
            [s.get(field) for s in summaries_30],
        )

    return {
        "sleepQuality": numeric("sleepQuality"),
        "totalSleep": numeric("allSleepTime"),
        "wakeCount": numeric("wakeCount"),
        # remSleepTime is only present in SleepRecord.sleep_summary rows uploaded after the
        # device schema gained this field (see sleep_schema.SleepRecordPayload/SleepSummaryPayload)
        # — older rows simply lack the key, so .get() naturally falls back to insufficient data.
        "remSleepTime": numeric("remSleepTime"),
        "lightSleep": numeric("lowSleepTime"),
        "deepSleep": numeric("deepSleepTime"),
        "sleepUp": clock("sleepUp"),
        "sleepDown": clock("sleepDown"),
    }


def _health_field(row: HealthRecord, key: str, sub_key: str) -> float | None:
    data = row.data or {}
    sub = data.get(key)
    return sub.get(sub_key) if sub else None


def _bp_string(systolic: float | None, diastolic: float | None) -> str | None:
    return f"{systolic}/{diastolic}" if systolic is not None and diastolic is not None else None


def _aggregate_health_trend(rows_7: list[HealthRecord], rows_30: list[HealthRecord], today_date: str) -> dict:
    today_rows = [r for r in rows_7 if r.date == today_date]

    def numeric(key: str, sub_key: str) -> dict:
        return _stats_with_today_and_baseline(
            _numeric_stats,
            [_health_field(r, key, sub_key) for r in rows_7],
            [_health_field(r, key, sub_key) for r in today_rows],
            [_health_field(r, key, sub_key) for r in rows_30],
        )

    systolic_stats = numeric("bloodPressure", "systolic")
    diastolic_stats = numeric("bloodPressure", "diastolic")
    return {
        "heartRate": numeric("heartRate", "ppgs"),
        "bloodPressure": {
            "avg": _bp_string(systolic_stats["avg"], diastolic_stats["avg"]),
            "min": _bp_string(systolic_stats["min"], diastolic_stats["min"]),
            "max": _bp_string(systolic_stats["max"], diastolic_stats["max"]),
            "today": _bp_string(systolic_stats["today"], diastolic_stats["today"]),
            "baseline30": {
                "avg": _bp_string(systolic_stats["baseline30"]["avg"], diastolic_stats["baseline30"]["avg"]),
                "min": _bp_string(systolic_stats["baseline30"]["min"], diastolic_stats["baseline30"]["min"]),
                "max": _bp_string(systolic_stats["baseline30"]["max"], diastolic_stats["baseline30"]["max"]),
            },
        },
        "bloodOxygen": numeric("bloodOxygen", "oxygens"),
        "bodyTemperature": numeric("bodyTemperature", "temperature"),
        "hrv": numeric("hrv", "values"),
        "stress": numeric("stress", "pressure"),
        "met": numeric("met", "values"),
    }


def _aggregate_activity_trend(rows_7: list[ActivityRecord], rows_30: list[ActivityRecord], today_date: str) -> dict:
    today_rows = [r for r in rows_7 if r.date == today_date]

    def field(row: ActivityRecord, key: str) -> float | None:
        return (row.data or {}).get(key)

    def numeric(key: str) -> dict:
        return _stats_with_today_and_baseline(
            _numeric_stats,
            [field(r, key) for r in rows_7],
            [field(r, key) for r in today_rows],
            [field(r, key) for r in rows_30],
        )

    return {
        "steps": numeric("stepValue"),
        "distance": numeric("disValue"),
        "calories": numeric("calValue"),
    }


def _week_dates(end_date: date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _validate(mac_address: str | None, previous_response_id: str | None) -> tuple[str, str]:
    if not mac_address or not mac_address.strip():
        raise AssistantError(400, "macAddress 不可為空", code="INVALID_PARAMETER")
    if not previous_response_id or not previous_response_id.strip():
        raise AssistantError(
            400, "responseId 不可為空，請先呼叫 /assistant/profile", code="INVALID_PARAMETER"
        )
    return mac_address.strip(), previous_response_id.strip()


def _resolve_end_date(date_str: str | None) -> date:
    """Defaults to "today" in REPORT_TZ when the frontend omits `date` (unchanged prior
    behavior); when given, it's the last day of the trailing 7-day window to query, matching
    data_summary_service's `date` param semantics."""
    if not date_str or not date_str.strip():
        return datetime.now(REPORT_TZ).date()
    try:
        return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise AssistantError(400, "date 格式錯誤，需為 YYYY-MM-DD", code="INVALID_PARAMETER") from None


def _save_uploaded_image(image_bytes: bytes, content_type: str | None) -> str | None:
    pic_id = files.generate_pic_id()
    return files.save_analysis_image(image_bytes, content_type, pic_id)


def generate_trend_summary(
    db: Session,
    mac_address: str | None,
    previous_response_id: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
    language: str = "zh",
    date_str: str | None = None,
) -> TrendSummaryRecord:
    """Stage 2 of the assistant flow: aggregates the trailing 7 days (ending on `date_str`, or
    today in REPORT_TZ if omitted) of sleep/health/activity data into avg/min/max per metric, plus
    a `today` value holding just the last day's own reading and a `baseline30` avg/min/max over
    the trailing 30 days (see `_stats_with_today_and_baseline`) — this user's own longer-run
    normal, preferred over generic ranges — then asks the AI (chained from /assistant/profile) to
    assess each metric against the user's body-characteristic level established in stage 1."""
    mac_address, previous_response_id = _validate(mac_address, previous_response_id)

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AssistantError(404, "找不到對應設備", code="DEVICE_NOT_FOUND")

    end_date = _resolve_end_date(date_str)
    start_date = end_date - timedelta(days=LOOKBACK_DAYS - 1)
    baseline_start_date = end_date - timedelta(days=BASELINE_DAYS - 1)
    dates_7 = set(_week_dates(end_date, LOOKBACK_DAYS))
    dates_30 = _week_dates(end_date, BASELINE_DAYS)

    # One query per table over the wider 30-day window; the 7-day rows are a subset filtered in
    # Python, rather than querying each table twice.
    sleep_rows_30 = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id, SleepRecord.date.in_(dates_30)
    ).all()
    health_rows_30 = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id, HealthRecord.date.in_(dates_30)
    ).all()
    activity_rows_30 = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device.id, ActivityRecord.date.in_(dates_30)
    ).all()

    sleep_rows_7 = [r for r in sleep_rows_30 if r.date in dates_7]
    health_rows_7 = [r for r in health_rows_30 if r.date in dates_7]
    activity_rows_7 = [r for r in activity_rows_30 if r.date in dates_7]

    if not sleep_rows_7 and not health_rows_7 and not activity_rows_7:
        raise AssistantError(422, "近 7 天內查無有效資料，無法生成健康趨勢摘要", code="INSUFFICIENT_DATA")

    today_date = end_date.isoformat()
    trend_data = {
        "sleep": _aggregate_sleep_trend(sleep_rows_7, sleep_rows_30, today_date),
        "health": _aggregate_health_trend(health_rows_7, health_rows_30, today_date),
        "activity": _aggregate_activity_trend(activity_rows_7, activity_rows_30, today_date),
    }
    payload = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "todayDate": today_date,
        "baseline30StartDate": baseline_start_date.isoformat(),
        "trendData": trend_data,
    }

    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, language)
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            f"Input:\n{json.dumps(payload, default=str)}",
            previous_response_id,
            image_bytes=image_bytes,
            mime_type=content_type,
            max_output_tokens=TREND_SUMMARY_MAX_TOKENS,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("AI trend summary generation failed")
        raise AssistantError(502, "健康趨勢摘要生成失敗", code="SUMMARY_GENERATION_FAILED") from e

    image_path = _save_uploaded_image(image_bytes, content_type) if image_bytes else None

    record = db.query(TrendSummaryRecord).filter(
        TrendSummaryRecord.mac_address == mac_address,
        TrendSummaryRecord.end_date == end_date.isoformat(),
    ).first()
    if record is None:
        record = TrendSummaryRecord(mac_address=mac_address, end_date=end_date.isoformat())
        db.add(record)

    record.start_date = start_date.isoformat()
    record.trend_data = trend_data
    record.ai_response = result
    record.level_consistent = bool(result.get("levelConsistent", True))
    record.image_path = image_path
    record.previous_response_id = previous_response_id
    record.response_id = response_id
    db.commit()
    db.refresh(record)
    return record
