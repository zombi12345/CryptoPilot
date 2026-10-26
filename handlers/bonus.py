import logging
from datetime import date, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool, get_user, get_global_setting

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

async def get_bonus_settings():
    base = await get_global_setting("bonus_base", "10")
    step = await get_global_setting("bonus_step", "5")
    return int(str(base).replace('"', '')), int(str(step).replace('"', ''))

@router.callback_query(F.data == "stub_bonus")
async def bonus_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user: return await callback.answer("Нажми /start", show_alert=True)
    
    streak = user.get("bonus_streak", 0)
    balance = user.get("balance_coins", 0)
    last_date = user.get("last_bonus_date")
    today = date.today()
    base, step = await get_bonus_settings()
    
    can_claim = True
    if last_date == today:
        can_claim = False
    elif last_date and last_date < today - timedelta(days=1):
        streak = 0 # Стрик сгорел
        
    text = (
        "🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 Твой баланс: <b>{balance} монет</b>\n"
        f"🔥 Твой стрик: <b>{streak} дней</b>\n\n"
    )
    
    if can_claim:
        next_reward = base + (streak * step)
        text += f"🎉 Забери ежедневный бонус: <b>+{next_reward} монет</b>!"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🎁 Забрать {next_reward} монет", callback_data="claim_bonus")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]
        ])
    else:
        text += "✅ Ты уже забрал бонус сегодня. Возвращайся завтра!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
        
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "claim_bonus")
async def claim_bonus(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    today = date.today()
    base, step = await get_bonus_settings()
    
    if user.get("last_bonus_date") == today:
        return await callback.answer("Ты уже забрал бонус сегодня!", show_alert=True)
        
    streak = user.get("bonus_streak", 0)
    last_date = user.get("last_bonus_date")
    
    if last_date and last_date < today - timedelta(days=1):
        streak = 0
        
    new_streak = streak + 1
    reward = base + (streak * step)
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET balance_coins = COALESCE(balance_coins, 0) + $1, last_bonus_date = CURRENT_DATE, bonus_streak = $2 WHERE user_id = $3
        """, reward, new_streak, callback.from_user.id)
        
    await callback.answer(f"🎉 Ты получил {reward} монет! Стрик: {new_streak}", show_alert=True)
    await bonus_menu(callback)