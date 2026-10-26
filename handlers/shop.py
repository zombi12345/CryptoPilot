import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool, get_user

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

@router.callback_query(F.data == "stub_shop")
async def shop_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    balance = user.get("balance_coins", 0) if user else 0
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        items = await conn.fetch("SELECT * FROM shop_items WHERE is_active = TRUE")
        
    text = f"🛒 <b>МАГАЗИН</b>\n➖➖➖➖➖➖➖➖➖➖\n💰 Твой баланс: <b>{balance} монет</b>\n\n"
    
    if not items:
        text += "Пока пусто. Заходи позже!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
        return await safe_edit(callback.message, text, reply_markup=kb)
        
    kb = []
    for item in items:
        kb.append([InlineKeyboardButton(
            text=f"{item['title']} — {item['price']} монет",
            callback_data=f"buy_item_{item['id']}"
        )])
    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")])
    
    await safe_edit(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("buy_item_"))
async def buy_item(callback: CallbackQuery):
    item_id = int(callback.data.replace("buy_item_", ""))
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        item = await conn.fetchrow("SELECT * FROM shop_items WHERE id = $1", item_id)
        user = await conn.fetchrow("SELECT balance_coins FROM users WHERE user_id = $1", callback.from_user.id)
        
    if not item: return await callback.answer("Товар не найден", show_alert=True)
    
    balance = user["balance_coins"] or 0
    if balance < item["price"]:
        return await callback.answer("❌ Недостаточно монет! Забирай ежедневный бонус.", show_alert=True)
        
    # Списываем монеты
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance_coins = balance_coins - $1 WHERE user_id = $2", item["price"], callback.from_user.id)
        await conn.execute("INSERT INTO user_inventory (user_id, item_id) VALUES ($1, $2)", callback.from_user.id, item_id)
        
    await callback.answer("✅ Покупка успешна!", show_alert=True)
    
    # Выдаем товар
    if item['item_type'] == 'sub':
        try:
            days = int(item['item_value'])
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users 
                    SET is_paid = TRUE, 
                        subscription_end = GREATEST(COALESCE(subscription_end, NOW()), NOW()) + make_interval(days => $1) 
                    WHERE user_id = $2
                """, days, callback.from_user.id)
            await callback.message.answer(f"🎉 <b>Ты купил подписку на {days} дней!</b>", parse_mode="HTML")
        except Exception as e:
            await callback.message.answer(f"⚠️ Ошибка выдачи подписки: {e}")
    else:
        await callback.message.answer(f"🎉 <b>Ты купил: {item['title']}</b>\n\n{item['item_value']}", parse_mode="HTML")
        
    await shop_menu(callback)