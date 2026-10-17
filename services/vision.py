import base64
import logging
from services.ai_client import chat_json

logger = logging.getLogger(__name__)

VISION_PROMPT = """Ты - аналитик графиков. На фото - скриншот графика цены криптовалюты.

Задача: распознать что видно и дать предварительный прогноз.

Ответ строго в JSON:
{
  "enough_data": true или false,
  "ticker": "BTC/USDT или null",
  "timeframe": "1h или null",
  "trend": "up / down / sideways / unknown",
  "description": "краткое описание что видно",
  "questions": ["вопрос1", "вопрос2"] или [],
  "forecast": {
    "direction": "up / down / sideways",
    "confidence": 0-100,
    "reasoning": "обоснование",
    "risks": "риски"
  } или null
}

Если не хватает данных (не видно тикер, таймфрейм, индикаторы) - enough_data=false, задай до 3 вопросов в questions, forecast=null.
Если данных достаточно - enough_data=true, forecast с прогнозом.
"""


async def analyze_photo(image_bytes: bytes, clarification: str = "") -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    user_text = "Проанализируй график."
    if clarification:
        user_text = f"Дополнительная информация: {clarification}\n\nПроанализируй график и дай финальный прогноз."
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT + "\n\n" + user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
    ]
    result = await chat_json(messages, max_tokens=1500)
    if not result:
        return {"error": "AI не ответил"}
    return result


def format_forecast(result: dict) -> str:
    if result.get("error"):
        return f"Ошибка: {result['error']}"

    if not result.get("enough_data", True):
        questions = result.get("questions", [])
        text = "Мне нужно уточнить:\n\n"
        for i, q in enumerate(questions[:3], 1):
            text += f"{i}. {q}\n"
        text += "\nНапиши ответ одним сообщением."
        return text

    f = result.get("forecast") or {}
    direction_map = {"up": "Рост", "down": "Падение", "sideways": "Боковик"}
    direction = direction_map.get(f.get("direction"), "неизвестно")

    return (
        f"Анализ графика\n\n"
        f"Тикер: {result.get('ticker') or 'не распознан'}\n"
        f"Таймфрейм: {result.get('timeframe') or 'не распознан'}\n"
        f"Тренд: {result.get('trend', 'unknown')}\n\n"
        f"Описание:\n{result.get('description', '-')}\n\n"
        f"Прогноз: {direction}\n"
        f"Уверенность: {f.get('confidence', 0)}%\n"
        f"Обоснование: {f.get('reasoning', '-')}\n"
        f"Риски: {f.get('risks', '-')}\n\n"
        f"Не является инвестиционной рекомендацией."
    )