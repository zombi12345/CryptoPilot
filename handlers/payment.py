import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool, get_user
from config import BOT_TOKEN

logger = logging.getLogger(__name__)
router = Router()

async def get_plans_from_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM global_settings WHERE key LIKE 'plan_%'")
    
    plans = {
        "1m": {"name": "1 месяц", "days": 30, "stars": 150},
        "3m": {"name": "3 месяца", "days": 90, "stars": 400},
        "1y": {"name": "1 год", "days": 365, "stars": 1500}
    }
    
    for r in rows:
        key = r["key"]
        val = str(r["value"]).replace('"', '')
        # plan_1m_stars или plan_1m_days
        if "_stars" in key:
            pid = key.replace("plan_", "").replace("_stars", "")
            if pid in plans:
                try: plans[pid]["stars"] = int(val)
                except: pass
        elif "_days" in key:
            pid = key.replace("plan_", "").replace("_days", "")
            if pid in plans:
                try: plans[pid]["days"] = int(val)
                except: pass
            
    return plans

async def payment_kb():
    plans = await get_plans_from_db()
    kb = []
    for plan_id, info in plans.items():
        kb.append([InlineKeyboardButton(
            text=f"{info['name']} ({info['days']} дн.) — {info['stars']} ⭐",
            callback_data=f"pay_{plan_id}"
        )])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

@router.callback_query(F.data == "sub_menu")
async def subscription_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    status = "👑 Premium" if user.get("is_paid") else "🆓 Free"
    text = (
        f"💎 <b>ПОДПИСКА</b>\n\n"
        f"Твой статус: {status}\n"
        f"Доступ к автоторговле, книгам и AI-анализу.\n\n"
        f"Выбери тариф:"
    )
    await callback.message.edit_text(text, reply_markup=await payment_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery):
    plan_id = callback.data.replace("pay_", "")
    plans = await get_plans_from_db()
    plan = plans.get(plan_id)
    if not plan:
        return await callback.answer("Тариф не найден", show_alert=True)

    await callback.message.answer_invoice(
        title=f"Подписка CryptoPilot: {plan['name']}",
        description=f"Доступ ко всем функциям на {plan['days']} дней",
        payload=f"sub_{plan_id}_{plan['days']}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Подписка", amount=plan["stars"])],
    )
    await callback.answer()

@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    payload = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id
    
    parts = payload.split("_")
    days = int(parts[2]) if len(parts) > 2 else 30

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO payments (user_id, stars_paid, payment_id, days)
            VALUES ($1, $2, $3, $4)
        """, user_id, payment.total_amount, charge_id, days)
        
        await conn.execute("""
            UPDATE users 
            SET is_paid = TRUE,
                subscription_end = GREATEST(COALESCE(subscription_end, NOW()), NOW()) + make_interval(days => $1)
            WHERE user_id = $2
        """, days, user_id)

    await message.answer(f"✅ <b>Оплата прошла!</b>\n\nПодписка на {days} дней активирована.", parse_mode="HTML")