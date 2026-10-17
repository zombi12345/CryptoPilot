#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Загрузчик Фазы A: PROJECT_STATE.md + preflight.bat + fix_tabs.py + check_encoding.py.
Запуск: python download_A.py
"""

from pathlib import Path

BASE = Path(__file__).parent

PROJECT_STATE_MD = r'''# PROJECT STATE — Trading Bot

> Обновляется в конце каждой сессии. Читать в начале каждой сессии — 30 секунд вместо 2000 строк правил.

---

## 📍 Текущий этап

**Фаза 0: Фундамент взаимодействия (A)**
Создаём PROJECT_STATE.md + preflight.bat + вспомогательные скрипты.

---

## ✅ Что работает

- Ничего (проект только начат)

---

## ❌ Что не работает

- Всё (проект только начат)

---

## 🎯 План

- [x] **A** — Фундамент взаимодействия (PROJECT_STATE, preflight, fix_tabs, check_encoding)
- [ ] **C** — Архитектурные решения торговли (спот/фьючерсы, demo, ключи, лимиты)
- [ ] **B** — Каркас бота (config, loader, webhook_bot, bot_prod, render.yaml, /start + заглушки)
- [ ] **D** — Анализ графиков (vision + indicators + прогноз)
- [ ] **E** — Стратегии + бэктест
- [ ] **F** — Demo-торговля
- [ ] **G** — Реальная торговля
- [ ] **H** — Новости + полировка

---

## 📦 Последний коммит

`—` (ещё не коммитили)

---

## 🔧 Известные проблемы

Нет.

---

## 🚨 Критичные напоминания

- **Demo-режим по умолчанию** — real только после явного подтверждения.
- **Kill-switch обязателен** — дневной лимит убытка, макс. позиций.
- **Лимит депозита на старте:** $1000.
- **Никакого eval()** в правилах стратегий.
- **Всегда SL + TP** — не торговать без них.
- **Дисклеймер** на каждом сигнале.
- **Письменное соглашение** с юзерами перед real-торговлей.

---

## 🧠 Технические решения (принятые)

- **Python 3.11.9** (не 3.14 — matplotlib/openai ломаются).
- **aiogram 3.13** — как в AstroBot.
- **PostgreSQL (Supabase pooler)** через asyncpg + `statement_cache_size=0`.
- **Redis** — FSM + rate-limit + кэш котировок.
- **Flask + gunicorn** — webhook для Render.
- **UptimeRobot** — `/health` каждые 5 минут.
- **AI-провайдер** — n1n.ai (gpt-4o-mini) + Gemini Flash (fallback).
- **Биржи** — Binance + Bybit через ccxt.
- **Файлы** — только UTF-8 без BOM, только 4 пробела, только полные файлы.

---

## 🪨 Грабли, которые НЕ повторяем

1. ❌ `Set-Content -Encoding UTF8` в PS5 → BOM → SyntaxError.
2. ❌ `write_text(newline="\n")` → обнуляет файлы.
3. ❌ `content.replace()` с кодом → ломает отступы.
4. ❌ `pip install X` без `==` → PyPI-фейки.
5. ❌ Табы → TabError.
6. ❌ `asyncio.gather` с SendMessage.
7. ❌ `callback.message.from_user` → это ID бота.
8. ❌ Кэш без инвалидации при UPDATE.
9. ❌ Миграции без `ADD COLUMN IF NOT EXISTS`.
10. ❌ Старый процесс бота в памяти → не подхватывает изменения.

---

## 📚 Ссылки

- **GitHub:** будет создан на этапе B
- **Render:** будет создан на этапе B
- **Supabase:** будет создан на этапе B
- **Бот:** будет создан на этапе B

---

## 🗓️ История сессий

### Сессия 1 (2026-10-17)
- Обработаны материалы AstroBot + PravoRB
- Приняты правила работы
- Решено: A → C → B
- Создаём: PROJECT_STATE.md, preflight.bat, fix_tabs.py, check_encoding.py
'''

PREFLIGHT_BAT = r'''@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo PREFLIGHT CHECK — Trading Bot
echo ============================================================
echo.

REM --- 1. Проверка Python ---
echo [1/6] Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo    X Python не найден в PATH
    echo    Установи Python 3.11.9 и добавь в PATH
    pause
    exit /b 1
)
python --version
echo    OK Python
echo.

REM --- 2. Фикс табов ---
echo [2/6] Замена табов на 4 пробела...
if exist fix_tabs.py (
    python fix_tabs.py
    echo    OK Табы исправлены
) else (
    echo    WARN fix_tabs.py не найден - пропуск
)
echo.

REM --- 3. Проверка кодировки ---
echo [3/6] Проверка UTF-8 без BOM...
if exist check_encoding.py (
    python check_encoding.py
    echo    OK Кодировка проверена
) else (
    echo    WARN check_encoding.py не найден - пропуск
)
echo.

REM --- 4. Проверка requirements.txt ---
echo [4/6] Проверка requirements.txt (все с ==)...
if exist requirements.txt (
    findstr /R /C:"^[a-zA-Z].*==.*" requirements.txt >nul
    if errorlevel 1 (
        echo    WARN В requirements.txt есть версии без ==
    ) else (
        echo    OK Версии зафиксированы
    )
) else (
    echo    WARN requirements.txt не найден
)
echo.

REM --- 5. Git commit + push ---
echo [5/6] Git commit + push...
git status --porcelain >nul 2>&1
if errorlevel 1 (
    echo    WARN Git не инициализирован - пропуск
) else (
    git add -A
    git diff --cached --quiet
    if errorlevel 1 (
        git commit -m "auto: preflight commit"
        git push 2>nul
        if errorlevel 1 (
            echo    WARN Push не удался
        ) else (
            echo    OK Commit + push OK
        )
    ) else (
        echo    INFO Нечего коммитить
    )
)
echo.

REM --- 6. Запуск бота ---
echo [6/6] Запуск бота...
echo ============================================================
echo.

powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -like '*webhook_bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo    Старый процесс очищен
echo.

echo    Запуск webhook_bot.py...
echo.
python webhook_bot.py

endlocal
pause
'''

FIX_TABS_PY = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Заменяет табы на 4 пробела во всех .py файлах."""

from pathlib import Path

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", ".idea", ".vscode"}


def fix_file(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"   WARN {path}: не UTF-8 — пропуск")
        return False
    except Exception as e:
        print(f"   WARN {path}: ошибка чтения — {e}")
        return False

    if "\t" not in content:
        return False

    new_content = content.replace("\t", "    ")

    try:
        path.write_text(new_content, encoding="utf-8")
        tabs_count = content.count("\t")
        print(f"   FIX {path}: {tabs_count} табов -> 4 пробела")
        return True
    except Exception as e:
        print(f"   ERR {path}: ошибка записи — {e}")
        return False


def main():
    root = Path(".")
    changed = 0
    total = 0

    for py_file in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py_file.parts):
            continue
        total += 1
        if fix_file(py_file):
            changed += 1

    print()
    print(f"   Всего проверено: {total} файлов")
    print(f"   Исправлено: {changed}")


if __name__ == "__main__":
    main()
'''

CHECK_ENCODING_PY = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверяет UTF-8 без BOM. Исправляет BOM и CP1251."""

from pathlib import Path

SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules", ".idea", ".vscode"}

BOM_UTF8 = b"\xef\xbb\xbf"


def check_file(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception as e:
        print(f"   ERR {path}: ошибка чтения — {e}")
        return "error"

    if raw.startswith(BOM_UTF8):
        try:
            content = raw[len(BOM_UTF8):].decode("utf-8")
            path.write_bytes(content.encode("utf-8"))
            print(f"   FIX {path}: удалён BOM")
            return "bom_fixed"
        except Exception as e:
            print(f"   ERR {path}: не UTF-8 после BOM — {e}")
            return "error"

    try:
        raw.decode("utf-8")
        return "ok"
    except UnicodeDecodeError:
        pass

    try:
        content = raw.decode("cp1251")
        path.write_bytes(content.encode("utf-8"))
        print(f"   FIX {path}: CP1251 -> UTF-8")
        return "cp1251_fixed"
    except Exception as e:
        print(f"   ERR {path}: не UTF-8 и не CP1251 — {e}")
        return "error"


def main():
    root = Path(".")
    stats = {"ok": 0, "bom_fixed": 0, "cp1251_fixed": 0, "error": 0, "skip": 0}

    for py_file in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py_file.parts):
            stats["skip"] += 1
            continue
        status = check_file(py_file)
        stats[status] = stats.get(status, 0) + 1

    print()
    print(f"   OK: {stats['ok']}")
    print(f"   BOM удалён: {stats['bom_fixed']}")
    print(f"   CP1251 -> UTF-8: {stats['cp1251_fixed']}")
    print(f"   Ошибок: {stats['error']}")


if __name__ == "__main__":
    main()
'''


FILES = {
    "PROJECT_STATE.md": PROJECT_STATE_MD,
    "preflight.bat": PREFLIGHT_BAT,
    "fix_tabs.py": FIX_TABS_PY,
    "check_encoding.py": CHECK_ENCODING_PY,
}


def main():
    print("=" * 60)
    print("Загрузчик Фазы A")
    print("=" * 60)
    print()

    for filename, content in FILES.items():
        path = BASE / filename
        path.write_text(content, encoding="utf-8", newline="")
        size = len(content.encode("utf-8"))
        print(f"   OK {filename} ({size} B)")

    print()
    print("=" * 60)
    print("ГОТОВО!")
    print("=" * 60)
    print()
    print("Что создано:")
    print("  1. PROJECT_STATE.md      — живой документ (читать в начале сессии)")
    print("  2. preflight.bat         — чек-лист перед запуском бота")
    print("  3. fix_tabs.py           — замена табов на 4 пробела")
    print("  4. check_encoding.py     — проверка UTF-8 без BOM")
    print()
    print("Дальше:")
    print("  1. Проверь, что файлы созданы")
    print("  2. Прочитай PROJECT_STATE.md — это контекст для следующих сессий")
    print("  3. Git commit:")
    print("     git add .")
    print("     git commit -m 'Фаза A: фундамент взаимодействия'")
    print()
    print("Переходим к Фазе C — архитектурные решения торговли.")


if __name__ == "__main__":
    main()