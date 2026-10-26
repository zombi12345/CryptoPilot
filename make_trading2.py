#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent
p = BASE / "handlers" / "trading.py"
content = p.read_text(encoding="utf-8")

# Убираем старый stub_trading
old_stub = '''@router.callback_query(F.data == "stub_trading")
async def trading_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Торговля (DEMO TESTNET)\\n\\n"
        "Все сделки идут на testnet. Реальные деньги не используются.\\n\\n"
        "RiskGuard проверит:\\n"
        "- Плечо\\n"
        "- Риск\\n"
        "- Наличие SL/TP\\n"
        "- Лимит депозита\\n\\n"
        "Открыть сделку?",
        reply_markup=trading_kb(),
    )
    await callback.answer()
'''

if old_stub in content:
    content = content.replace(old_stub, "")
    print("OK: старый stub_trading удалён")

# Обновляем place_order — добавляем user_id
old_call = '''    result = await place_order(
        exchange_name=p["exchange"],
        symbol=p["symbol"],
        side=p["side"],
        amount=p["amount"],
        price=p["sl"],
        leverage=p["leverage"],
        sl=p["sl"],
        tp=p["tp"],
        mode="testnet",
    )'''

new_call = '''    result = await place_order(
        user_id=callback.from_user.id,
        exchange_name=p["exchange"],
        symbol=p["symbol"],
        side=p["side"],
        amount=p["amount"],
        price=p["sl"],
        leverage=p["leverage"],
        sl=p["sl"],
        tp=p["tp"],
        mode=p.get("mode", "testnet"),
        market=p.get("market", "futures"),
    )'''

if old_call in content:
    content = content.replace(old_call, new_call)
    print("OK: place_order обновлён")

p.write_text(content, encoding="utf-8", newline="")
print("ГОТОВО")