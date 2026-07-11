import json


def as_bullet_list(message) -> list[str]:
    """Normalizes an AI "message" field (either a bare string or a list) into a list of
    non-empty bullet strings, so every caller storing/consuming AnalysisRecord.system_answer
    gets a consistent shape regardless of which prompt schema produced it."""
    if isinstance(message, list):
        return [str(item) for item in message if str(item).strip()]
    if message:
        return [str(message)]
    return []


def dump_answer(bullets: list[str]) -> str:
    """Encodes a bullet list for storage in a Text column."""
    return json.dumps(bullets, ensure_ascii=False)


def load_stored_answer(raw: str | None) -> list[str]:
    """Parses an AnalysisRecord.system_answer column back into a bullet list. Tolerates rows
    written before the bullet-list format existed (a plain string), wrapping them into a
    one-item list."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return as_bullet_list(parsed)
