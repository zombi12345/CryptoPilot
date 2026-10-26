import logging
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool

logger = logging.getLogger(__name__)
router = Router()

async def get_ads_config():
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM global_settings WHERE key = 'ads_config'")
    default = {"enabled": False, "frequency": "daily", "frequency_value": 1, "max_per_day": 3, "show_to_admins": False}
    if not row: return default
    try:
        import json
        val = json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
        if isinstance(val, dict):
            for k, v in default.items():
                if k not in val: val[k] = v
            return val
    except: pass
    return default

async def set_ads_config(**kwargs):
    import json
    current = await get_ads_config()
    for k, v in kwargs.items(): current[k] = v
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO global_settings (key, value) VALUES ('ads_config', $1::jsonb) ON CONFLICT (key) DO UPDATE SET value = $1::jsonb", json.dumps(current))

async def log_ad(action, ad_id, user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO ad_stats (ad_id, user_id, action) VALUES ($1, $2, $3)", ad_id, user_id, action)

async def should_show_ad(user_id, is_admin=False):
    config = await get_ads_config()
    if not config.get("enabled"): return False
    if is_admin and not config.get("show_to_admins", False): return False
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        today_count = await conn.fetchval("SELECT COUNT(*) FROM ad_stats WHERE user_id = $1 AND action = 'show' AND created_at >= CURRENT_DATE", user_id)
        max_per_day = config.get("max_per_day", 3)
        if max_per_day > 0 and today_count >= max_per_day: return False
        
        freq = config.get("frequency", "daily")
        if freq == "daily" and today_count > 0: return False
        elif freq == "every_n":
            n = config.get("frequency_value", 5)
            if n > 0:
                total = await conn.fetchval("SELECT COUNT(*) FROM ad_stats WHERE user_id = $1", user_id)
                if total % n != 0: return False
    return True

def _build_ad_url(ad):
    link = ad.get("link")
    if not link: return ""
    mode = ad.get("link_mode", "direct")
    if mode == "utm":
        sep = "&" if "?" in link else "?"
        return f"{link}{sep}utm_source=cryptopilot&utm_medium=ad&utm_campaign=ad_{ad['id']}"
    return link

async def show_ad_if_needed(message: Message, is_admin=False):
    if not await should_show_ad(message.from_user.id, is_admin): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        ads = await conn.fetch("SELECT * FROM ads WHERE enabled = TRUE")
        if not ads: return
        ad = random.choice(ads)
        
    divider = "➖" * 12
    text = f"{divider}\n📢 <b>РЕКЛАМА</b>\n\n{ad['text']}\n{divider}"
    
    # Кнопки: ссылка и (если нажали) счетчик
    buttons = []
    if ad['link']:
        buttons.append([InlineKeyboardButton(text=f"🔥 {ad['button_text']}", callback_data=f"ad_click_{ad['id']}")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

    try:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        await log_ad("show", ad["id"], message.from_user.id)
    except Exception as e:
        logger.error(f"[AD ERROR] {e}")

@router.callback_query(F.data.startswith("ad_click_"))
async def ad_click(callback: CallbackQuery):
    ad_id = int(callback.data.replace("ad_click_", ""))
    await log_ad("click", ad_id, callback.from_user.id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if row:
        ad = dict(row)
        full_link = _build_ad_url(ad)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ Открыть ссылку", url=full_link)]]) if full_link else None
        await callback.message.edit_text(
            f"📢 <b>{ad['text']}</b>\n\n<i>Нажми на кнопку ниже, чтобы перейти.</i>",
            reply_markup=kb, parse_mode="HTML"
        )
    await callback.answer("Переход...")