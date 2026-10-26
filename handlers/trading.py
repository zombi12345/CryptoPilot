import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from states import TradeStates
from services.risk_guard import check_trade
from services.exchange import place_order, fetch_positions, close_position, fetch_balance_full, transfer_spot_to_futures
from services.smart_money import get_congress_trades
from database import (
    list_exchange_keys, save_order, close_order_in_db, list_orders, get_orders_stats,
    get_user, toggle_auto_trade, get_daily_pnl, update_auto_settings
)

logger = logging.getLogger(__name__)
router = Router()
_pending = {}

class AutoStates(StatesGroup):
    waiting_settings = State()
    waiting_ticker = State()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
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
        [InlineKeyboardButton(text="🕵️ Умные деньги", callback_data="trade_smart")],
        [InlineKeyboardButton(text="🤖 Автоторговля", callback_data="trade_auto")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])

@router.callback_query(F.data == "stub_trading")
async def trading_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "💼 <b>ТОРГОВЛЯ</b>\n\n"
        "Здесь ты можешь:\n"
        "• посмотреть баланс и позиции\n"
        "• перевести USDT со спота на фьючерсы\n"
        "• открыть/закрыть сделку\n"
        "• настроить автоторговлю\n"
        "• посмотреть сделки конгресса\n"
        "• управлять API-ключами\n\n"
        "<i>Все сделки по умолчанию идут в режиме testnet (демо).</i>"
    )
    await safe_edit(callback.message, text, reply_markup=trading_main_kb())
    await callback.answer()

# ============================================================
# УМНЫЕ ДЕНЬГИ
# ============================================================
@router.callback_query(F.data == "trade_smart")
async def smart_money_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏛 Конгресс", callback_data="smart_congress")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    text = (
        "🕵️ <b>УМНЫЕ ДЕНЬГИ</b>\n\n"
        "Здесь ты можешь посмотреть сделки конгрессменов США.\n\n"
        "Данные приходят с задержкой от 1 до 45 дней (зависит от скорости раскрытия).\n"
        "Это <b>не</b> инвестиционная рекомендация."
    )
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "smart_congress")
async def smart_congress_prompt(callback: CallbackQuery, state: FSMContext):
    await safe_edit(callback.message, "🏛 <b>СДЕЛКИ КОНГРЕССА</b>\n\nВведи тикер акции (например: <code>NVDA</code>):")
    await state.set_state(AutoStates.waiting_ticker)
    await callback.answer()

@router.message(AutoStates.waiting_ticker, F.text)
async def smart_congress_fetch(message: Message, state: FSMContext):
    ticker = message.text.strip().upper()
    await state.clear()
    msg = await message.answer(f"⏳ Загружаю сделки по {ticker}...")
    res = get_congress_trades(ticker, limit=10)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Другой тикер", callback_data="smart_congress")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="trade_smart")],
    ])
    if not res.get("ok"): return await safe_edit(msg, f"❌ Ошибка: {res.get('error')}", reply_markup=kb)
    trades = res.get("trades", [])
    if not trades: return await safe_edit(msg, f"Сделок по {ticker} не найдено.", reply_markup=kb)
    text = f"🏛 <b>СДЕЛКИ КОНГРЕССА ({ticker})</b>\n\n"
    for t in trades:
        politician = t.get("member", "?")
        type_ = t.get("type", "?")
        amount = t.get("amount_range", "?")
        date = t.get("transaction_date", "?")
        icon = "🟢" if "buy" in str(type_).lower() or "purchase" in str(type_).lower() else "🔴"
        text += f"{icon} <b>{politician}</b>\n  {type_} | {amount} | {date}\n\n"
    if len(text) > 4000: text = text[:4000] + "\n(обрезано)"
    await safe_edit(msg, text, reply_markup=kb)
# ============================================================
# АВТОТОРГОВЛЯ
# ============================================================
@router.callback_query(F.data == "trade_auto")
async def trade_auto(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return await callback.answer("Нажми /start", show_alert=True)
    status = "🟢 Включена" if user.get("allow_spot") else "🔴 Выключена"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Включить" if not user.get("allow_spot") else "🛑 Выключить", callback_data="toggle_auto")],
        [InlineKeyboardButton(text="⚙️ Настроить", callback_data="trade_auto_settings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="trade_auto_stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    text = f"🤖 <b>АВТОТОРГОВЛЯ</b>\n\nСтатус: {status}\n\n<i>Бот каждые 5 минут проверяет ваши активные стратегии.</i>"
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "toggle_auto")
async def toggle_auto_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return await callback.answer("Нажми /start", show_alert=True)
    new_status = not user.get("allow_spot")
    await toggle_auto_trade(callback.from_user.id, new_status)
    await callback.answer("✅ Включено" if new_status else "🛑 Выключено", show_alert=True)
    await trade_auto(callback)

@router.callback_query(F.data == "trade_auto_settings")
async def auto_settings_menu(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    if not user: return await callback.answer("Нажми /start", show_alert=True)
    text = (
        f"⚙️ <b>НАСТРОЙКИ АВТО</b>\n\n"
        f"Риск: <b>{user.get('max_risk_pct')}%</b>\n"
        f"Плечо: <b>{user.get('max_leverage')}x</b>\n"
        f"Сделок/день: <b>{user.get('daily_trades_limit')}</b>\n"
        f"Депозит: <b>${user.get('deposit_limit')}</b>\n\n"
        f"<i>Отправь 4 числа: Риск% Плечо Сделок Депозит$</i>\n"
        f"Пример: <code>2 3 10 100</code>"
    )
    await safe_edit(callback.message, text)
    await state.set_state(AutoStates.waiting_settings)
    await callback.answer()

@router.message(AutoStates.waiting_settings, F.text.regexp(r'^\d+(\.\d+)?\s+\d+\s+\d+\s+\d+(\.\d+)?$'))
async def auto_settings_save(message: Message, state: FSMContext):
    parts = message.text.split()
    try:
        risk, lev, trades, dep = float(parts[0]), float(parts[1]), int(parts[2]), float(parts[3])
        if risk > 10 or lev > 10 or trades > 50 or dep > 100000: raise ValueError
    except ValueError:
        return await message.answer("❌ Неверные значения.")
    await update_auto_settings(message.from_user.id, risk, lev, trades, dep)
    await state.clear()
    await message.answer("✅ Настройки обновлены.")

@router.callback_query(F.data == "trade_auto_stats")
async def auto_stats(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return await callback.answer("Нажми /start", show_alert=True)
    stats = await get_orders_stats(callback.from_user.id)
    orders = await list_orders(callback.from_user.id, limit=10)
    daily_pnl = await get_daily_pnl(callback.from_user.id)
    total = stats.get("total", 0) or 0
    closed = stats.get("closed", 0) or 0
    wins = stats.get("wins", 0) or 0
    total_pnl = float(stats.get("total_pnl", 0) or 0)
    win_rate = (wins / closed * 100) if closed > 0 else 0
    max_loss = float(user.get('deposit_limit', 100)) * float(user.get('daily_loss_limit_pct', 3)) / 100
    text = f"📊 <b>СТАТИСТИКА</b>\n\nДневной PnL: {daily_pnl:+.2f} USDT\nЛимит: {max_loss:.2f} USDT\n\nВсего: {total} | Закрыто: {closed}\nWin rate: <b>{win_rate:.1f}%</b>\nPnL: <b>{total_pnl:+.2f} USDT</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="trade_auto")]])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

# ============================================================
# БАЛАНС / ПОЗИЦИИ / ИСТОРИЯ
# ============================================================
@router.callback_query(F.data == "trade_balance")
async def show_balance(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys: return await callback.answer("Нет ключей", show_alert=True)
    k = keys[0]
    await safe_edit(callback.message, "⏳ Загружаю баланс...")
    res = await fetch_balance_full(callback.from_user.id, k["exchange"], k["mode"], k["market"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Перевести USDT", callback_data="trade_transfer")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_balance")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")],
    ])
    if not res.get("ok"): return await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}", reply_markup=kb)
    coins = res.get("coins", [])
    if not coins: return await safe_edit(callback.message, "💤 Баланс пуст.", reply_markup=kb)
    text = f"💰 <b>БАЛАНС</b>\n\n"
    for c in coins: text += f"• <b>{c['amount']:.4f}</b> {c['coin']}\n"
    await safe_edit(callback.message, text, reply_markup=kb)

@router.callback_query(F.data == "trade_transfer")
async def do_transfer(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys: return
    k = keys[0]
    await safe_edit(callback.message, "⏳ Перевожу...")
    res = await transfer_spot_to_futures(callback.from_user.id, k["exchange"], k["mode"], "spot", "USDT", None)
    if res.get("ok"): await callback.answer("✅ Переведено", show_alert=True)
    else: await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}")
    await show_balance(callback)

@router.callback_query(F.data == "trade_positions")
async def show_positions(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    if not keys: return await callback.answer("Нет ключей", show_alert=True)
    k = keys[0]
    await safe_edit(callback.message, "⏳ Загружаю позиции...")
    res = await fetch_positions(callback.from_user.id, k["exchange"], k["mode"], k["market"])
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_positions")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")]])
    if not res.get("ok"): return await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}", reply_markup=kb)
    positions = res.get("positions", [])
    if not positions: return await safe_edit(callback.message, f"💤 Позиций нет. Баланс: {res.get('balance', 0):.2f} USDT", reply_markup=kb)
    text = f"📊 <b>ПОЗИЦИИ ({len(positions)})</b>\n\n"
    for p in positions:
        side = "🟢" if p["side"] == "long" else "🔴"
        pnl = f"{p['pnl']:+.2f}"
        text += f"{p['symbol']} {side} | {pnl} USDT ({p['roi']:+.2f}%)\n"
    await safe_edit(callback.message, text, reply_markup=kb)

@router.callback_query(F.data == "trade_history")
async def show_history(callback: CallbackQuery):
    orders = await list_orders(callback.from_user.id, limit=10)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="trade_history")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_trading")]])
    if not orders: return await safe_edit(callback.message, "📜 История пуста.", reply_markup=kb)
    text = "📜 <b>ИСТОРИЯ</b>\n\n"
    for o in orders:
        icon = "🟢" if o['status']=='closed' and o['pnl']>0 else "🔴" if o['status']=='closed' else "⚪"
        text += f"{icon} {o['symbol']} @ {o['entry_price']:.2f}\n"
        if o['status'] == 'closed': text += f"   PnL: {o['pnl']:+.2f} USDT\n\n"
        else: text += "   Открыта\n\n"
    await safe_edit(callback.message, text, reply_markup=kb)

# ============================================================
# ОТКРЫТИЕ СДЕЛКИ
# ============================================================
@router.callback_query(F.data == "trade_open")
async def trade_open(callback: CallbackQuery, state: FSMContext):
    await safe_edit(callback.message, "📈 Введи тикер (например: BTCUSDT):")
    await state.set_state(TradeStates.choosing_symbol)
    await callback.answer()

@router.message(TradeStates.choosing_symbol, F.text)
async def trade_symbol(message: Message, state: FSMContext):
    await state.update_data(symbol=message.text.strip().upper())
    await message.answer("Направление?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="LONG", callback_data="trade_side_buy")],[InlineKeyboardButton(text="SHORT", callback_data="trade_side_sell")]]))
    await state.set_state(TradeStates.choosing_direction)

@router.callback_query(TradeStates.choosing_direction, F.data.startswith("trade_side_"))
async def trade_side(callback: CallbackQuery, state: FSMContext):
    await state.update_data(side=callback.data.replace("trade_side_", ""))
    await safe_edit(callback.message, "Размер (например: 0.01):")
    await state.set_state(TradeStates.choosing_size)

@router.message(TradeStates.choosing_size, F.text)
async def trade_size(message: Message, state: FSMContext):
    await state.update_data(amount=float(message.text.strip()))
    await message.answer("Плечо (1-10):")
    await state.set_state(TradeStates.setting_sl_tp)

@router.message(TradeStates.setting_sl_tp, F.text)
async def trade_lev(message: Message, state: FSMContext):
    await state.update_data(leverage=float(message.text.strip()))
    await message.answer("SL и TP через пробел (например: 58000 65000):")
    await state.set_state(TradeStates.confirming)

@router.message(TradeStates.confirming, F.text)
async def trade_sltp(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    data = await state.get_data()
    keys = await list_exchange_keys(message.from_user.id)
    if not keys: return await message.answer("Нет ключей.")
    k = keys[0]
    _pending[message.from_user.id] = {
        "exchange": k["exchange"], "mode": k["mode"], "market": k["market"],
        "symbol": data["symbol"], "side": data["side"], "amount": data["amount"],
        "leverage": data["leverage"], "sl": float(parts[0]), "tp": float(parts[1]),
    }
    await message.answer(f"Подтвердить {data['symbol']} {data['side'].upper()}?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да", callback_data="trade_confirm")],[InlineKeyboardButton(text="❌ Нет", callback_data="trade_cancel")]]))
    await state.clear()

@router.callback_query(F.data == "trade_confirm")
async def trade_confirm(callback: CallbackQuery):
    p = _pending.get(callback.from_user.id)
    if not p: return await callback.answer("Нет данных", show_alert=True)
    await safe_edit(callback.message, "⏳ Отправляю...")
    res = await place_order(callback.from_user.id, p["exchange"], p["symbol"], p["side"], p["amount"], p["sl"], p["leverage"], p["sl"], p["tp"], p["mode"], p["market"])
    if res.get("ok"):
        await save_order(user_id=callback.from_user.id, exchange=p["exchange"], mode=p["mode"], market=p["market"], symbol=p["symbol"], side=p["side"], amount=p["amount"], entry_price=p["sl"], sl=p["sl"], tp=p["tp"], leverage=p["leverage"], order_id=str(res["order"].get("id")))
        await safe_edit(callback.message, "✅ Ордер открыт!")
    else:
        await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}")
    _pending.pop(callback.from_user.id, None)

@router.callback_query(F.data == "trade_cancel")
async def trade_cancel(callback: CallbackQuery):
    _pending.pop(callback.from_user.id, None)
    await safe_edit(callback.message, "Отменено.", reply_markup=trading_main_kb())
