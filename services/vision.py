import base64
import logging
from services.ai_client import chat, chat_json
# RAG отключен для деплоя
# from services.rag import get_book_context, list_books

logger = logging.getLogger(__name__)

VISION_PROMPT = """Ты - профессиональный технический аналитик. На фото - скриншот графика цены криптовалюты.

Задача: ДЕТАЛЬНО распознать график и дать обоснованный прогноз.

Ответ строго в JSON:
{
  "enough_data": true или false,
  "ticker": "BTC/USDT или null",
  "timeframe": "1h или null",
  "current_price": "число или null",
  "trend": "up / down / sideways / unknown",
  "trend_reason": "почему такой тренд",
  "key_levels": {
    "support": ["уровень1"],
    "resistance": ["уровень1"]
  },
  "patterns": "какие паттерны видно",
  "candles": "что видно по свечам",
  "indicators": "какие индикаторы и значения",
  "volume": "что видно по объёмам",
  "description": "полное описание графика в 5-10 предложениях",
  "questions": ["вопрос1"] или [],
  "forecast": {
    "direction": "up / down / sideways",
    "confidence": 0-100,
    "reasoning": ["пункт 1", "пункт 2", "пункт 3", "пункт 4", "пункт 5"],
    "scenarios": {
      "bullish": "что для роста",
      "bearish": "что для падения"
    },
    "targets": {
      "up": "цель роста",
      "down": "цель падения"
    },
    "invalidation": "при каком уровне отмена",
    "risks": "конкретные риски"
  } или null
}

ТРЕБОВАНИЯ:
- reasoning - МАССИВ строк, минимум 5 пунктов.
- НЕ пиши общих фраз.
- Если видишь индикаторы - назови значения.
- Если видишь уровни - назови числа.
"""


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, dict):
        return " ".join(f"{k}={v}" for k, v in val.items())
    if isinstance(val, list):
        return " ".join(_to_str(x) for x in val)
    return str(val)


async def analyze_photo(image_bytes: bytes, clarification: str = "", user_id: int = None) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    user_text = "Детально проанализируй график. Не пиши общих фраз."
    if clarification:
        user_text = f"Дополнительно: {clarification}\n\nПроанализируй график детально."
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_PROMPT + "\n\n" + user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
    ]
    result = await chat_json(messages, max_tokens=2500)
    if not result:
        return {"error": "AI не ответил"}

    # RAG-обогащение временно отключено (нет chromadb на сервере)
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

    parts = ["АНАЛИЗ ГРАФИКА\n"]
    parts.append(f"Тикер: {result.get('ticker') or 'не распознан'}")
    parts.append(f"Таймфрейм: {result.get('timeframe') or 'не распознан'}")
    if result.get("current_price"):
        parts.append(f"Цена: {result['current_price']}")
    parts.append(f"Тренд: {result.get('trend', 'unknown')}")

    levels = result.get("key_levels") or {}
    if levels.get("support") or levels.get("resistance"):
        parts.append("")
        parts.append("Уровни:")
        if levels.get("support"):
            parts.append(f"  Поддержка: {', '.join(str(x) for x in levels['support'])}")
        if levels.get("resistance"):
            parts.append(f"  Сопротивление: {', '.join(str(x) for x in levels['resistance'])}")

    if result.get("patterns"):
        parts.append(f"Паттерны: {result['patterns']}")
    if result.get("indicators"):
        parts.append(f"Индикаторы: {result['indicators']}")

    parts.append("")
    parts.append(f"ПРОГНОЗ: {direction}")
    parts.append(f"Уверенность: {f.get('confidence', 0)}%")

    reasoning = f.get("reasoning")
    if reasoning:
        parts.append("")
        parts.append("Кратко:")
        if isinstance(reasoning, list):
            for i, r in enumerate(reasoning[:2], 1):
                parts.append(f"  {i}. {r}")
        else:
            parts.append(f"  {reasoning}")

    parts.append("")
    parts.append("Не является инвестиционной рекомендацией.")
    return "\n".join(parts)


def format_details(result: dict) -> str:
    if result.get("error"):
        return f"Ошибка: {result['error']}"

    f = result.get("forecast") or {}
    direction_map = {"up": "Рост", "down": "Падение", "sideways": "Боковик"}
    direction = direction_map.get(f.get("direction"), "неизвестно")

    parts = ["ПОДРОБНЫЙ РАЗБОР\n"]
    parts.append("ЧТО ВИДНО:")
    parts.append(f"  Тикер: {result.get('ticker') or '?'}")
    parts.append(f"  Таймфрейм: {result.get('timeframe') or '?'}")
    if result.get("current_price"):
        parts.append(f"  Цена: {result['current_price']}")
    parts.append(f"  Тренд: {result.get('trend', 'unknown')}")
    if result.get("trend_reason"):
        parts.append(f"  Причина: {result['trend_reason']}")

    levels = result.get("key_levels") or {}
    if levels.get("support") or levels.get("resistance"):
        parts.append("")
        parts.append("УРОВНИ:")
        if levels.get("support"):
            parts.append(f"  Поддержка: {', '.join(str(x) for x in levels['support'])}")
        if levels.get("resistance"):
            parts.append(f"  Сопротивление: {', '.join(str(x) for x in levels['resistance'])}")

    if result.get("patterns"):
        parts.append("")
        parts.append(f"ПАТТЕРНЫ: {result['patterns']}")
    if result.get("candles"):
        parts.append(f"СВЕЧИ: {result['candles']}")
    if result.get("indicators"):
        parts.append(f"ИНДИКАТОРЫ: {result['indicators']}")
    if result.get("volume"):
        parts.append(f"ОБЪЁМЫ: {result['volume']}")
    if result.get("description"):
        parts.append("")
        parts.append("ОПИСАНИЕ:")
        parts.append(result["description"])

    parts.append("")
    parts.append(f"ПРОГНОЗ: {direction} (уверенность {f.get('confidence', 0)}%)")

    reasoning = f.get("reasoning")
    if reasoning:
        parts.append("")
        parts.append("ПОЧЕМУ ТАКОЙ ВЫБОР:")
        if isinstance(reasoning, list):
            for i, r in enumerate(reasoning, 1):
                parts.append(f"  {i}. {r}")
        else:
            parts.append(f"  {reasoning}")

    parts.append("")
    parts.append("Не является инвестиционной рекомендацией.")
    return "\n".join(parts)