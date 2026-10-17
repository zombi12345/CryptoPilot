import logging
import json
from openai import AsyncOpenAI
from config import N1N_API_KEY, N1N_BASE_URL, N1N_MODEL

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=N1N_API_KEY,
            base_url=N1N_BASE_URL,
        )
    return _client


async def chat(messages, model=None, temperature=0.3, max_tokens=1500):
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model or N1N_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"AI error: {e}")
        return ""


async def chat_json(messages, model=None, max_tokens=1500):
    raw = await chat(messages, model=model, max_tokens=max_tokens)
    if not raw:
        return {}
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception as e:
        logger.warning(f"JSON parse error: {e}")
    return {}