import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import TradeStates
from keyboards.main import main_menu_keyboard
from services.risk_guard import check_trade
from services.exchange import place_order
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()

_pending = {}


def trading_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="trade_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")],
    ])


@router.callback_query(F.data == "stub_trading")
async def trading_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Торговля (DEMO TESTNET)\n\n"
        "Все сделки идут на testnet. Реальные деньги не используются.\n\n"
        "RiskGuard проверит:\n"
        "- Плечо\n"
        "- Риск\n"
        "- Наличие SL/TP\n"
        "- Лимит депозита\n\n"
        "Открыть сделку?",
        reply_markup=trading_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "trade_open")
async def trade_open(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Шаг 1/5: Введи тикер (например, BTC/USDT или BTCUSDT):"
    )
    await state.set_state(TradeStates.choosing_symbol)
    await callback.answer()


@router.message(TradeStates.choosing_symbol, F.text)
async def trade_symbol(message: Message, state: FSMContext):
    symbol = message.text.strip().upper().replace("/", "")
    if not symbol:
        await message.answer("Неверный тикер.")
        return
    await state.update_data(symbol=symbol)
    await message.answer("Шаг 2/5: Направление?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="LONG", callback_data="trade_side_buy")],
        [InlineKeyboardButton(text="SHORT", callback_data="trade_side_sell")],
    ]))
    await state.set_state(TradeStates.choosing_direction)


@router.callback_query(TradeStates.choosing_direction, F.data.startswith("trade_side_"))
async def trade_side(callback: CallbackQuery, state: FSMContext):
    side = callback.data.replace("trade_side_", "")
    await state.update_data(side=side)
    await callback.message.edit_text("Шаг 3/5: Размер позиции (в монетах, например 0.001):")
    await state.set_state(TradeStates.choosing_size)
    await callback.answer()


@router.message(TradeStates.choosing_size, F.text)
async def trade_size(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введи положительное число.")
        return
    await state.update_data(amount=amount)
    await message.answer("Шаг 4/5: Плечо (1-10):")
    await state.set_state(TradeStates.setting_sl_tp)


@router.message(TradeStates.setting_sl_tp, F.text)
async def trade_leverage(message: Message, state: FSMContext):
    try:
        lev = float(message.text.strip())
        if lev < 1 or lev > 10:
            raise ValueError
    except ValueError:
        await message.answer("Плечо от 1 до 10.")
        return
    await state.update_data(leverage=lev)
    await message.answer("Шаг 5/5: Введи SL и TP через пробел (например: 60000 65000):")
    await state.set_state(TradeStates.confirming)


@router.message(TradeStates.confirming, F.text)
async def trade_sltp(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Нужно два числа через пробел: SL TP")
        return
    try:
        sl = float(parts[0])
        tp = float(parts[1])
    except ValueError:
        await message.answer("Числа не распознаны.")
        return

    data = await state.get_data()
    symbol = data["symbol"]
    side = data["side"]
    amount = data["amount"]
    leverage = data["leverage"]

    ex_name = "binance" if "USDT" in symbol else "bybit"

    risk_pct = 2.0
    price = (sl + tp) / 2

    check = await check_trade(
        user_id=message.from_user.id,
        symbol=symbol,
        side=side,
        amount=amount,
        price=price,
        leverage=leverage,
        risk_pct=risk_pct,
        has_sl=True,
        has_tp=True,
    )

    if not check.get("ok"):
        await message.answer(f"🚫 RiskGuard блокирует:\n{check['reason']}")
        await state.clear()
        return

    warning = check.get("warning")
    text = (
        f"Проверка RiskGuard: пройдена\n"
        f"Уровень риска: {check['level']}\n"
    )
    if warning:
        text += f"\n⚠️ {warning}\n"
    text += (
        f"\nБиржа: {ex_name} (TESTNET)\n"
        f"Тикер: {symbol}\n"
        f"Направление: {side.upper()}\n"
        f"Размер: {amount}\n"
        f"Плечо: {leverage}x\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n\n"
        f"Подтвердить?"
    )

    _pending[message.from_user.id] = {
        "exchange": ex_name, "symbol": symbol, "side": side,
        "amount": amount, "leverage": leverage, "sl": sl, "tp": tp,
    }

    await message.answer(text, reply_markup=confirm_kb())
    await state.clear()


@router.callback_query(F.data == "trade_confirm")
async def trade_confirm(callback: CallbackQuery):
    user_id = callback.from_user.id
    p = _pending.get(user_id)
    if not p:
        await callback.answer("Нет данных", show_alert=True)
        return

    await callback.message.edit_text("Отправляю ордер на testnet...")
    result = await place_order(
        exchange_name=p["exchange"],
        symbol=p["symbol"],
        side=p["side"],
        amount=p["amount"],
        price=p["sl"],
        leverage=p["leverage"],
        sl=p["sl"],
        tp=p["tp"],
        mode="testnet",
    )

    if result.get("ok"):
        order = result["order"]
        await callback.message.edit_text(
            f"✅ Ордер отправлен (testnet)\n\n"
            f"ID: {order.get('id')}\n"
            f"Тикер: {p['symbol']}\n"
            f"Направление: {p['side'].upper()}\n"
            f"Размер: {p['amount']}\n"
            f"Плечо: {p['leverage']}x\n"
            f"SL: {p['sl']}\n"
            f"TP: {p['tp']}\n\n"
            f"Демо-режим. Реальные деньги не используются."
        )
    else:
        await callback.message.edit_text(f"❌ Ошибка биржи:\n{result.get('error')}")

    _pending.pop(user_id, None)
    await callback.answer()


@router.callback_query(F.data == "trade_cancel")
async def trade_cancel(callback: CallbackQuery):
    _pending.pop(callback.from_user.id, None)
    await callback.message.edit_text("Отменено.", reply_markup=trading_kb())
    await callback.answer()