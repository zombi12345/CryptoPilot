#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
p = BASE / "handlers" / "trading.py"
content = p.read_text(encoding="utf-8")

# 1. Добавляем "История" в главное меню
old_kb = '''        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],'''
new_kb = '''        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="📜 История", callback_data="trade_history")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],'''

if old_kb in content:
    content = content.replace(old_kb, new_kb)
    print("OK: кнопка История добавлена")
else:
    print("WARN: кнопка не найдена (уже есть или другой текст)")

# 2. Добавляем обработчик истории в конец файла (если его нет)
if "async def show_history" not in content:
    history_code = '''

# ============================================================
# ИСТОРИЯ СДЕЛОК
# ============================================================
@router.callback_query(F.data == "trade_history")
async def show_history(callback: CallbackQuery):
    orders = await list_orders(callback.from_user.id, limit=20)
    stats = await get_orders_stats(callback.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_history")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    
    if not orders:
        await safe_edit(callback.message, "📜 История пуста. Сделок ещё не было.", reply_markup=kb)
        return
    
    total = stats.get("total", 0) or 0
    closed = stats.get("closed", 0) or 0
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0
    total_pnl = float(stats.get("total_pnl", 0) or 0)
    
    win_rate = (wins / closed * 100) if closed > 0 else 0
    pnl_sign = "+" if total_pnl >= 0 else ""
    
    text = (
        f"📜 <b>ИСТОРИЯ СДЕЛОК</b>\\n\\n"
        f"📊 Всего: {total} | Закрыто: {closed}\\n"
        f"✅ Wins: {wins} | ❌ Losses: {losses}\\n"
        f"🎯 Win rate: <b>{win_rate:.1f}%</b>\\n"
        f"💰 Общий PnL: <b>{pnl_sign}{total_pnl:.2f} USDT</b>\\n\\n"
        f"<b>Последние сделки:</b>\\n\\n"
    )
    
    for o in orders[:10]:
        status_icon = "🟢" if o["status"] == "open" else "⚪"
        side_icon = "📈" if o["side"] == "buy" else "📉"
        dt = o["created_at"].strftime("%d.%m %H:%M") if o["created_at"] else "?"
        
        line = f"{status_icon} {side_icon} {o['symbol']} {o['amount']} @ {o['entry_price']:.2f}\\n"
        if o["status"] == "closed" and o["pnl"] is not None:
            pnl_s = "+" if float(o["pnl"]) >= 0 else ""
            line += f"   PnL: {pnl_s}{float(o['pnl']):.2f} USDT | {dt}\\n\\n"
        else:
            line += f"   Открыта | {dt}\\n\\n"
        text += line
    
    if len(text) > 4000:
        text = text[:4000] + "\\n(обрезано)"
    
    await safe_edit(callback.message, text, reply_markup=kb)
'''
    content += history_code
    print("OK: обработчик истории добавлен")

p.write_text(content, encoding="utf-8", newline="")
print("ГОТОВО")