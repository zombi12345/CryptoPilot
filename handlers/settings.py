import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user, get_pool

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="settings_profile")],
        [InlineKeyboardButton(text="📊 Мои стратегии", callback_data="settings_strats")],
        [InlineKeyboardButton(text="📈 История бэктестов", callback_data="settings_bts")],
        [InlineKeyboardButton(text="📰 Дайджест (8:00)", callback_data="settings_digest")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])

@router.callback_query(F.data == "stub_settings")
async def settings_menu(callback: CallbackQuery):
    await safe_edit(callback.message, "⚙️ <b>НАСТРОЙКИ</b>\n\nВыбери раздел:", reply_markup=settings_kb())
    await callback.answer()

@router.callback_query(F.data == "settings_profile")
async def settings_profile(callback: CallbackQuery):
    uid = callback.from_user.id
    user = await get_user(uid)
    if not user: return await callback.answer("Не найден", show_alert=True)
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        strats = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE user_id = $1", uid)
    
    text = (
        f"👤 <b>ПРОФИЛЬ</b>\n➖➖➖➖➖➖➖➖➖➖\n"
        f"ID: <code>{uid}</code>\n"
        f"Имя: {user.get('first_name') or '-'}\n"
        f"Подписка: {'✅ до ' + user['subscription_end'].strftime('%d.%m.%Y') if user.get('subscription_end') else '❌ Нет'}\n"
        f"Стратегий: {strats}"
    )
    await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()

@router.callback_query(F.data == "settings_strats")
async def settings_strats(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, symbol, timeframe, is_active FROM strategies WHERE user_id = $1", callback.from_user.id)
    if not rows: return await safe_edit(callback.message, "Нет стратегий.", reply_markup=settings_kb())
    text = "📊 <b>МОИ СТРАТЕГИИ:</b>\n"
    for r in rows: text += f"{'🟢' if r['is_active'] else '⚪'} {r['name']} ({r['symbol']})\n"
    await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()

@router.callback_query(F.data == "settings_bts")
async def settings_bts(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol, total_return_pct FROM backtests WHERE user_id = $1 LIMIT 5", callback.from_user.id)
    if not rows: return await safe_edit(callback.message, "Бэктестов нет.", reply_markup=settings_kb())
    text = "📈 <b>БЭКТЕСТЫ:</b>\n"
    for r in rows: text += f"• {r['symbol']}: {r['total_return_pct']}%\n"
    await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()

@router.callback_query(F.data == "settings_digest")
async def settings_digest(callback: CallbackQuery):
    text = (
        "📰 <b>УТРЕННИЙ ДАЙДЖЕСТ</b>\n\n"
        "Каждый день в <b>08:00 UTC (11:00 МСК)</b> бот будет присылать:\n"
        "• Топ-5 монет (изменение за 24ч)\n"
        "• Главные новости криптомира\n\n"
        "<i>Дайджест включен автоматически для всех юзеров.</i>"
    )
    await safe_edit(callback.message, text, reply_markup=settings_kb())
    await callback.answer()