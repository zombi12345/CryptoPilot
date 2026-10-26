#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
p = BASE / "handlers" / "trading.py"
content = p.read_text(encoding="utf-8")

# 1. Добавляем waiting_ticker в AutoStates
if "waiting_ticker = State()" not in content:
    content = content.replace(
        "class AutoStates(StatesGroup):\n    waiting_settings = State()",
        "class AutoStates(StatesGroup):\n    waiting_settings = State()\n    waiting_ticker = State()"
    )
    print("OK: waiting_ticker добавлен")

# 2. Добавляем новые обработчики в конец файла
new_code = '''

# ============================================================
# УМНЫЕ ДЕНЬГИ
# ============================================================
from services.smart_money import get_congress_trades

@router.callback_query(F.data == "trade_smart")
async def smart_money_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 Конгресс", callback_data="smart_congress")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    text = (
        "🕵️ <b>УМНЫЕ ДЕНЬГИ</b>\\n\\n"
        "Здесь ты можешь посмотреть сделки конгрессменов США.\\n\\n"
        "Данные приходят с задержкой (до 45 дней).\\n"
        "Это <b>не</b> инвестиционная рекомендация."
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "smart_congress")
async def smart_congress_prompt(callback: CallbackQuery, state: FSMContext):
    await safe_edit(
        callback.message,
        "🏛 <b>СДЕЛКИ КОНГРЕССА</b>\\n\\n"
        "Введи тикер акции (например: <code>NVDA</code>, <code>TSLA</code>, <code>AAPL</code>):"
    )
    await state.set_state(AutoStates.waiting_ticker)
    await callback.answer()


@router.message(AutoStates.waiting_ticker, F.text)
async def smart_congress_fetch(message: Message, state: FSMContext):
    ticker = message.text.strip().upper()
    await state.clear()
    
    msg = await message.answer(f"⏳ Загружаю сделки конгрессменов по {ticker}...")
    res = await get_congress_trades(ticker, limit=10)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой тикер", callback_data="smart_congress")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="trade_smart")],
    ])
    
    if not res.get("ok"):
        await safe_edit(msg, f"❌ Ошибка: {res.get('error')}", reply_markup=kb)
        return
        
    trades = res.get("trades", [])
    if not trades:
        await safe_edit(msg, f"Сделок по {ticker} не найдено.", reply_markup=kb)
        return
        
    text = f"🏛 <b>СДЕЛКИ КОНГРЕССА ({ticker})</b>\\n\\n"
    for t in trades:
        politician = t.get("member", "?")
        type_ = t.get("type", "?")
        amount = t.get("amount_range", "?")
        date = t.get("transaction_date", "?")
        
        icon = "🟢" if "buy" in str(type_).lower() or "purchase" in str(type_).lower() else "🔴"
        text += f"{icon} <b>{politician}</b>\\n  {type_} | {amount} | {date}\\n\\n"
        
    if len(text) > 4000:
        text = text[:4000] + "\\n(обрезано)"
        
    await safe_edit(msg, text, reply_markup=kb)
'''
if "async def smart_money_menu" not in content:
    content += new_code
    print("OK: добавлены обработчики smart money")

p.write_text(content, encoding="utf-8", newline="")
print("ГОТОВО")