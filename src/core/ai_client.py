import base64
import json
import os

from openai import OpenAI

from src.core.logging import logger

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.4))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", 60))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", 1000))
OPENAI_MAX_INPUT_TOKENS = int(os.getenv("OPENAI_MAX_INPUT_TOKENS", 16000))

# No tiktoken dependency in this project; ~1 token per 2 characters is a conservative,
# dependency-free ratio that stays safe for both English and CJK mixed text.
_CHARS_PER_TOKEN = 2

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


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN + 1


def _cap_user_prompt(system_prompt: str, user_prompt: str) -> str:
    """Truncates the user prompt so system+user together stay within OPENAI_MAX_INPUT_TOKENS.

    Only the variable-length user payload is truncated (the fixed system instructions never
    are), since the user side is what can grow unbounded (long chat messages, large data dumps).
    """
    budget_tokens = max(OPENAI_MAX_INPUT_TOKENS - _estimate_tokens(system_prompt), 0)
    max_chars = budget_tokens * _CHARS_PER_TOKEN
    if len(user_prompt) <= max_chars:
        return user_prompt
    logger.warning(
        "Truncating oversized user prompt from %d to ~%d chars to respect OPENAI_MAX_INPUT_TOKENS",
        len(user_prompt), max_chars,
    )
    return user_prompt[:max_chars] + "\n...[truncated]"


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


def generate_json(system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> tuple[dict, dict]:
    """Calls OpenAI chat completions with a JSON response format.

    Returns (parsed_json, usage) where usage is {prompt_tokens, completion_tokens, total_tokens}.
    Raises the OpenAI SDK's own exceptions on network/timeout/rate-limit/API errors,
    and AIResponseFormatError if the response content isn't valid JSON.

    max_tokens overrides OPENAI_MAX_TOKENS for callers that need a tighter reply-length
    cap (e.g. a chat-style endpoint), without lowering the shared default for everyone.
    """
    user_prompt = _cap_user_prompt(system_prompt, user_prompt)
    completion = _client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        max_tokens=max_tokens or OPENAI_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{system_prompt}\n\n{SYSTEM_PROMPT_SUFFIX}"},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _parse_completion(completion)


def generate_json_response(
    instructions: str,
    input_text: str,
    previous_response_id: str | None = None,
    max_output_tokens: int | None = None,
    image_bytes: bytes | None = None,
    mime_type: str | None = None,
) -> tuple[dict, str, dict]:
    """Like generate_json, but uses the Responses API so a multi-turn caller can pass
    previous_response_id to resume a conversation OpenAI already has stored server-side,
    instead of replaying the full conversation history into the prompt on every call
    (see analysis_service.py, the only caller of this function today).

    When image_bytes is given, it's attached as an input_image content block alongside
    input_text on this turn, so it becomes part of the stored conversation the same way
    previous_response_id resumes it — unlike generate_json_with_image, which is a one-shot
    Chat Completions call with no memory of prior turns.

    Returns (parsed_json, response_id, usage) where usage is
    {prompt_tokens, completion_tokens, total_tokens} (renamed to match generate_json's shape;
    the Responses API itself calls these input_tokens/output_tokens/total_tokens).
    """
    # json_object mode requires the literal word "json" to appear in the input, not just the
    # instructions (verified against the live API — omitting this raises a 400).
    input_text = _cap_user_prompt(instructions, f"{input_text}\n\n(Respond with a JSON object.)")
    if image_bytes:
        b64_image = base64.b64encode(image_bytes).decode("ascii")
        input_payload = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": input_text},
                    {
                        "type": "input_image",
                        "image_url": f"data:{mime_type or 'image/jpeg'};base64,{b64_image}",
                    },
                ],
            }
        ]
    else:
        input_payload = input_text
    response = _client.responses.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        max_output_tokens=max_output_tokens or OPENAI_MAX_TOKENS,
        instructions=f"{instructions}\n\n{SYSTEM_PROMPT_SUFFIX}",
        input=input_payload,
        text={"format": {"type": "json_object"}},
        previous_response_id=previous_response_id,
        store=True,
    )
    usage = response.usage
    usage_dict = {
        "prompt_tokens": getattr(usage, "input_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "output_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }
    try:
        return json.loads(response.output_text), response.id, usage_dict
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("OpenAI returned non-JSON content: %s", response.output_text)
        raise AIResponseFormatError(f"OpenAI response was not valid JSON: {e}") from e


def generate_json_with_image(
    system_prompt: str, user_prompt: str, image_bytes: bytes, mime_type: str
) -> tuple[dict, dict]:
    """Same as generate_json, but attaches an image to the user message for vision analysis."""
    user_prompt = _cap_user_prompt(system_prompt, user_prompt)
    b64_image = base64.b64encode(image_bytes).decode("ascii")
    completion = _client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
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
