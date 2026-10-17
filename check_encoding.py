#!/usr/bin/env python3
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
