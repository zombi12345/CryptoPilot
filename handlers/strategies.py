import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import StrategyStates
from keyboards.main import main_menu_keyboard
from database import (
    list_strategies, get_strategy, create_strategy, toggle_strategy, delete_strategy,
    save_backtest, list_backtests,
)
from services import fetch_ohlcv, compute_indicators, run_backtest
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()

PRESETS = {
    "rsi_reversal": {
        "name": "RSI-реверсия",
        "timeframe": "1h",
        "indicators": [{"name": "RSI", "period": 14}, {"name": "EMA", "period": 200}],
        "entry_rules": [
            {"indicator": "RSI_14", "operator": "<", "value": 30},
            {"indicator": "close", "operator": ">", "value_ref": "EMA_200"},
        ],
        "exit_rules": [{"indicator": "RSI_14", "operator": ">", "value": 70}],
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 4.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "ema_cross": {
        "name": "EMA-кроссовер",
        "timeframe": "4h",
        "indicators": [{"name": "EMA", "period": 50}, {"name": "EMA", "period": 200}],
        "entry_rules": [
            {"indicator": "EMA_50", "operator": "crosses_above", "value_ref": "EMA_200"},
        ],
        "exit_rules": [
            {"indicator": "EMA_50", "operator": "crosses_below", "value_ref": "EMA_200"},
        ],
        "risk": {"stop_loss_pct": 3.0, "take_profit_pct": 6.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "bollinger_bounce": {
        "name": "Bollinger-отскок",
        "timeframe": "1h",
        "indicators": [{"name": "BB", "period": 20, "std": 2}, {"name": "RSI", "period": 14}],
        "entry_rules": [
            {"indicator": "close", "operator": "<", "value_ref": "BB_20_2_LOWER"},
            {"indicator": "RSI_14", "operator": "<", "value": 35},
        ],
        "exit_rules": [{"indicator": "close", "operator": ">", "value_ref": "BB_20_2_MID"}],
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 3.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
}


def strategies_list_kb(strategies):
    kb = []
    for s in strategies:
        status = "[A]" if s["is_active"] else "[-]"
        kb.append([InlineKeyboardButton(text=f"{status} {s['name']} ({s['symbol']} {s['timeframe']})", callback_data=f"str_view_{s['id']}")])
    kb.append([InlineKeyboardButton(text="+ Создать из пресета", callback_data="str_presets")])
    kb.append([InlineKeyboardButton(text="Меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def presets_kb():
    kb = []
    for pid, p in PRESETS.items():
        kb.append([InlineKeyboardButton(text=p["name"], callback_data=f"str_use_{pid}")])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="stub_strategies")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def strategy_view_kb(s):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выключить" if s["is_active"] else "Включить", callback_data=f"str_toggle_{s['id']}")],
        [InlineKeyboardButton(text="Бэктест", callback_data=f"str_bt_{s['id']}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"str_del_{s['id']}")],
        [InlineKeyboardButton(text="Назад", callback_data="stub_strategies")],
    ])


@router.callback_query(F.data == "stub_strategies")
async def strategies_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    strategies = await list_strategies(user_id)
    if not strategies:
        text = "Стратегии\n\nУ тебя пока нет стратегий. Создай из пресета."
    else:
        text = f"Стратегии ({len(strategies)})\n\nВыбери или создай новую:"
    await callback.message.edit_text(text, reply_markup=strategies_list_kb(strategies))
    await callback.answer()


@router.callback_query(F.data == "str_presets")
async def presets_menu(callback: CallbackQuery):
    await callback.message.edit_text("Выбери пресет:", reply_markup=presets_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("str_use_"))
async def use_preset(callback: CallbackQuery, state: FSMContext):
    pid = callback.data.replace("str_use_", "")
    preset = PRESETS.get(pid)
    if not preset:
        await callback.answer("Пресет не найден", show_alert=True)
        return
    await state.update_data(preset_id=pid, preset=preset)
    await callback.message.edit_text(
        f"Пресет: {preset['name']}\n\nВведи тикер (например, BTC/USDT):",
    )
    await state.set_state(StrategyStates.waiting_ticker)
    await callback.answer()


@router.message(StrategyStates.waiting_ticker, F.text)
async def preset_ticker(message: Message, state: FSMContext):
    symbol = message.text.strip().upper()
    if "/" not in symbol:
        await message.answer("Формат: BTC/USDT. Попробуй ещё или /cancel")
        return
    data = await state.get_data()
    preset = data.get("preset")
    preset_id = data.get("preset_id")
    if not preset:
        await message.answer("Ошибка, начни заново.")
        await state.clear()
        return
    sid = await create_strategy(
        user_id=message.from_user.id,
        name=preset["name"],
        symbol=symbol,
        timeframe=preset["timeframe"],
        preset_id=preset_id,
        indicators=preset["indicators"],
        entry_rules=preset["entry_rules"],
        exit_rules=preset["exit_rules"],
        risk=preset["risk"],
        logic=preset["logic"],
    )
    await state.clear()
    await message.answer(f"Стратегия создана (ID {sid}). Открой Стратегии чтобы запустить бэктест.")


@router.callback_query(F.data.startswith("str_view_"))
async def view_strategy(callback: CallbackQuery):
    sid = int(callback.data.replace("str_view_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    text = (
        f"{s['name']}\n\n"
        f"Тикер: {s['symbol']}\n"
        f"Таймфрейм: {s['timeframe']}\n"
        f"Логика: {s['logic']}\n"
        f"Статус: {'активна' if s['is_active'] else 'выключена'}\n"
        f"Индикаторы: {len(s['indicators'])}\n"
        f"Правил входа: {len(s['entry_rules'])}\n"
        f"Правил выхода: {len(s['exit_rules'])}"
    )
    await callback.message.edit_text(text, reply_markup=strategy_view_kb(s))
    await callback.answer()


@router.callback_query(F.data.startswith("str_toggle_"))
async def toggle(callback: CallbackQuery):
    sid = int(callback.data.replace("str_toggle_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await toggle_strategy(sid, not s["is_active"])
    await view_strategy(callback)


@router.callback_query(F.data.startswith("str_del_"))
async def delete(callback: CallbackQuery):
    sid = int(callback.data.replace("str_del_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await delete_strategy(sid)
    await strategies_menu(callback, FSMContext(storage=callback.bot.session.api.kwargs.get("storage")) if False else None) if False else None
    strategies = await list_strategies(callback.from_user.id)
    await callback.message.edit_text(
        f"Стратегия удалена. Осталось: {len(strategies)}",
        reply_markup=strategies_list_kb(strategies),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("str_bt_"))
async def run_bt(callback: CallbackQuery):
    sid = int(callback.data.replace("str_bt_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("Загружаю данные и считаю бэктест...")
    df = await fetch_ohlcv(s["symbol"], s["timeframe"], limit=1000)
    if df.empty:
        await callback.message.edit_text("Не удалось получить данные по тикеру.")
        return
    df = compute_indicators(df, s["indicators"])
    df["close"] = df["close"]
    res = run_backtest(df, s)
    if "error" in res:
        await callback.message.edit_text(f"Ошибка бэктеста: {res['error']}")
        return
    await save_backtest(
        strategy_id=sid, user_id=callback.from_user.id,
        symbol=s["symbol"], timeframe=s["timeframe"],
        period_start=df.iloc[0]["ts"], period_end=df.iloc[-1]["ts"],
        metrics=res, equity_curve=res["equity_curve"], trades=res["trades"],
    )
    text = (
        f"Бэктест: {s['name']}\n\n"
        f"Тикер: {s['symbol']} {s['timeframe']}\n"
        f"Доходность: {res['total_return_pct']}%\n"
        f"Макс. просадка: {res['max_drawdown_pct']}%\n"
        f"Win rate: {res['win_rate']}%\n"
        f"Profit factor: {res['profit_factor']}\n"
        f"Всего сделок: {res['total_trades']}\n\n"
        f"Результат на истории. Будущее может отличаться."
    )
    await callback.message.edit_text(text, reply_markup=strategy_view_kb(s))
    await callback.answer()