import json
import os

from openai import OpenAI

from src.core.logging import logger

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.4))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", 60))

SYSTEM_PROMPT_SUFFIX = "Respond with a single JSON object only, no surrounding text."

_client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)


class AIResponseFormatError(Exception):
    """Raised when OpenAI returns content that cannot be parsed as JSON."""


def generate_json(system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
    """Calls OpenAI chat completions with a JSON response format.

    Returns (parsed_json, usage) where usage is {prompt_tokens, completion_tokens, total_tokens}.
    Raises the OpenAI SDK's own exceptions on network/timeout/rate-limit/API errors,
    and AIResponseFormatError if the response content isn't valid JSON.
    """
    completion = _client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{system_prompt}\n\n{SYSTEM_PROMPT_SUFFIX}"},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = completion.choices[0].message.content
    usage = completion.usage
    usage_dict = {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    try:
        return json.loads(content), usage_dict
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("OpenAI returned non-JSON content: %s", content)
        raise AIResponseFormatError(f"OpenAI response was not valid JSON: {e}") from e
