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
TREND_SUMMARY_MAX_TOKENS = int(os.getenv("ASSISTANT_TREND_MAX_TOKENS", 2000))

# No per-device timezone is stored anywhere in this codebase; matches data_summary_service's
# fixed +08:00 treatment of "today" for every device.
REPORT_TZ = timezone(timedelta(hours=8))

_PROMPT_RULES = (Path(__file__).parent / "trend_prompt.md").read_text(encoding="utf-8")
_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object containing the per-metric assessment described above. The exact
field names are up to you; the content and rules above are not."""


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


def _aggregate_sleep_trend(rows: list[SleepRecord]) -> dict:
    summaries = [row.sleep_summary or {} for row in rows]
    return {
        "sleepQuality": _numeric_stats([s.get("sleepQuality") for s in summaries]),
        "totalSleep": _numeric_stats([s.get("allSleepTime") for s in summaries]),
        "wakeCount": _numeric_stats([s.get("wakeCount") for s in summaries]),
        # This system's sleep data model only tracks deep/light/total sleep, never a separate
        # REM segment (see data_summary_service._aggregate_sleep), so this is always reported
        # as unavailable rather than fabricated.
        "rem": {"avg": None, "min": None, "max": None},
        "lightSleep": _numeric_stats([s.get("lowSleepTime") for s in summaries]),
        "deepSleep": _numeric_stats([s.get("deepSleepTime") for s in summaries]),
        "sleepUp": _clock_stats([s.get("sleepUp") for s in summaries]),
        "sleepDown": _clock_stats([s.get("sleepDown") for s in summaries]),
    }


def _health_field(row: HealthRecord, key: str, sub_key: str) -> float | None:
    data = row.data or {}
    sub = data.get(key)
    return sub.get(sub_key) if sub else None


def _bp_string(systolic: float | None, diastolic: float | None) -> str | None:
    return f"{systolic}/{diastolic}" if systolic is not None and diastolic is not None else None


def _aggregate_health_trend(rows: list[HealthRecord]) -> dict:
    systolic_stats = _numeric_stats([_health_field(r, "bloodPressure", "systolic") for r in rows])
    diastolic_stats = _numeric_stats([_health_field(r, "bloodPressure", "diastolic") for r in rows])
    return {
        "heartRate": _numeric_stats([_health_field(r, "heartRate", "ppgs") for r in rows]),
        "bloodPressure": {
            "avg": _bp_string(systolic_stats["avg"], diastolic_stats["avg"]),
            "min": _bp_string(systolic_stats["min"], diastolic_stats["min"]),
            "max": _bp_string(systolic_stats["max"], diastolic_stats["max"]),
        },
        "bloodOxygen": _numeric_stats([_health_field(r, "bloodOxygen", "oxygens") for r in rows]),
        "bodyTemperature": _numeric_stats([_health_field(r, "bodyTemperature", "temperature") for r in rows]),
        "hrv": _numeric_stats([_health_field(r, "hrv", "values") for r in rows]),
        "stress": _numeric_stats([_health_field(r, "stress", "pressure") for r in rows]),
        "met": _numeric_stats([_health_field(r, "met", "values") for r in rows]),
    }


def _aggregate_activity_trend(rows: list[ActivityRecord]) -> dict:
    def field(row: ActivityRecord, key: str) -> float | None:
        return (row.data or {}).get(key)

    return {
        "steps": _numeric_stats([field(r, "stepValue") for r in rows]),
        "distance": _numeric_stats([field(r, "disValue") for r in rows]),
        "calories": _numeric_stats([field(r, "calValue") for r in rows]),
    }


def _week_dates(end_date: date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _validate(mac_address: str | None, previous_response_id: str | None) -> tuple[str, str]:
    if not mac_address or not mac_address.strip():
        raise AssistantError(400, "macAddress 不可為空", code="INVALID_PARAMETER")
    if not previous_response_id or not previous_response_id.strip():
        raise AssistantError(
            400, "previousResponseId 不可為空，請先呼叫 /assistant/profile", code="INVALID_PARAMETER"
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
    today in REPORT_TZ if omitted) of sleep/health/activity data into avg/min/max per metric,
    then asks the AI (chained from /assistant/profile) to assess each metric against the user's
    body-characteristic level established in stage 1."""
    mac_address, previous_response_id = _validate(mac_address, previous_response_id)

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AssistantError(404, "找不到對應設備", code="DEVICE_NOT_FOUND")

    end_date = _resolve_end_date(date_str)
    start_date = end_date - timedelta(days=LOOKBACK_DAYS - 1)
    dates = _week_dates(end_date, LOOKBACK_DAYS)

    sleep_rows = db.query(SleepRecord).filter(
        SleepRecord.device_id == device.id, SleepRecord.date.in_(dates)
    ).all()
    health_rows = db.query(HealthRecord).filter(
        HealthRecord.device_id == device.id, HealthRecord.date.in_(dates)
    ).all()
    activity_rows = db.query(ActivityRecord).filter(
        ActivityRecord.device_id == device.id, ActivityRecord.date.in_(dates)
    ).all()

    if not sleep_rows and not health_rows and not activity_rows:
        raise AssistantError(422, "近 7 天內查無有效資料，無法生成健康趨勢摘要", code="INSUFFICIENT_DATA")

    trend_data = {
        "sleep": _aggregate_sleep_trend(sleep_rows),
        "health": _aggregate_health_trend(health_rows),
        "activity": _aggregate_activity_trend(activity_rows),
    }
    payload = {"startDate": start_date.isoformat(), "endDate": end_date.isoformat(), "trendData": trend_data}

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
