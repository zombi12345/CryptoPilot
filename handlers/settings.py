import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from database import get_user, get_pool, toggle_auto_trade

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                await msg.answer(text, parse_mode=parse_mode)
        except Exception:
            pass


def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="settings_profile")],
        [InlineKeyboardButton(text="📊 Мои стратегии", callback_data="settings_strats")],
        [InlineKeyboardButton(text="📈 История бэктестов", callback_data="settings_bts")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        callback.message,
        "⚙️ <b>НАСТРОЙКИ</b>\n\nУправление профилем, стратегиями, историей.\n\n<i>Автоторговля и статистика перенесены в раздел Торговля.</i>",
        reply_markup=settings_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_profile")
async def settings_profile(callback: CallbackQuery):
    uid = callback.from_user.id
    user = await get_user(uid)
    if not user:
        await callback.answer("Не найден", show_alert=True)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        bts_count = await conn.fetchval("SELECT COUNT(*) FROM backtests WHERE user_id = $1", uid)
        strats_count = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE user_id = $1", uid)
        active = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE user_id = $1 AND is_active = TRUE", uid)

    auto_status = "🟢 Вкл" if user.get("allow_spot") else "🔴 Выкл"

    text = (
        f"👤 <b>МОЙ ПРОФИЛЬ</b>\n\n"
        f"ID: <code>{uid}</code>\n"
        f"Имя: {user.get('first_name') or '-'}\n"
        f"Username: @{user.get('username') or '-'}\n\n"
        f"<b>АКТИВНОСТЬ:</b>\n"
        f"  Стратегий: {strats_count or 0} (активных: {active or 0})\n"
        f"  Бэктестов: {bts_count or 0}\n"
        f"  Автоторговля: {auto_status}"
    )
    await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()


@router.callback_query(F.data == "settings_strats")
async def settings_strats(callback: CallbackQuery):
    uid = callback.from_user.id
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, symbol, timeframe, is_active FROM strategies WHERE user_id = $1 ORDER BY created_at DESC", uid)
    if not rows:
        await safe_edit(callback.message, "У тебя нет стратегий.", reply_markup=settings_kb())
    else:
        text = "📊 <b>МОИ СТРАТЕГИИ:</b>\n\n"
        for r in rows:
            status = "🟢" if r["is_active"] else "⚪"
            text += f"{status} #{r['id']} {r['name']} ({r['symbol']} {r['timeframe']})\n"
        await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()


@router.callback_query(F.data == "settings_bts")
async def settings_bts(callback: CallbackQuery):
    uid = callback.from_user.id
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT b.strategy_id, s.name, b.symbol, b.timeframe, b.total_return_pct,
                   b.max_drawdown_pct, b.win_rate, b.total_trades
            FROM backtests b LEFT JOIN strategies s ON s.id = b.strategy_id
            WHERE b.user_id = $1 ORDER BY b.created_at DESC LIMIT 10
        """, uid)
    if not rows:
        await safe_edit(callback.message, "Бэктестов пока нет.", reply_markup=settings_kb())
    else:
        text = "📈 <b>ИСТОРИЯ БЭКТЕСТОВ:</b>\n\n"
        for r in rows:
            name = r["name"] or f"#{r['strategy_id']}"
            text += f"<b>{name}</b> ({r['symbol']} {r['timeframe']})\nДоходность: {r['total_return_pct']}% | Win rate: {r['win_rate']}%\n\n"
        if len(text) > 4000: text = text[:4000] + "\n\n(обрезано)"
        await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()