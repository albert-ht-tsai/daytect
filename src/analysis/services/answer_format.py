import json

SUMMARY_KEYS = ("healthSummary", "fatigueSummary", "recoverySummary")


def dump_summary(summary: dict) -> str:
    """Encodes the 3-key structured chat reply (healthSummary/fatigueSummary/recoverySummary)
    for storage in a Text column."""
    return json.dumps({key: summary.get(key, "") for key in SUMMARY_KEYS}, ensure_ascii=False)


def load_stored_summary(raw: str | None) -> dict:
    """Parses an AnalysisRecord.system_answer column back into the 3-key structured summary.
    Tolerates rows written before this format existed (a bullet-point list or plain string, from
    the old /request reply shape), folding their content into healthSummary so older session
    history doesn't crash the reader."""
    empty = {key: "" for key in SUMMARY_KEYS}
    if not raw:
        return empty
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {**empty, "healthSummary": raw}
    if isinstance(parsed, dict):
        return {key: str(parsed.get(key) or "") for key in SUMMARY_KEYS}
    if isinstance(parsed, list):
        return {**empty, "healthSummary": "; ".join(str(item) for item in parsed)}
    return {**empty, "healthSummary": str(parsed)}


def as_bullet_list(message) -> list[str]:
    """Normalizes an AI "message" field (either a bare string or a list) into a list of
    non-empty bullet strings, so every caller storing/consuming AnalysisSummaryRecord.summary
    (the compacted conversation digest) gets a consistent shape regardless of which prompt
    schema produced it."""
    if isinstance(message, list):
        return [str(item) for item in message if str(item).strip()]
    if message:
        return [str(message)]
    return []


def dump_answer(bullets: list[str]) -> str:
    """Encodes a bullet list (AnalysisSummaryRecord.summary) for storage in a Text column."""
    return json.dumps(bullets, ensure_ascii=False)


def load_stored_answer(raw: str | None) -> list[str]:
    """Parses an AnalysisSummaryRecord.summary column back into a bullet list. Tolerates rows
    written before the bullet-list format existed (a plain string), wrapping them into a
    one-item list."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return as_bullet_list(parsed)
