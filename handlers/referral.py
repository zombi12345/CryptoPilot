import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

@router.callback_query(F.data == "stub_referral")
async def referral_menu(callback: CallbackQuery):
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback.from_user.id}"
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE referrer_id = $1", callback.from_user.id)
        
    text = (
        "👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "Приглашай друзей и получай <b>+50 монет</b> за каждого!\n"
        "Твой друг также получит <b>+50 монет</b> на старт.\n\n"
        f"👥 Приглашено друзей: <b>{count}</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        "<i>Нажми на ссылку, чтобы скопировать.</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu_activities")]
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()