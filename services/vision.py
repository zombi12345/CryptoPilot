import base64
import logging
from services.ai_client import chat_json
from services.rag import get_book_context, list_books
from services.summarizer import format_all_summaries
from database import get_all_book_summaries

logger = logging.getLogger(__name__)

VISION_PROMPT = """Ты - профессиональный технический аналитик. На фото - скриншот графика цены криптовалюты.

Ответ строго в JSON:
{
  "enough_data": true или false,
  "ticker": "BTC/USDT или null",
  "timeframe": "1h или null",
  "current_price": "число или null",
  "trend": "up / down / sideways / unknown",
  "trend_reason": "почему такой тренд",
  "key_levels": {"support": ["уровень1"], "resistance": ["уровень1"]},
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
    "scenarios": {"bullish": "что для роста", "bearish": "что для падения"},
    "targets": {"up": "цель роста", "down": "цель падения"},
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

    if result.get("enough_data") and user_id:
        query_parts = [
            _to_str(result.get("ticker")),
            _to_str(result.get("trend")),
            _to_str(result.get("patterns")),
            _to_str(result.get("indicators")),
            _to_str(result.get("candles")),
            _to_str(result.get("volume")),
            _to_str(result.get("description")),
        ]
        query = " ".join(p for p in query_parts if p)
        books = list_books(user_id)
        summaries = await get_all_book_summaries(user_id)
        summaries_text = format_all_summaries(summaries) if summaries else ""
        chunks_ctx = get_book_context(user_id, query, top_k=20) if query.strip() else ""

        if summaries_text or chunks_ctx:
            result["book_context_used"] = True
            result["book_sources"] = list(summaries.keys()) if summaries else []
            result["books_available"] = [b["filename"] for b in books]

            system_prompt = (
                "Ты - технический аналитик. У тебя есть:\n"
                "1. Данные с графика.\n"
                "2. КОНСПЕКТЫ ВСЕХ книг.\n"
                "3. Выдержки из книг по ситуации.\n\n"
                "ГЛАВНОЕ ПРАВИЛО: используй МАКСИМУМ книг. "
                "Если правило в нескольких книгах - упомяни все. "
                "Если противоречат - отметь.\n\n"
                "ТРЕБОВАНИЯ:\n"
                "1. reasoning - МАССИВ из 5-8 пунктов, каждый со ссылкой [книга].\n"
                "2. book_rules_applied - все правила из книг.\n"
                "3. books_used - список ВСЕХ книг, использованных.\n"
                "4. Не пиши общих фраз.\n\n"
                "Ответ в JSON:\n"
                "{\n"
                "  \"forecast\": {\n"
                "    \"direction\": \"up/down/sideways\",\n"
                "    \"confidence\": 0-100,\n"
                "    \"reasoning\": [\"пункт 1 [книга]\", \"пункт 2 [книга]\"],\n"
                "    \"book_rules_applied\": [\"правило 1 [книга]\"],\n"
                "    \"books_used\": [\"книга1.pdf\", \"книга2.pdf\"],\n"
                "    \"conflicts\": \"если противоречат\",\n"
                "    \"scenarios\": {\"bullish\": \"...\", \"bearish\": \"...\"},\n"
                "    \"targets\": {\"up\": \"...\", \"down\": \"...\"},\n"
                "    \"invalidation\": \"...\",\n"
                "    \"risks\": \"...\"\n"
                "  }\n"
                "}"
            )
            user_msg = (
                f"ГРАФИК:\n"
                f"Тикер: {result.get('ticker')}\n"
                f"Таймфрейм: {result.get('timeframe')}\n"
                f"Цена: {result.get('current_price')}\n"
                f"Тренд: {result.get('trend')} ({result.get('trend_reason')})\n"
                f"Уровни: {result.get('key_levels')}\n"
                f"Паттерны: {result.get('patterns')}\n"
                f"Свечи: {result.get('candles')}\n"
                f"Индикаторы: {result.get('indicators')}\n"
                f"Объёмы: {result.get('volume')}\n\n"
                f"ДОСТУПНЫЕ КНИГИ: {', '.join(b['filename'] for b in books)}\n\n"
                f"КОНСПЕКТЫ ВСЕХ КНИГ:\n{summaries_text}\n\n"
                f"ВЫДЕРЖКИ:\n{chunks_ctx}\n\n"
                f"Дай прогноз. Используй МАКСИМУМ книг."
            )
            enrich_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]
            enriched = await chat_json(enrich_messages, max_tokens=2500)
            if enriched and enriched.get("forecast"):
                result["forecast"] = enriched["forecast"]
                result["enriched_by_books"] = True
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

    books_used = f.get("books_used")
    if books_used:
        parts.append("")
        parts.append(f"Книги: {', '.join(books_used)}")

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

    book_rules = f.get("book_rules_applied")
    if book_rules:
        parts.append("")
        parts.append("ПРАВИЛА ИЗ КНИГ:")
        for r in book_rules:
            parts.append(f"  - {r}")

    books_used = f.get("books_used")
    if books_used:
        parts.append("")
        parts.append(f"ИСПОЛЬЗОВАНЫ: {', '.join(books_used)}")

    if f.get("conflicts"):
        parts.append("")
        parts.append(f"ПРОТИВОРЕЧИЯ: {f['conflicts']}")

    scenarios = f.get("scenarios") or {}
    if scenarios:
        parts.append("")
        parts.append("СЦЕНАРИИ:")
        if scenarios.get("bullish"):
            parts.append(f"  Вверх: {scenarios['bullish']}")
        if scenarios.get("bearish"):
            parts.append(f"  Вниз: {scenarios['bearish']}")

    targets = f.get("targets") or {}
    if targets:
        parts.append("")
        parts.append("ЦЕЛИ:")
        if targets.get("up"):
            parts.append(f"  Вверх: {targets['up']}")
        if targets.get("down"):
            parts.append(f"  Вниз: {targets['down']}")

    if f.get("invalidation"):
        parts.append("")
        parts.append(f"ОТМЕНА: {f['invalidation']}")

    if f.get("risks"):
        parts.append("")
        parts.append(f"РИСКИ: {f['risks']}")

    parts.append("")
    parts.append("Не является инвестиционной рекомендацией.")
    return "\n".join(parts)
