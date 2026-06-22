import json
import os

from src.core.logging import logger

AI_PRIMARY_PROVIDER = os.getenv("AI_PRIMARY_PROVIDER", "openai")
AI_FAST_PROVIDER = os.getenv("AI_FAST_PROVIDER", "groq")
AI_FALLBACK_PROVIDER = os.getenv("AI_FALLBACK_PROVIDER", "groq")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", 0.4))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", 1024))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", 30))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL") or None
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", 0.4))
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", 1024))
GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", 30))

SYSTEM_PROMPT = (
    "You are Daytect AI, a health-data analysis assistant. "
    "Respond with a single JSON object only, no surrounding text, matching exactly the schema described in the prompt."
)


def _call_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS)
    completion = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        max_tokens=OPENAI_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return completion.choices[0].message.content


def _call_groq(prompt: str) -> str:
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL, timeout=GROQ_TIMEOUT_SECONDS)
    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=GROQ_TEMPERATURE,
        max_tokens=GROQ_MAX_TOKENS,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return completion.choices[0].message.content


_PROVIDER_CALLERS = {
    "openai": _call_openai,
    "groq": _call_groq,
}


def generate_json(prompt: str, provider: str) -> dict:
    caller = _PROVIDER_CALLERS.get(provider)
    if caller is None:
        raise ValueError(f"Unknown AI provider: {provider}")
    raw = caller(prompt)
    return json.loads(raw)


def generate_daily(prompt: str) -> dict:
    return generate_json(prompt, AI_FAST_PROVIDER)


def generate_periodic(prompt: str) -> dict:
    try:
        return generate_json(prompt, AI_PRIMARY_PROVIDER)
    except Exception as e:
        logger.warning("AI primary provider (%s) failed: %s — falling back to %s", AI_PRIMARY_PROVIDER, e, AI_FALLBACK_PROVIDER)
        return generate_json(prompt, AI_FALLBACK_PROVIDER)
