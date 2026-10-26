#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path

BASE = Path(__file__).parent

TRADING_PY = '''import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from states import TradeStates
from services.risk_guard import check_trade
from services.exchange import place_order, fetch_positions, close_position, fetch_balance_full, transfer_spot_to_futures
from database import (
    list_exchange_keys, save_order, close_order_in_db, list_orders, get_orders_stats,
    get_user, toggle_auto_trade, get_daily_pnl, update_auto_settings
)

logger = logging.getLogger(__name__)
router = Router()

_pending = {}

class AutoStates(StatesGroup):
    waiting_settings = State()


async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e): return
        try:
            if reply_markup: await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else: await msg.answer(text, parse_mode=parse_mode)
        except Exception: pass


def trading_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="trade_balance")],
        [InlineKeyboardButton(text="📊 Позиции", callback_data="trade_positions")],
        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="📜 История", callback_data="trade_history")],
        [InlineKeyboardButton(text="🤖 Автоторговля", callback_data="trade_auto")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_trading")
async def trading_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "💼 <b>ТОРГОВЛЯ</b>\\n\\n"
        "Здесь ты можешь:\\n"
        "• посмотреть баланс и позиции\\n"
        "• перевести USDT со спота на фьючерсы\\n"
        "• открыть/закрыть сделку\\n"
        "• настроить автоторговлю\\n"
        "• управлять API-ключами\\n\\n"
        "<i>Все сделки по умолчанию идут в режиме testnet (демо).</i>"
    )
    await safe_edit(callback.message, text, reply_markup=trading_main_kb())
    await callback.answer()


# ============================================================
# АВТОТОРГОВЛЯ В ТОРГОВЛЕ
# ============================================================
@router.callback_query(F.data == "trade_auto")
async def trade_auto(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    status = "🟢 Включена" if user.get("allow_spot") else "🔴 Выключена"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Включить" if not user.get("allow_spot") else "🛑 Выключить", callback_data="toggle_auto")],
        [InlineKeyboardButton(text="⚙️ Настроить", callback_data="trade_auto_settings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="trade_auto_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    
    text = (
        f"🤖 <b>АВТОТОРГОВЛЯ</b>\\n\\n"
        f"Статус: {status}\\n\\n"
        f"<i>Бот каждые 5 минут проверяет ваши активные стратегии и сам открывает сделки при сигнале.</i>"
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "toggle_auto")
async def toggle_auto_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    new_status = not user.get("allow_spot")
    await toggle_auto_trade(callback.from_user.id, new_status)
    await callback.answer("✅ Включено" if new_status else "🛑 Выключено", show_alert=True)
    await trade_auto(callback)


@router.callback_query(F.data == "trade_auto_settings")
async def auto_settings_menu(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user: return
    
    text = (
        f"⚙️ <b>НАСТРОЙКИ АВТО</b>\\n\\n"
        f"Текущие параметры:\\n"
        f"  Риск на сделку: <b>{user.get('max_risk_pct')}%</b>\\n"
        f"  Плечо: <b>{user.get('max_leverage')}x</b>\\n"
        f"  Лимит сделок/день: <b>{user.get('daily_trades_limit')}</b>\\n"
        f"  Лимит депозита: <b>${user.get('deposit_limit')}</b>\\n\\n"
        f"<i>Отправь 4 числа через пробел в порядке:\\nРиск_% Плечо_х Сделок_день Депозит_$</i>\\n"
        f"Пример: <code>2 3 10 100</code>"
    )
    await safe_edit(callback.message, text)
    await state.set_state(AutoStates.waiting_settings)
    await callback.answer()


@router.message(AutoStates.waiting_settings, F.text.regexp(r'^\\d+(\\.\\d+)?\\s+\\d+\\s+\\d+\\s+\\d+(\\.\\d+)?$'))
async def auto_settings_save(message: Message, state: FSMContext):
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("❌ Нужно 4 числа: Риск Плечо Сделок Депозит")
        return
        
    try:
        risk, lev, trades, dep = float(parts[0]), float(parts[1]), int(parts[2]), float(parts[3])
        if risk > 10 or lev > 10 or trades > 50 or dep > 100000: raise ValueError
    except ValueError:
        await message.answer("❌ Неверные значения. Риск до 10%, плечо до 10x, сделок до 50, депо до 100000$.")
        return

    await update_auto_settings(message.from_user.id, risk, lev, trades, dep)
    await state.clear()
    await message.answer("✅ Настройки автоторговли обновлены.")
    # Имитация нажатия на кнопку
    class FakeCallback:
        def __init__(self, msg, user):
            self.message = msg
            self.from_user = user
        async def answer(self, *args, **kwargs): pass
    await trade_auto(FakeCallback(message, message.from_user))


@router.callback_query(F.data == "trade_auto_stats")
async def auto_stats(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return
    
    stats = await get_orders_stats(callback.from_user.id)
    orders = await list_orders(callback.from_user.id, limit=10)
    daily_pnl = await get_daily_pnl(callback.from_user.id)
    
    total = stats.get("total", 0) or 0
    closed = stats.get("closed", 0) or 0
    wins = stats.get("wins", 0) or 0
    losses = stats.get("losses", 0) or 0
    total_pnl = float(stats.get("total_pnl", 0) or 0)
    win_rate = (wins / closed * 100) if closed > 0 else 0
    
    max_loss = float(user.get('deposit_limit', 100)) * float(user.get('daily_loss_limit_pct', 3)) / 100
    
    text = (
        f"📊 <b>СТАТИСТИКА АВТО</b>\\n\\n"
        f"Дневной PnL: {daily_pnl:+.2f} USDT\\n"
        f"Лимит убытка: {max_loss:.2f} USDT\\n\\n"
        f"Всего сделок: {total}\\n"
        f"Закрыто: {closed} (W: {wins} / L: {losses})\\n"
        f"Win rate: <b>{win_rate:.1f}%</b>\\n"
        f"Общий PnL: <b>{total_pnl:+.2f} USDT</b>\\n\\n"
        f"<b>Последние:</b>\\n"
    )
    
    for o in orders[:5]:
        icon = "🟢" if o['status']=='closed' and o['pnl'] and o['pnl']>0 else "🔴" if o['status']=='closed' else "⚪"
        text += f"{icon} {o['symbol']} @ {o['entry_price']:.2f}\\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="trade_auto")],
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


# ============================================================
# БАЛАНС
# ============================================================
@router.callback_query(F.data == "trade_balance")
async def show_balance(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys:
        await callback.answer("Сначала добавь API-ключи", show_alert=True)
        return
    k = keys[0]
    await safe_edit(callback.message, "⏳ Загружаю баланс...")
    res = await fetch_balance_full(callback.from_user.id, k["exchange"], k["mode"], k["market"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Перевести USDT на фьючерсы", callback_data="trade_transfer")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_balance")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    if not res.get("ok"):
        await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}", reply_markup=kb)
        return
    coins = res.get("coins", [])
    if not coins:
        await safe_edit(callback.message, "💤 Баланс пуст.", reply_markup=kb)
        return
    text = f"💰 <b>БАЛАНС ({k['exchange'].capitalize()} {k['mode']} {k['market']})</b>\\n\\n"
    for c in coins:
        text += f"• <b>{c['amount']:.4f}</b> {c['coin']}\\n"
    text += "\\n<i>Для фьючерсов нужен USDT на фьючерсном кошельке.</i>"
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "trade_transfer")
async def do_transfer(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys: return
    k = keys[0]
    await safe_edit(callback.message, "⏳ Перевожу USDT...")
    res = await transfer_spot_to_futures(callback.from_user.id, k["exchange"], k["mode"], "spot", "USDT", None)
    if res.get("ok"):
        await callback.answer(f"✅ Переведено {res['amount']:.2f} USDT", show_alert=True)
        await show_balance(callback)
    else:
        await safe_edit(callback.message, f"❌ Ошибка перевода:\\n{res.get('error')}\\n\\n<i>Проверь права Universal Transfer.</i>")
        await callback.answer()


# ============================================================
# ПОЗИЦИИ
# ============================================================
def pos_kb(positions):
    kb = []
    for i, p in enumerate(positions):
        kb.append([InlineKeyboardButton(text=f"❌ Закрыть {p['symbol']} {p['side'].upper()}", callback_data=f"close_pos_{i}")])
    kb.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_positions")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.callback_query(F.data == "trade_positions")
async def show_positions(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys: return
    k = keys[0]
    await safe_edit(callback.message, "⏳ Загружаю позиции...")
    res = await fetch_positions(callback.from_user.id, k["exchange"], k["mode"], k["market"])
    if not res.get("ok"):
        await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}", reply_markup=pos_kb([]))
        return
    positions = res.get("positions", [])
    balance = res.get("balance", 0)
    _pending[callback.from_user.id] = {"positions": positions, "keys": k}
    if not positions:
        await safe_edit(callback.message, f"💤 Открытых позиций нет.\\n\\n💰 Баланс: <b>{balance:.2f} USDT</b>", reply_markup=pos_kb([]))
        return
    text = f"📊 <b>ОТКРЫТЫЕ ПОЗИЦИИ ({len(positions)})</b>\\n💰 Баланс: <b>{balance:.2f} USDT</b>\\n\\n"
    for p in positions:
        side_icon = "🟢 LONG" if p["side"] == "long" else "🔴 SHORT"
        pnl_sign = "+" if p["pnl"] >= 0 else ""
        roi_sign = "+" if p["roi"] >= 0 else ""
        pnl_emoji = "📈" if p["pnl"] >= 0 else "📉"
        text += (
            f"<b>{p['symbol']}</b> {side_icon}\\n"
            f"  📍 Вход: <code>{p['entry']:.2f}</code> → <code>{p['mark']:.2f}</code>\\n"
            f"  {pnl_emoji} PnL: <b>{pnl_sign}{p['pnl']:.2f} USDT</b> ({roi_sign}{p['roi']:.2f}%)\\n"
            f"  ⚙️ Плечо: {p['leverage']}x | 📦 Объем: {p['contracts']}\\n"
            f"  🛑 SL: {p['sl'] or 'нет'} | 🎯 TP: {p['tp'] or 'нет'}\\n\\n"
        )
    if len(text) > 4000: text = text[:4000] + "\\n(обрезано)"
    await safe_edit(callback.message, text, reply_markup=pos_kb(positions))


@router.callback_query(F.data.startswith("close_pos_"))
async def do_close_position(callback: CallbackQuery):
    user_id = callback.from_user.id
    idx = int(callback.data.replace("close_pos_", ""))
    data = _pending.get(user_id)
    if not data or idx >= len(data["positions"]):
        await callback.answer("Позиция не найдена, обнови", show_alert=True)
        return
    p = data["positions"][idx]
    k = data["keys"]
    await safe_edit(callback.message, f"⏳ Закрываю {p['symbol']}...")
    res = await close_position(user_id, k["exchange"], p["symbol"], p["side"], p["contracts"], k["mode"], k["market"])
    if res.get("ok"):
        pnl = p.get("pnl", 0) if p else 0
        close_price = p.get("mark", 0) if p else 0
        await close_order_in_db(user_id, p["symbol"], close_price, pnl)
        await callback.answer("✅ Позиция закрыта", show_alert=True)
        await show_positions(callback)
    else:
        await safe_edit(callback.message, f"❌ Ошибка закрытия:\\n{res.get('error')}")
        await callback.answer()


# ============================================================
# ОТКРЫТИЕ СДЕЛКИ
# ============================================================
@router.callback_query(F.data == "trade_open")
async def trade_open(callback: CallbackQuery, state: FSMContext):
    await safe_edit(callback.message, "📈 <b>ОТКРЫТИЕ СДЕЛКИ</b>\\n\\nШаг 1/5: Введи тикер (например: BTC/USDT или BTCUSDT)")
    await state.set_state(TradeStates.choosing_symbol)
    await callback.answer()

@router.message(TradeStates.choosing_symbol, F.text)
async def trade_symbol(message: Message, state: FSMContext):
    symbol = message.text.strip().upper().replace("/", "")
    if not symbol: return await message.answer("❌ Неверный тикер.")
    await state.update_data(symbol=symbol)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 LONG", callback_data="trade_side_buy")],
        [InlineKeyboardButton(text="🔴 SHORT", callback_data="trade_side_sell")],
    ])
    await message.answer(f"Тикер: <b>{symbol}</b>\\n\\nШаг 2/5: Выбери направление:", reply_markup=kb, parse_mode="HTML")
    await state.set_state(TradeStates.choosing_direction)

@router.callback_query(TradeStates.choosing_direction, F.data.startswith("trade_side_"))
async def trade_side(callback: CallbackQuery, state: FSMContext):
    side = callback.data.replace("trade_side_", "")
    await state.update_data(side=side)
    await safe_edit(callback.message, "Шаг 3/5: Введи размер позиции (например: 0.01)")
    await state.set_state(TradeStates.choosing_size)

@router.message(TradeStates.choosing_size, F.text)
async def trade_size(message: Message, state: FSMContext):
    try: amount = float(message.text.strip().replace(",", "."))
    except: return await message.answer("❌ Введи число.")
    if amount <= 0: return await message.answer("❌ Больше нуля.")
    await state.update_data(amount=amount)
    await message.answer("Шаг 4/5: Введи плечо (1-10)")
    await state.set_state(TradeStates.setting_sl_tp)

@router.message(TradeStates.setting_sl_tp, F.text)
async def trade_leverage(message: Message, state: FSMContext):
    try: lev = float(message.text.strip())
    except: return await message.answer("❌ Введи число.")
    if lev < 1 or lev > 10: return await message.answer("❌ Плечо 1-10.")
    await state.update_data(leverage=lev)
    await message.answer("Шаг 5/5: Введи SL и TP через пробел (например: 58000 65000)", parse_mode="HTML")
    await state.set_state(TradeStates.confirming)

@router.message(TradeStates.confirming, F.text)
async def trade_sltp(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2: return await message.answer("❌ Два числа: SL TP.")
    try: sl, tp = float(parts[0]), float(parts[1])
    except: return await message.answer("❌ Числа не распознаны.")

    data = await state.get_data()
    keys = await list_exchange_keys(message.from_user.id)
    if not keys: return await message.answer("❌ Нет API-ключей.")
    k = keys[0]
    
    check = await check_trade(message.from_user.id, data["symbol"], data["side"], data["amount"], (sl+tp)/2, data["leverage"], 2.0, True, True)
    if not check.get("ok"):
        await message.answer(f"🚫 <b>RiskGuard:</b>\\n{check['reason']}", parse_mode="HTML")
        await state.clear()
        return

    warning = f"\\n⚠️ <i>{check['warning']}</i>\\n" if check.get("warning") else ""
    text = (
        f"✅ <b>RiskGuard пропустил</b>\\nУровень: <b>{check['level']}</b>\\n{warning}\\n"
        f"Биржа: {k['exchange']} ({k['mode']} {k['market']})\\n"
        f"Тикер: <b>{data['symbol']}</b>\\n"
        f"Размер: {data['amount']}\\n"
        f"Плечо: {data['leverage']}x\\n"
        f"🛑 SL: {sl}\\n"
        f"🎯 TP: {tp}\\n\\nПодтвердить?"
    )
    _pending[message.from_user.id] = {
        "exchange": k["exchange"], "mode": k["mode"], "market": k["market"],
        "symbol": data["symbol"], "side": data["side"], "amount": data["amount"],
        "leverage": data["leverage"], "sl": sl, "tp": tp,
    }
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="trade_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data == "trade_confirm")
async def trade_confirm(callback: CallbackQuery):
    p = _pending.get(callback.from_user.id)
    if not p or "symbol" not in p: return await callback.answer("Нет данных", show_alert=True)
    await safe_edit(callback.message, "⏳ Отправляю ордер...")
    result = await place_order(callback.from_user.id, p["exchange"], p["symbol"], p["side"], p["amount"], p["sl"], p["leverage"], p["sl"], p["tp"], p["mode"], p["market"])
    if result.get("ok"):
        await save_order(user_id=callback.from_user.id, exchange=p["exchange"], mode=p["mode"], market=p["market"], symbol=p["symbol"], side=p["side"], amount=p["amount"], entry_price=p["sl"], sl=p["sl"], tp=p["tp"], leverage=p["leverage"], order_id=str(result["order"].get("id")))
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 К позициям", callback_data="trade_positions")], [InlineKeyboardButton(text="⬅️ В меню", callback_data="stub_trading")]])
        await safe_edit(callback.message, f"✅ <b>Ордер открыт</b>\\n\\n🆔 ID: <code>{result['order'].get('id')}</code>\\nТикер: <b>{p['symbol']}</b>\\nРазмер: {p['amount']}\\nПлечо: {p['leverage']}x\\n🛑 SL: {p['sl']}\\n🎯 TP: {p['tp']}", reply_markup=kb)
    else:
        await safe_edit(callback.message, f"❌ <b>Ошибка:</b>\\n{result.get('error')}")
    _pending.pop(callback.from_user.id, None)

@router.callback_query(F.data == "trade_cancel")
async def trade_cancel(callback: CallbackQuery):
    _pending.pop(callback.from_user.id, None)
    await safe_edit(callback.message, "Отменено.", reply_markup=trading_main_kb())


# ============================================================
# ИСТОРИЯ
# ============================================================
@router.callback_query(F.data == "trade_history")
async def show_history(callback: CallbackQuery):
    orders = await list_orders(callback.from_user.id, limit=20)
    stats = await get_orders_stats(callback.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_history")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")]])
    if not orders:
        return await safe_edit(callback.message, "📜 История пуста. Сделок еще не было.", reply_markup=kb)
    total = stats.get("total", 0) or 0
    closed = stats.get("closed", 0) or 0
    wins = stats.get("wins", 0) or 0
    total_pnl = float(stats.get("total_pnl", 0) or 0)
    win_rate = (wins / closed * 100) if closed > 0 else 0
    text = f"📜 <b>ИСТОРИЯ</b>\\n\\nВсего: {total} | Закрыто: {closed}\\nWin rate: <b>{win_rate:.1f}%</b>\\nОбщий PnL: <b>{total_pnl:+.2f} USDT</b>\\n\\n<b>Последние:</b>\\n"
    for o in orders[:10]:
        icon = "🟢" if o['status']=='closed' and o['pnl']>0 else "🔴" if o['status']=='closed' else "⚪"
        text += f"{icon} {o['symbol']} @ {o['entry_price']:.2f}\\n"
        if o["status"] == "closed" and o["pnl"] is not None:
            text += f"   PnL: {o['pnl']:+.2f} USDT\\n\\n"
        else:
            text += "   Открыта\\n\\n"
    if len(text) > 4000: text = text[:4000] + "\\n(обрезано)"
    await safe_edit(callback.message, text, reply_markup=kb)
'''

path = BASE / "handlers" / "trading.py"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(TRADING_PY, encoding="utf-8", newline="")
print(f"OK handlers/trading.py ({len(TRADING_PY.encode('utf-8'))} B)")
print("ГОТОВО")