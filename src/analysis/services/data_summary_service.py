import json
import math
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from src.analysis.models.analysis_pic_model import AnalysisPicRecord
from src.analysis.models.data_summary_model import DataSummaryRecord
from src.analysis.services.errors import AnalysisError
from src.core import ai_client, files
from src.core.logging import logger
from src.device.models.device_model import DeviceRecord
from src.device.models.health_model import HealthRecord
from src.device.models.sleep_model import SleepRecord

LOOKBACK_DAYS = 7
PROMPT_VERSION = "data_summary_v2"

# A full report has up to 16 metrics (name/value/unit/status/note each) plus a 主要發現 highlights
# block, an overall summary, and disclaimer, all in Traditional Chinese — this routinely exceeds
# the shared OPENAI_MAX_TOKENS default (tuned for shorter chat-style replies) and gets truncated
# mid-JSON, so this endpoint gets its own larger, independently-tunable budget instead of relying
# on that default.
DATA_SUMMARY_MAX_TOKENS = int(os.getenv("DATA_SUMMARY_MAX_TOKENS", 2500))

# No per-device timezone is stored anywhere in this codebase. `date` is treated as a wall-clock
# calendar day in a single fixed offset for every device, matching the +08:00 example in the
# spec this endpoint implements.
REPORT_TZ = timezone(timedelta(hours=8))

_PROMPT_RULES = (Path(__file__).parent / "data_summary_prompt.md").read_text(encoding="utf-8")

_SYSTEM_PROMPT = f"""{_PROMPT_RULES}

Return a single JSON object containing the report described above (title, statistics period,
per-metric list with average/unit/status/short note, overall summary, and a health-data
disclaimer). The exact field names are up to you; the content and rules above are not."""

# General, non-personalized reference ranges used only because metric_status must come from the
# system rather than be invented by the AI (see data_summary_prompt.md #8/#9). These are not
# clinical diagnostic thresholds and are not derived per-user (contrast with the personalized
# baseline health_insight_service asks the AI to establish for a different feature).
_HEART_RATE_RANGE = (60, 100)
_BODY_TEMPERATURE_RANGE = (36.1, 37.2)
_SLEEP_DURATION_RANGE_MINUTES = (420, 540)  # ~7-9 hours
_SLEEP_QUALITY_NORMAL_MIN = 70
_BLOOD_OXYGEN_NORMAL_MIN = 95
_STRESS_HIGH_MIN = 30
_MET_RANGE = (1.0, 3.0)
_BP_LOW = (90, 60)  # systolic, diastolic
_BP_HIGH = (130, 85)
_RESPIRATORY_RANGE = (12, 20)  # general adult resting breaths/min
# General consumer-wearable RMSSD-style HRV convention: lower is the flag worth surfacing (poor
# recovery / high sympathetic load); there's no "too high" HRV concern, so this is a floor, not a
# range, unlike the other metrics above.
_HRV_NORMAL_MIN = 20
# General sleep-hygiene convention: 0-2 nighttime awakenings is typical for adults.
_AWAKE_COUNT_NORMAL_MAX = 2

# metric -> (json key inside HealthRecord.data, sub-key) used both to average and to detect
# whether a given day's row has usable data for that metric.
_HEALTH_METRIC_FIELDS = {
    "heart_rate_bpm": ("heartRate", "ppgs"),
    "blood_oxygen_percent": ("bloodOxygen", "oxygens"),
    "body_temperature_celsius": ("bodyTemperature", "temperature"),
    "respiratory_breaths_per_min": ("respiratory", "resRates"),
    "hrv_ms": ("hrv", "values"),
    "stress": ("stress", "pressure"),
    "met": ("met", "values"),
}


def _average(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 1)


def _time_of_day_minutes(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    return dt.hour * 60 + dt.minute + dt.second / 60


def _circular_mean_clock(iso_strings: list[str | None]) -> str | None:
    """Averages clock times (e.g. sleep start / wake-up) as points on a 24h circle so a set of
    times like 23:41 and 00:15 averages to ~23:58, not ~12:xx as a naive numeric mean would."""
    minutes = [_time_of_day_minutes(s) for s in iso_strings]
    present = [m for m in minutes if m is not None]
    if not present:
        return None
    angles = [m / 1440 * 2 * math.pi for m in present]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)
    mean_angle = math.atan2(sin_sum, cos_sum) % (2 * math.pi)
    mean_minutes = int(round(mean_angle / (2 * math.pi) * 1440)) % 1440
    return f"{mean_minutes // 60:02d}:{mean_minutes % 60:02d}"


def _health_field(row: HealthRecord, key: str, sub_key: str) -> float | None:
    data = row.data or {}
    sub = data.get(key)
    return sub.get(sub_key) if sub else None


def _week_dates(end_date: date, days: int) -> list[str]:
    return [(end_date - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]


def _aggregate_sleep(sleep_rows: list[SleepRecord]) -> dict:
    summaries = [row.sleep_summary or {} for row in sleep_rows]
    return {
        "sleep_quality": _average([s.get("sleepQuality") for s in summaries]),
        "sleep_duration_minutes": _average([s.get("allSleepTime") for s in summaries]),
        "sleep_start_time": _circular_mean_clock([s.get("sleepDown") for s in summaries]),
        "wake_up_time": _circular_mean_clock([s.get("sleepUp") for s in summaries]),
        "awake_count": _average([s.get("wakeCount") for s in summaries]),
        # This system's sleep data model only tracks deep/light/total sleep, never a separate
        # REM segment, so this is always reported as unavailable rather than fabricated.
        "rem_duration_minutes": None,
        "light_sleep_duration_minutes": _average([s.get("lowSleepTime") for s in summaries]),
        "deep_sleep_duration_minutes": _average([s.get("deepSleepTime") for s in summaries]),
    }


def _aggregate_health(health_rows: list[HealthRecord]) -> dict:
    averages = {
        metric: _average([_health_field(r, key, sub_key) for r in health_rows])
        for metric, (key, sub_key) in _HEALTH_METRIC_FIELDS.items()
    }
    systolic = _average([_health_field(r, "bloodPressure", "systolic") for r in health_rows])
    diastolic = _average([_health_field(r, "bloodPressure", "diastolic") for r in health_rows])
    return {
        **averages,
        "blood_pressure": {"systolic_mmhg": systolic, "diastolic_mmhg": diastolic},
    }


def _status_from_range(value: float | None, low: float, high: float) -> str:
    if value is None:
        return "insufficient_data"
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def _blood_pressure_status(bp: dict) -> str:
    systolic, diastolic = bp.get("systolic_mmhg"), bp.get("diastolic_mmhg")
    if systolic is None or diastolic is None:
        return "insufficient_data"
    if systolic < _BP_LOW[0] or diastolic < _BP_LOW[1]:
        return "low"
    if systolic >= _BP_HIGH[0] or diastolic >= _BP_HIGH[1]:
        return "high"
    return "normal"


def _presence_status(value) -> str:
    """For metrics with no defensible general normal range (clock times, absolute light/deep
    sleep minutes): report whether data exists at all rather than inventing a threshold, per
    data_summary_prompt.md #9. Distinct from "unknown" (HRV-style, where a range was considered
    and deliberately rejected) only in intent — same status string, since that's the vocabulary
    the prompt already defines (data_summary_prompt.md #7)."""
    return "insufficient_data" if value is None else "unknown"


def _compute_metric_status(sleep_data: dict, health_data: dict) -> dict:
    sleep_quality = sleep_data["sleep_quality"]
    awake_count = sleep_data["awake_count"]
    stress = health_data["stress"]
    met = health_data["met"]
    hrv = health_data["hrv_ms"]
    blood_oxygen = health_data["blood_oxygen_percent"]
    return {
        "sleep_quality": (
            "insufficient_data" if sleep_quality is None
            else "normal" if sleep_quality >= _SLEEP_QUALITY_NORMAL_MIN else "low"
        ),
        "sleep_duration_minutes": _status_from_range(
            sleep_data["sleep_duration_minutes"], *_SLEEP_DURATION_RANGE_MINUTES
        ),
        "sleep_start_time": _presence_status(sleep_data["sleep_start_time"]),
        "wake_up_time": _presence_status(sleep_data["wake_up_time"]),
        "awake_count": (
            "insufficient_data" if awake_count is None
            else "normal" if awake_count <= _AWAKE_COUNT_NORMAL_MAX else "high"
        ),
        # This system's sleep data model never tracks a separate REM segment (see
        # _aggregate_sleep), so this is always null and always reported as insufficient_data.
        "rem_duration_minutes": "insufficient_data",
        "light_sleep_duration_minutes": _presence_status(sleep_data["light_sleep_duration_minutes"]),
        "deep_sleep_duration_minutes": _presence_status(sleep_data["deep_sleep_duration_minutes"]),
        "heart_rate_bpm": _status_from_range(health_data["heart_rate_bpm"], *_HEART_RATE_RANGE),
        "blood_pressure": _blood_pressure_status(health_data["blood_pressure"]),
        "blood_oxygen_percent": (
            "insufficient_data" if blood_oxygen is None
            else "normal" if blood_oxygen >= _BLOOD_OXYGEN_NORMAL_MIN else "low"
        ),
        "body_temperature_celsius": _status_from_range(
            health_data["body_temperature_celsius"], *_BODY_TEMPERATURE_RANGE
        ),
        "respiratory_breaths_per_min": _status_from_range(
            health_data["respiratory_breaths_per_min"], *_RESPIRATORY_RANGE
        ),
        # General consumer-wearable convention (see _HRV_NORMAL_MIN): only a low reading is
        # flagged, since higher HRV isn't a concern.
        "hrv_ms": (
            "insufficient_data" if hrv is None
            else "low" if hrv < _HRV_NORMAL_MIN else "normal"
        ),
        "stress": (
            "insufficient_data" if stress is None
            else "high" if stress >= _STRESS_HIGH_MIN else "normal"
        ),
        "met": (
            "insufficient_data" if met is None
            else "low" if met < _MET_RANGE[0]
            else "high" if met > _MET_RANGE[1]
            else "normal"
        ),
    }


def _abnormal_metrics(metric_status: dict) -> list[str]:
    """Metrics the system itself flagged as low/high — the only ones data_summary_prompt.md's
    主要發現 (key findings) section is allowed to draw from, so the AI can't pad it with normal
    metrics or invent its own notion of "notable"."""
    return [metric for metric, status in metric_status.items() if status in ("low", "high")]


def _missing_metrics(sleep_data: dict, health_data: dict) -> list[str]:
    missing = [key for key, value in sleep_data.items() if value is None]
    missing += [key for key, value in health_data.items() if key != "blood_pressure" and value is None]
    bp = health_data["blood_pressure"]
    if bp.get("systolic_mmhg") is None and bp.get("diastolic_mmhg") is None:
        missing.append("blood_pressure")
    return missing


def _health_row_has_data(row: HealthRecord) -> bool:
    if any(_health_field(row, key, sub_key) is not None for key, sub_key in _HEALTH_METRIC_FIELDS.values()):
        return True
    return _health_field(row, "bloodPressure", "systolic") is not None or (
        _health_field(row, "bloodPressure", "diastolic") is not None
    )


def _sleep_row_has_data(row: SleepRecord) -> bool:
    return any(v is not None for v in (row.sleep_summary or {}).values())


def _period_has_data(sleep_rows: list[SleepRecord], health_rows: list[HealthRecord]) -> bool:
    """True if ANY day in the fetched 7-day window has usable data. Deliberately not limited to
    the requested end date: a report is a 7-day trend summary, so a device that simply hasn't
    synced yet for the most recent day(s) shouldn't block generation as long as earlier days in
    the window have data."""
    return any(_sleep_row_has_data(r) for r in sleep_rows) or any(_health_row_has_data(r) for r in health_rows)


def _validate_mac_address(mac_address: str | None) -> str:
    if not mac_address or not mac_address.strip():
        raise AnalysisError(400, "macAddress 或 date 格式錯誤", code="INVALID_PARAMETER")
    return mac_address.strip()


def _validate_date(date_str: str | None) -> date:
    if not date_str:
        raise AnalysisError(400, "macAddress 或 date 格式錯誤", code="INVALID_PARAMETER")
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise AnalysisError(400, "macAddress 或 date 格式錯誤", code="INVALID_PARAMETER") from None


def _build_ai_payload(
    mac_address: str,
    report_date: str,
    start_time: datetime,
    end_time: datetime,
    sleep_data: dict,
    health_data: dict,
    metric_status: dict,
    data_quality: dict,
    has_image: bool,
) -> dict:
    return {
        "mac_address": mac_address,
        "report_date": report_date,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "sleep_data": sleep_data,
        "health_data": health_data,
        "metric_status": metric_status,
        "data_quality": data_quality,
        "has_image": has_image,
    }


def _generate_report(
    payload: dict, image_bytes: bytes | None, content_type: str | None
) -> tuple[dict, str]:
    """Uses the Responses API (not generate_json's Chat Completions call) so the returned
    response id can be saved and later passed as previousResponseId to /health_summary — that
    endpoint relies on OpenAI already having this call's macAddress + 7-day data in context
    server-side, rather than re-querying the database itself.

    When an image is attached, it rides along in this same call (see
    ai_client.generate_json_response) so it also becomes part of that stored context."""
    try:
        prompt = ai_client.with_language(_SYSTEM_PROMPT, "zh")
        result, response_id, _usage = ai_client.generate_json_response(
            prompt,
            f"Input:\n{json.dumps(payload, default=str)}",
            image_bytes=image_bytes,
            mime_type=content_type,
            max_output_tokens=DATA_SUMMARY_MAX_TOKENS,
        )
        return result, response_id
    except Exception as e:  # noqa: BLE001
        logger.exception("AI data summary generation failed")
        raise AnalysisError(502, "數據摘要生成失敗", code="SUMMARY_GENERATION_FAILED") from e


def _save_uploaded_image(db: Session, mac_address: str, image_bytes: bytes, content_type: str | None) -> str:
    pic_id = files.generate_pic_id()
    image_path = files.save_analysis_image(image_bytes, content_type, pic_id)
    db.add(AnalysisPicRecord(mac_address=mac_address, pic_id=pic_id, image_path=image_path))
    db.commit()
    return pic_id


def _source_updated_at(sleep_rows: list[SleepRecord], health_rows: list[HealthRecord]) -> datetime:
    timestamps = [r.updated_at for r in sleep_rows] + [r.updated_at for r in health_rows]
    return max(timestamps)


def get_or_generate_summary(
    db: Session,
    mac_address: str,
    date_str: str,
    image_bytes: bytes | None = None,
    content_type: str | None = None,
) -> tuple[DataSummaryRecord, bool]:
    """Returns (record, generated) where generated is False when a still-fresh saved summary
    was returned as-is, and True when a new one was just computed and (re)saved.

    An attached image always forces regeneration (bypassing the cache below), since it's new
    input the caller wants reflected in this report."""
    mac_address = _validate_mac_address(mac_address)
    end_date = _validate_date(date_str)
    # Normalized to a canonical zero-padded YYYY-MM-DD from here on, so it always matches the
    # zero-padded date strings _week_dates() generates and SleepRecord/HealthRecord store —
    # date_str itself may not be zero-padded even though _validate_date's strptime accepts it.
    date_str = end_date.isoformat()

    device = db.query(DeviceRecord).filter(DeviceRecord.mac_address == mac_address).first()
    if device is None:
        raise AnalysisError(404, "找不到指定設備", code="DEVICE_NOT_FOUND")

    start_date = end_date - timedelta(days=LOOKBACK_DAYS - 1)
    dates = _week_dates(end_date, LOOKBACK_DAYS)

    sleep_rows = (
        db.query(SleepRecord)
        .filter(SleepRecord.device_id == device.id, SleepRecord.date.in_(dates))
        .all()
    )
    health_rows = (
        db.query(HealthRecord)
        .filter(HealthRecord.device_id == device.id, HealthRecord.date.in_(dates))
        .all()
    )

    if not _period_has_data(sleep_rows, health_rows):
        raise AnalysisError(422, "近 7 天內查無有效資料，無法生成數據摘要", code="INSUFFICIENT_DATA")

    sleep_data = _aggregate_sleep(sleep_rows)
    health_data = _aggregate_health(health_rows)
    metric_status = _compute_metric_status(sleep_data, health_data)
    data_quality = {
        "sleep_sample_days": len(sleep_rows),
        "health_sample_days": len(health_rows),
        "missing_metrics": _missing_metrics(sleep_data, health_data),
        "abnormal_metrics": _abnormal_metrics(metric_status),
    }

    start_time = datetime.combine(start_date, time.min, tzinfo=REPORT_TZ)
    end_time = datetime.combine(end_date, time(23, 59, 59), tzinfo=REPORT_TZ)
    source_updated_at = _source_updated_at(sleep_rows, health_rows)

    existing = db.query(DataSummaryRecord).filter(
        DataSummaryRecord.mac_address == mac_address,
        DataSummaryRecord.report_date == date_str,
    ).first()

    if (
        image_bytes is None
        and existing is not None
        and existing.source_updated_at is not None
        and existing.source_updated_at >= source_updated_at
    ):
        return existing, False

    payload = _build_ai_payload(
        mac_address, date_str, start_time, end_time, sleep_data, health_data, metric_status, data_quality,
        has_image=bool(image_bytes),
    )
    ai_response, response_id = _generate_report(payload, image_bytes, content_type)

    pic_id = _save_uploaded_image(db, mac_address, image_bytes, content_type) if image_bytes else None

    if existing is None:
        existing = DataSummaryRecord(mac_address=mac_address, report_date=date_str)
        db.add(existing)

    existing.start_time = start_time
    existing.end_time = end_time
    existing.sleep_summary = sleep_data
    existing.health_summary = health_data
    existing.metric_status = metric_status
    existing.ai_response = ai_response
    existing.response_id = response_id
    existing.pic_id = pic_id
    existing.prompt_version = PROMPT_VERSION
    existing.source_updated_at = source_updated_at
    db.commit()
    db.refresh(existing)
    return existing, True
