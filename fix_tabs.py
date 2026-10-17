#!/usr/bin/env python3
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
