import json

from sqlalchemy.orm import Session

from src.analysis.models.analysis_model import AnalysisRecord
from src.analysis.models.analysis_summary_model import AnalysisSummaryRecord
from src.analysis.services.answer_format import as_bullet_list, dump_answer, load_stored_answer
from src.analysis.services.errors import AnalysisError
from src.core import ai_client
from src.core.logging import logger

COMPACT_TURN_COUNT = 10
COMPACT_MAX_TOKENS = 400

_COMPACT_SYSTEM_PROMPT = """You are compacting a health/fatigue chat conversation history into a short
key-point digest for future reference. You will receive up to the last 10 turns of the conversation, oldest
first, each with the user's question ("userQuestion") and the assistant's bullet-point reply from that turn
("reply").

Combine them into a single, deduplicated set of key points capturing the user's recurring questions/concerns
and the most important, still-relevant findings about their health metrics and fatigue status. If a later
turn updates or contradicts an earlier one, keep only the later, more current point.

Return a JSON object: {"message": ["<string>", ...]}
Rules:
- At most 8 bullet points, each concise and self-contained (understandable without the original turns).
- Do not diagnose disease or recommend medication or medical treatment.
- Do not invent findings not present in the source turns.
- Use clear, simple language.
- Return JSON only."""


def _turn_payload(record: AnalysisRecord) -> dict:
    return {
        "userQuestion": record.user_question,
        "reply": load_stored_answer(record.system_answer),
        "recordDatetime": record.record_datetime.isoformat() if record.record_datetime else None,
    }


def _generate_compact_summary(turns: list[dict], language: str) -> list[str]:
    prompt = ai_client.with_language(_COMPACT_SYSTEM_PROMPT, language)
    try:
        result, _usage = ai_client.generate_json(
            prompt, f"Input:\n{json.dumps({'turns': turns}, default=str)}", max_tokens=COMPACT_MAX_TOKENS
        )
        return as_bullet_list(result.get("message"))
    except Exception as e:  # noqa: BLE001
        logger.exception("AI summary compaction failed")
        raise AnalysisError(502, f"Unable to compact summary: {e}") from e


def compact_summary(
    db: Session, mac_address: str, session_id: str, language: str = "en"
) -> tuple[list[str], int]:
    if not mac_address or not mac_address.strip():
        raise AnalysisError(400, "macAddress 不可為空")
    if not session_id or not session_id.strip():
        raise AnalysisError(400, "session_id 不可為空")

    records = (
        db.query(AnalysisRecord)
        .filter(AnalysisRecord.mac_address == mac_address, AnalysisRecord.session_id == session_id)
        .order_by(AnalysisRecord.record_datetime.desc())
        .limit(COMPACT_TURN_COUNT)
        .all()
    )
    if not records:
        raise AnalysisError(404, "找不到對應的對話紀錄")

    records.reverse()  # oldest -> newest, so the AI reads the conversation in order
    turns = [_turn_payload(r) for r in records]
    summary = _generate_compact_summary(turns, language)

    existing = (
        db.query(AnalysisSummaryRecord)
        .filter(
            AnalysisSummaryRecord.mac_address == mac_address,
            AnalysisSummaryRecord.session_id == session_id,
        )
        .first()
    )
    if existing is None:
        existing = AnalysisSummaryRecord(mac_address=mac_address, session_id=session_id)
        db.add(existing)

    existing.summary = dump_answer(summary)
    existing.source_count = len(records)
    existing.start_record_datetime = records[0].record_datetime
    existing.end_record_datetime = records[-1].record_datetime
    db.commit()
    db.refresh(existing)

    return summary, existing.source_count


def get_compact_summary(db: Session, mac_address: str, session_id: str) -> tuple[list[str], int] | None:
    record = (
        db.query(AnalysisSummaryRecord)
        .filter(
            AnalysisSummaryRecord.mac_address == mac_address,
            AnalysisSummaryRecord.session_id == session_id,
        )
        .first()
    )
    if record is None:
        return None
    return load_stored_answer(record.summary), record.source_count
