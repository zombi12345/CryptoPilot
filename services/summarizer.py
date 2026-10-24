import logging
from services.ai_client import chat_json
from services.rag import split_into_chapters

logger = logging.getLogger(__name__)

CHAPTER_PROMPT = """Ты - аналитик книги по трейдингу. Тебе даны несколько фрагментов книги.

Ответ в JSON:
{
  "chapters": [
    {"chapter_title": "название", "main_ideas": ["идея 1"], "rules": ["правило 1"], "patterns": ["паттерн 1"], "quotes": ["цитата 1"], "summary": "2-3 предложения"}
  ]
}

ТРЕБОВАНИЯ:
- По одному объекту на каждый фрагмент
- main_ideas: 2-4 идеи
- rules: конкретные правила трейдинга (может быть пустым)
- patterns: упомянутые паттерны (может быть пустым)
- Только конкретика
"""

BOOK_PROMPT = """Ты - аналитик книги по трейдингу. Тебе даны конспекты всех глав.

Ответ в JSON:
{
  "title": "название книги",
  "author": "автор",
  "core_philosophy": "главная идея в 3-5 предложениях",
  "key_concepts": ["концепция 1"],
  "all_rules": ["правило 1"],
  "all_patterns": ["паттерн 1"],
  "indicators_used": ["индикатор 1"],
  "entry_conditions": ["условие входа 1"],
  "exit_conditions": ["условие выхода 1"],
  "risk_management": ["правило риска 1"],
  "best_for": "какие таймфреймы/активы",
  "chapters_summary": "2-3 предложения"
}

ТРЕБОВАНИЯ:
- all_rules: до 20 самых важных правил
- entry_conditions: до 10
- exit_conditions: до 10
- risk_management: до 10
- key_concepts: 5-15
- Только конкретика
"""

BATCH_SIZE = 5
CHAPTER_CHUNK = 20000
MAX_CHAPTERS = 150


async def summarize_batch(batch: list, start_idx: int) -> list:
    parts = []
    for i, ch in enumerate(batch, 1):
        parts.append(f"=== Фрагмент {start_idx + i - 1} ===\n{ch[:CHAPTER_CHUNK]}")
    text = "\n\n".join(parts)

    messages = [
        {"role": "system", "content": CHAPTER_PROMPT},
        {"role": "user", "content": f"Фрагменты книги:\n\n{text}\n\nСделай конспект каждого фрагмента."},
    ]
    result = await chat_json(messages, max_tokens=2500)
    if not result or not result.get("chapters"):
        return [{
            "chapter_title": f"Фрагмент {start_idx + i}",
            "main_ideas": [],
            "rules": [],
            "patterns": [],
            "quotes": [],
            "summary": ch[:200],
        } for i, ch in enumerate(batch)]

    out = []
    chapters = result["chapters"]
    for i, ch in enumerate(batch):
        if i < len(chapters):
            c = chapters[i]
            c.setdefault("main_ideas", [])
            c.setdefault("rules", [])
            c.setdefault("patterns", [])
            c.setdefault("quotes", [])
            c.setdefault("summary", "")
            out.append(c)
        else:
            out.append({
                "chapter_title": f"Фрагмент {start_idx + i}",
                "main_ideas": [],
                "rules": [],
                "patterns": [],
                "quotes": [],
                "summary": ch[:200],
            })
    return out


async def summarize_book(user_id: int, filename: str, full_text: str) -> dict:
    chapters = split_into_chapters(full_text)
    logger.info(f"Книга {filename}: {len(chapters)} фрагментов")

    if not chapters:
        return {"error": "Не удалось разбить на главы"}

    if len(chapters) > MAX_CHAPTERS:
        logger.info(f"Слишком много фрагментов ({len(chapters)}), берём первые {MAX_CHAPTERS}")
        step = len(chapters) // MAX_CHAPTERS
        chapters = chapters[::step][:MAX_CHAPTERS]
        logger.info(f"После прореживания: {len(chapters)}")

    chapter_summaries = []
    total_batches = (len(chapters) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(chapters), BATCH_SIZE):
        batch = chapters[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info(f"  Батч {batch_num}/{total_batches} (фрагменты {i+1}-{min(i+BATCH_SIZE, len(chapters))})")
        s = await summarize_batch(batch, i + 1)
        chapter_summaries.extend(s)

    logger.info(f"  Все батчи готовы, собираю общий конспект")
    all_chapters_text = ""
    for i, s in enumerate(chapter_summaries, 1):
        all_chapters_text += f"\n=== Глава {i} ===\n"
        all_chapters_text += f"Идеи: {', '.join(s.get('main_ideas', []))}\n"
        all_chapters_text += f"Правила: {', '.join(s.get('rules', []))}\n"
        all_chapters_text += f"Паттерны: {', '.join(s.get('patterns', []))}\n"
        all_chapters_text += f"Сводка: {s.get('summary', '')}\n"

    messages = [
        {"role": "system", "content": BOOK_PROMPT},
        {"role": "user", "content": f"Книга: {filename}\n\n{all_chapters_text[:50000]}"},
    ]
    book_summary = await chat_json(messages, max_tokens=3000)
    if not book_summary:
        book_summary = {"error": "Не удалось суммаризировать"}

    book_summary["chapters_count"] = len(chapters)
    book_summary["chapters_summaries"] = chapter_summaries
    return book_summary


def format_book_summary(summary: dict) -> str:
    if summary.get("error"):
        return f"Ошибка: {summary['error']}"

    parts = ["КОНСПЕКТ КНИГИ\n"]
    if summary.get("title"):
        parts.append(f"Название: {summary['title']}")
    if summary.get("author"):
        parts.append(f"Автор: {summary['author']}")
    parts.append(f"Глав: {summary.get('chapters_count', '?')}")

    if summary.get("core_philosophy"):
        parts.append("")
        parts.append("ГЛАВНАЯ ИДЕЯ:")
        parts.append(summary["core_philosophy"])

    if summary.get("key_concepts"):
        parts.append("")
        parts.append("КОНЦЕПЦИИ:")
        for c in summary["key_concepts"][:15]:
            parts.append(f"  - {c}")

    if summary.get("all_rules"):
        parts.append("")
        parts.append("ПРАВИЛА:")
        for r in summary["all_rules"][:20]:
            parts.append(f"  - {r}")

    if summary.get("entry_conditions"):
        parts.append("")
        parts.append("ВХОД:")
        for r in summary["entry_conditions"][:10]:
            parts.append(f"  - {r}")

    if summary.get("exit_conditions"):
        parts.append("")
        parts.append("ВЫХОД:")
        for r in summary["exit_conditions"][:10]:
            parts.append(f"  - {r}")

    if summary.get("risk_management"):
        parts.append("")
        parts.append("РИСК:")
        for r in summary["risk_management"][:10]:
            parts.append(f"  - {r}")

    if summary.get("all_patterns"):
        parts.append("")
        parts.append("ПАТТЕРНЫ:")
        for p in summary["all_patterns"][:15]:
            parts.append(f"  - {p}")

    if summary.get("indicators_used"):
        parts.append("")
        parts.append(f"ИНДИКАТОРЫ: {', '.join(summary['indicators_used'])}")

    if summary.get("best_for"):
        parts.append("")
        parts.append(f"ПОДХОДИТ ДЛЯ: {summary['best_for']}")

    return "\n".join(parts)


def format_all_summaries(summaries: dict) -> str:
    parts = []
    for fname, s in summaries.items():
        parts.append(f"=== {fname} ===")
        if s.get("core_philosophy"):
            parts.append(s["core_philosophy"])
        if s.get("all_rules"):
            parts.append("Правила: " + "; ".join(s["all_rules"][:10]))
        if s.get("entry_conditions"):
            parts.append("Вход: " + "; ".join(s["entry_conditions"][:5]))
        if s.get("exit_conditions"):
            parts.append("Выход: " + "; ".join(s["exit_conditions"][:5]))
        if s.get("risk_management"):
            parts.append("Риск: " + "; ".join(s["risk_management"][:5]))
        parts.append("")
    return "\n\n".join(parts)