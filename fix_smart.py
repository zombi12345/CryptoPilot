#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
p = BASE / "handlers" / "trading.py"
content = p.read_text(encoding="utf-8")

# 1. Добавляем waiting_ticker в AutoStates, если его нет
if "waiting_ticker = State()" not in content:
    content = content.replace(
        "class AutoStates(StatesGroup):\n    waiting_settings = State()",
        "class AutoStates(StatesGroup):\n    waiting_settings = State()\n    waiting_ticker = State()"
    )
    print("OK: waiting_ticker добавлен в AutoStates")

# 2. Ищем старую функцию smart_congress
start_marker = '@router.callback_query(F.data == "smart_congress")'
end_marker = '@router.callback_query(F.data == "smart_insider")'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    # Вырезаем старый блок
    new_block = '''@router.callback_query(F.data == "smart_congress")
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
    content = content[:start_idx] + new_block + content[end_idx:]
    print("OK: smart_congress заменён на ввод тикера")
else:
    print("WARN: не найдены маркеры smart_congress / smart_insider")

p.write_text(content, encoding="utf-8", newline="")
print("ГОТОВО")