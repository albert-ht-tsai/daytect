import json

MODEL_CONTEXT_LIMIT = 128_000
RESERVED_OUTPUT_TOKENS = 4_000
RESERVED_SYSTEM_PROMPT_TOKENS = 2_000
RESERVED_FINAL_INSTRUCTION_TOKENS = 2_000
SAFETY_MARGIN_TOKENS = 10_000
MAX_BATCH_INPUT_TOKENS = 30_000

_CHARS_PER_TOKEN = 4


def estimate_tokens(obj) -> int:
    text = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return max(1, len(text) // _CHARS_PER_TOKEN)


def split_into_batches(metrics: dict) -> list[dict]:
    """Greedily groups metric entries into batches whose estimated token size
    stays under MAX_BATCH_INPUT_TOKENS. A single oversized metric still gets
    its own batch rather than being dropped."""
    batches: list[dict] = []
    current_batch: dict = {}
    current_tokens = 0

    for key, value in metrics.items():
        item_tokens = estimate_tokens({key: value})
        if current_batch and current_tokens + item_tokens > MAX_BATCH_INPUT_TOKENS:
            batches.append(current_batch)
            current_batch = {}
            current_tokens = 0
        current_batch[key] = value
        current_tokens += item_tokens

    if current_batch:
        batches.append(current_batch)

    return batches or [{}]
