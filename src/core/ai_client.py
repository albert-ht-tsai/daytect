import base64
import json
import os

from openai import OpenAI

from src.core.logging import logger

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.4))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", 60))

SYSTEM_PROMPT_SUFFIX = "Respond with a single JSON object only, no surrounding text."

LANGUAGE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "zh": "請使用繁體中文回覆。",
}

_client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)


def with_language(system_prompt: str, language: str) -> str:
    """Appends a language directive to a system prompt; unrecognized codes fall back to English."""
    instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])
    return f"{system_prompt}\n- {instruction}"


class AIResponseFormatError(Exception):
    """Raised when OpenAI returns content that cannot be parsed as JSON."""


def _parse_completion(completion) -> tuple[dict, dict]:
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
    return _parse_completion(completion)


def generate_json_with_image(
    system_prompt: str, user_prompt: str, image_bytes: bytes, mime_type: str
) -> tuple[dict, dict]:
    """Same as generate_json, but attaches an image to the user message for vision analysis."""
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    completion = _client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{system_prompt}\n\n{SYSTEM_PROMPT_SUFFIX}"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}},
                ],
            },
        ],
    )
    return _parse_completion(completion)
