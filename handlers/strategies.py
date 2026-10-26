import logging
import json
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from states import StrategyStates
from keyboards.main import main_menu_keyboard
from database import (
    list_strategies, get_strategy, create_strategy, toggle_strategy, delete_strategy,
    save_backtest, list_backtests, get_pool,
)
from services import fetch_ohlcv, compute_indicators
from services.backtest import run_backtest, make_equity_png

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
        "entry_rules": [{"indicator": "EMA_50", "operator": "crosses_above", "value_ref": "EMA_200"}],
        "exit_rules": [{"indicator": "EMA_50", "operator": "crosses_below", "value_ref": "EMA_200"}],
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
    "macd_trend": {
        "name": "MACD-тренд",
        "timeframe": "4h",
        "indicators": [{"name": "MACD", "fast": 12, "slow": 26, "signal": 9}, {"name": "EMA", "period": 200}],
        "entry_rules": [
            {"indicator": "MACD_12_26_9", "operator": "crosses_above", "value_ref": "MACD_12_26_9_SIGNAL"},
            {"indicator": "close", "operator": ">", "value_ref": "EMA_200"},
        ],
        "exit_rules": [{"indicator": "MACD_12_26_9", "operator": "crosses_below", "value_ref": "MACD_12_26_9_SIGNAL"}],
        "risk": {"stop_loss_pct": 3.0, "take_profit_pct": 9.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "stoch_reversal": {
        "name": "Stoch-реверсия",
        "timeframe": "1h",
        "indicators": [{"name": "Stoch", "period": 14}, {"name": "RSI", "period": 14}],
        "entry_rules": [
            {"indicator": "RSI_14", "operator": "<", "value": 30},
            {"indicator": "close", "operator": ">", "value": 0},
        ],
        "exit_rules": [{"indicator": "RSI_14", "operator": ">", "value": 65}],
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 4.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "sma_trend": {
        "name": "SMA-тренд",
        "timeframe": "1d",
        "indicators": [{"name": "SMA", "period": 50}, {"name": "SMA", "period": 200}],
        "entry_rules": [{"indicator": "SMA_50", "operator": ">", "value_ref": "SMA_200"}],
        "exit_rules": [{"indicator": "SMA_50", "operator": "<", "value_ref": "SMA_200"}],
        "risk": {"stop_loss_pct": 5.0, "take_profit_pct": 15.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "bb_breakout": {
        "name": "BB-пробой",
        "timeframe": "1h",
        "indicators": [{"name": "BB", "period": 20, "std": 2}, {"name": "ATR", "period": 14}],
        "entry_rules": [{"indicator": "close", "operator": ">", "value_ref": "BB_20_2_UPPER"}],
        "exit_rules": [{"indicator": "close", "operator": "<", "value_ref": "BB_20_2_MID"}],
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 4.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "rsi_macd_combo": {
        "name": "RSI + MACD",
        "timeframe": "4h",
        "indicators": [
            {"name": "RSI", "period": 14},
            {"name": "MACD", "fast": 12, "slow": 26, "signal": 9},
        ],
        "entry_rules": [
            {"indicator": "RSI_14", "operator": "<", "value": 40},
            {"indicator": "MACD_12_26_9", "operator": "crosses_above", "value_ref": "MACD_12_26_9_SIGNAL"},
        ],
        "exit_rules": [
            {"indicator": "RSI_14", "operator": ">", "value": 70},
        ],
        "risk": {"stop_loss_pct": 3.0, "take_profit_pct": 6.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "ema_pullback": {
        "name": "EMA-откат",
        "timeframe": "1h",
        "indicators": [
            {"name": "EMA", "period": 50},
            {"name": "EMA", "period": 200},
            {"name": "RSI", "period": 14},
        ],
        "entry_rules": [
            {"indicator": "EMA_50", "operator": ">", "value_ref": "EMA_200"},
            {"indicator": "close", "operator": "<", "value_ref": "EMA_50"},
            {"indicator": "RSI_14", "operator": "<", "value": 50},
        ],
        "exit_rules": [{"indicator": "RSI_14", "operator": ">", "value": 70}],
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 5.0, "risk_per_trade_pct": 1.0},
        "logic": "AND",
    },
    "conservative": {
        "name": "Консервативная",
        "timeframe": "1d",
        "indicators": [
            {"name": "EMA", "period": 200},
            {"name": "RSI", "period": 14},
        ],
        "entry_rules": [
            {"indicator": "close", "operator": ">", "value_ref": "EMA_200"},
            {"indicator": "RSI_14", "operator": "<", "value": 50},
        ],
        "exit_rules": [{"indicator": "RSI_14", "operator": ">", "value": 75}],
        "risk": {"stop_loss_pct": 5.0, "take_profit_pct": 15.0, "risk_per_trade_pct": 0.5},
        "logic": "AND",
    },
}


async def safe_edit(msg, text, reply_markup=None):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup)
        else:
            await msg.edit_text(text)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup)
            else:
                await msg.answer(text)
        except Exception:
            pass


def strat_list_kb(strategies):
    kb = []
    for s in strategies:
        status = "A" if s["is_active"] else "-"
        kb.append([InlineKeyboardButton(
            text=f"{status} {s['name']} ({s['symbol']} {s['timeframe']})",
            callback_data=f"str_view_{s['id']}",
        )])
    kb.append([InlineKeyboardButton(text="+ Создать из пресета", callback_data="str_presets")])
    kb.append([InlineKeyboardButton(text="Сравнить все", callback_data="str_compare")])
    kb.append([InlineKeyboardButton(text="Меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def presets_kb():
    kb = []
    for pid, p in PRESETS.items():
        kb.append([InlineKeyboardButton(text=p["name"], callback_data=f"str_use_{pid}")])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="stub_strategies")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def strat_view_kb(s):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выключить" if s["is_active"] else "Включить", callback_data=f"str_toggle_{s['id']}")],
        [InlineKeyboardButton(text="Бэктест", callback_data=f"str_bt_{s['id']}")],
        [InlineKeyboardButton(text="История", callback_data=f"str_hist_{s['id']}")],
        [InlineKeyboardButton(text="Экспорт JSON", callback_data=f"str_export_{s['id']}")],
        [InlineKeyboardButton(text="Клонировать", callback_data=f"str_clone_{s['id']}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"str_del_{s['id']}")],
        [InlineKeyboardButton(text="Назад", callback_data="stub_strategies")],
    ])


@router.callback_query(F.data == "stub_strategies")
async def strategies_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    strategies = await list_strategies(user_id)
    if not strategies:
        text = (
            "СТРАТЕГИИ\n\n"
            "У тебя пока нет стратегий.\n\n"
            "Создай из пресета — 10 готовых вариантов:\n"
            "RSI, EMA, MACD, Bollinger, Stoch, SMA, BB-пробой, RSI+MACD, EMA-откат, консервативная."
        )
    else:
        text = f"СТРАТЕГИИ ({len(strategies)})\n\nВыбери или создай новую:"
    await safe_edit(callback.message, text, reply_markup=strat_list_kb(strategies))
    await callback.answer()


@router.callback_query(F.data == "str_presets")
async def presets_menu(callback: CallbackQuery):
    text = "ПРЕСЕТЫ\n\nГотовые стратегии. Выбери пресет и введи тикер."
    await safe_edit(callback.message, text, reply_markup=presets_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("str_use_"))
async def use_preset(callback: CallbackQuery, state: FSMContext):
    pid = callback.data.replace("str_use_", "")
    preset = PRESETS.get(pid)
    if not preset:
        await callback.answer("Пресет не найден", show_alert=True)
        return
    await state.update_data(preset_id=pid, preset=preset)
    await safe_edit(callback.message, f"Пресет: {preset['name']}\n\nВведи тикер (например, BTC/USDT):")
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
    await message.answer(f"Стратегия создана (ID {sid}).\nОткрой Стратегии чтобы прогнать бэктест.")


@router.callback_query(F.data.startswith("str_view_"))
async def view_strategy(callback: CallbackQuery):
    sid = int(callback.data.replace("str_view_", ""))
    await _show_strategy(callback, sid)


async def _show_strategy(callback: CallbackQuery, sid: int):
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return

    indicators_text = ", ".join(
        f"{i.get('name')}({i.get('period', '')})" for i in s.get("indicators", [])
    )
    entry_text = "\n".join(
        f"  {i+1}. {r.get('indicator')} {r.get('operator')} {r.get('value') if 'value' in r else r.get('value_ref')}"
        for i, r in enumerate(s.get("entry_rules", []))
    )
    exit_text = "\n".join(
        f"  {i+1}. {r.get('indicator')} {r.get('operator')} {r.get('value') if 'value' in r else r.get('value_ref')}"
        for i, r in enumerate(s.get("exit_rules", []))
    )
    risk = s.get("risk", {})

    text = (
        f"СТРАТЕГИЯ #{s['id']}\n\n"
        f"Название: {s['name']}\n"
        f"Тикер: {s['symbol']}\n"
        f"Таймфрейм: {s['timeframe']}\n"
        f"Логика: {s['logic']}\n"
        f"Статус: {'активна' if s['is_active'] else 'выключена'}\n\n"
        f"ИНДИКАТОРЫ:\n  {indicators_text}\n\n"
        f"ВХОД:\n{entry_text}\n\n"
        f"ВЫХОД:\n{exit_text}\n\n"
        f"РИСК:\n"
        f"  SL: {risk.get('stop_loss_pct')}%\n"
        f"  TP: {risk.get('take_profit_pct')}%\n"
        f"  Риск на сделку: {risk.get('risk_per_trade_pct')}%"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n(обрезано)"
    await safe_edit(callback.message, text, reply_markup=strat_view_kb(s))
    await callback.answer()


@router.callback_query(F.data.startswith("str_toggle_"))
async def toggle(callback: CallbackQuery):
    sid = int(callback.data.replace("str_toggle_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await toggle_strategy(sid, not s["is_active"])
    await _show_strategy(callback, sid)


@router.callback_query(F.data.startswith("str_del_"))
async def delete(callback: CallbackQuery):
    sid = int(callback.data.replace("str_del_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await delete_strategy(sid)
    strategies = await list_strategies(callback.from_user.id)
    await safe_edit(
        callback.message,
        f"Стратегия удалена. Осталось: {len(strategies)}",
        reply_markup=strat_list_kb(strategies),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("str_clone_"))
async def clone(callback: CallbackQuery):
    sid = int(callback.data.replace("str_clone_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    new_id = await create_strategy(
        user_id=s["user_id"],
        name=f"{s['name']} (copy)",
        symbol=s["symbol"],
        timeframe=s["timeframe"],
        preset_id=s.get("preset_id"),
        indicators=s["indicators"],
        entry_rules=s["entry_rules"],
        exit_rules=s["exit_rules"],
        risk=s["risk"],
        logic=s["logic"],
    )
    await callback.answer(f"Клонировано (ID {new_id})")
    strategies = await list_strategies(callback.from_user.id)
    await safe_edit(
        callback.message,
        f"Клонировано. Всего стратегий: {len(strategies)}",
        reply_markup=strat_list_kb(strategies),
    )


@router.callback_query(F.data.startswith("str_export_"))
async def export_json(callback: CallbackQuery):
    sid = int(callback.data.replace("str_export_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = {
        "name": s["name"],
        "symbol": s["symbol"],
        "timeframe": s["timeframe"],
        "indicators": s["indicators"],
        "entry_rules": s["entry_rules"],
        "exit_rules": s["exit_rules"],
        "risk": s["risk"],
        "logic": s["logic"],
    }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > 4000:
        text = text[:4000] + "\n(обрезано)"
    await safe_edit(
        callback.message,
        f"JSON стратегии #{sid}:\n\n{text}",
        reply_markup=strat_view_kb(s),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("str_bt_"))
async def run_bt(callback: CallbackQuery):
    sid = int(callback.data.replace("str_bt_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await safe_edit(callback.message, f"Загружаю данные и считаю бэктест для {s['symbol']} {s['timeframe']}...")
    df = await fetch_ohlcv(s["symbol"], s["timeframe"], limit=1000)
    if df.empty:
        await safe_edit(callback.message, "Не удалось получить данные по тикеру.")
        return

    df = compute_indicators(df, s["indicators"])
    res = run_backtest(df, s)
    if "error" in res:
        await safe_edit(callback.message, f"Ошибка бэктеста: {res['error']}")
        return

    await save_backtest(
        strategy_id=sid, user_id=callback.from_user.id,
        symbol=s["symbol"], timeframe=s["timeframe"],
        period_start=df.iloc[0]["ts"], period_end=df.iloc[-1]["ts"],
        metrics=res, equity_curve=res["equity_curve"], trades=res["trades"],
    )

    text = (
        f"БЭКТЕСТ: {s['name']}\n"
        f"Тикер: {s['symbol']} {s['timeframe']}\n"
        f"Свечей: {len(df)}\n\n"
        f"Доходность: {res['total_return_pct']}%\n"
        f"Макс. просадка: {res['max_drawdown_pct']}%\n"
        f"Win rate: {res['win_rate']}% ({res['wins']}W/{res['losses']}L)\n"
        f"Profit factor: {res['profit_factor']}\n"
        f"Sharpe: {res['sharpe']}\n"
        f"Сделок: {res['total_trades']}\n"
        f"Средняя сделка: ${res['avg_pnl']}\n"
        f"Макс прибыль: ${res['max_win']}\n"
        f"Макс убыток: ${res['max_loss']}\n\n"
        f"Результат на истории. Будущее может отличаться."
    )
    if len(text) > 4000:
        text = text[:4000]

    png = make_equity_png(res["equity_curve"])
    if png and os.path.exists(png):
        try:
            await callback.message.answer_photo(FSInputFile(png), caption=text)
        except Exception:
            await safe_edit(callback.message, text)
        try:
            os.remove(png)
        except Exception:
            pass
    else:
        await safe_edit(callback.message, text)
    await callback.answer()


@router.callback_query(F.data.startswith("str_hist_"))
async def history(callback: CallbackQuery):
    sid = int(callback.data.replace("str_hist_", ""))
    s = await get_strategy(sid)
    if not s or s["user_id"] != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    bts = await list_backtests(sid)
    if not bts:
        await safe_edit(callback.message, "Бэктестов ещё нет.", reply_markup=strat_view_kb(s))
        await callback.answer()
        return
    text = f"ИСТОРИЯ БЭКТЕСТОВ #{sid}\n\n"
    for b in bts[:10]:
        dt = b["created_at"].strftime("%d.%m %H:%M") if b.get("created_at") else "?"
        text += (
            f"{dt} {b['symbol']} {b['timeframe']}\n"
            f"  return={b['total_return_pct']}% dd={b['max_drawdown_pct']}% "
            f"wr={b['win_rate']}% trades={b['total_trades']}\n"
        )
    if len(text) > 4000:
        text = text[:4000]
    await safe_edit(callback.message, text, reply_markup=strat_view_kb(s))
    await callback.answer()


@router.callback_query(F.data == "str_compare")
async def compare(callback: CallbackQuery):
    uid = callback.from_user.id
    strategies = await list_strategies(uid)
    if not strategies:
        await callback.answer("Нет стратегий", show_alert=True)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (strategy_id) strategy_id, total_return_pct, win_rate, total_trades
            FROM backtests WHERE user_id = $1
            ORDER BY strategy_id, created_at DESC
        """, uid)

    by_id = {r["strategy_id"]: r for r in rows}
    text = "СРАВНЕНИЕ СТРАТЕГИЙ\n\n"
    for s in strategies:
        b = by_id.get(s["id"])
        if b:
            text += (
                f"{s['name']} ({s['symbol']} {s['timeframe']})\n"
                f"  return={b['total_return_pct']}% wr={b['win_rate']}% trades={b['total_trades']}\n"
            )
        else:
            text += f"{s['name']} ({s['symbol']} {s['timeframe']})\n  нет бэктеста\n"
    if len(text) > 4000:
        text = text[:4000]
    await safe_edit(callback.message, text, reply_markup=strat_list_kb(strategies))
    await callback.answer()
