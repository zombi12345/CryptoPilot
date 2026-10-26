import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from keyboards.main import main_menu_keyboard, main_reply_keyboard
from database import create_user_if_missing, get_pool, get_user
from config import ADMINS
from handlers.ads_display import show_ad_if_needed

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", user_id)
    is_new = not existing
    await create_user_if_missing(user_id, message.from_user.username or "", message.from_user.first_name or "")

    if is_new:
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1].replace("ref_", ""))
                if referrer_id != user_id:
                    async with pool.acquire() as conn:
                        await conn.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES ($1, $2) ON CONFLICT (referred_id) DO NOTHING", referrer_id, user_id)
                        await conn.execute("UPDATE users SET balance_coins = COALESCE(balance_coins, 0) + 50 WHERE user_id = $1", user_id)
                        await conn.execute("UPDATE users SET balance_coins = COALESCE(balance_coins, 0) + 50 WHERE user_id = $1", referrer_id)
                    await message.answer("🎁 Ты получил <b>+50 монет</b> за переход по реферальной ссылке!", parse_mode="HTML")
                    try: await message.bot.send_message(referrer_id, "🎉 По твоей ссылке зашел друг! Ты получил <b>+50 монет</b>.", parse_mode="HTML")
                    except: pass
            except Exception as e:
                logger.error(f"Referral error: {e}")

    async with pool.acquire() as conn:
        trial_enabled = await conn.fetchval("SELECT value FROM global_settings WHERE key = 'trial_enabled'")
        trial_days = await conn.fetchval("SELECT value FROM global_settings WHERE key = 'trial_days'")
        
        # Выдаем триал, если включено и юзер новый
        if str(trial_enabled).replace('"', '') == "true":
            row = await conn.fetchrow("SELECT trial_used, is_paid FROM users WHERE user_id = $1", user_id)
            if row and not row["trial_used"] and not row["is_paid"]:
                days = int(str(trial_days).replace('"', '')) if trial_days else 3
                await conn.execute("UPDATE users SET is_paid = TRUE, trial_used = TRUE, subscription_end = NOW() + make_interval(days => $1) WHERE user_id = $2", days, user_id)
                await message.answer(f"🎁 <b>Вам активирован бесплатный триал на {days} дней!</b>", parse_mode="HTML")

    user = await get_user(user_id)
    is_paid = user.get("is_paid", False)
    sub_end = user.get("subscription_end")
    
    # Предупреждение о платном доступе
    if not is_paid:
        warning = (
            "⚠️ <b>БЕСПЛАТНЫЙ ДОСТУП</b>\n"
            "У вас нет активной подписки.\n"
            "Лимит AI: <b>50 запросов/день</b>.\n"
            "Торговля: <b>только Demo</b>.\n\n"
            "💎 Купите Premium, чтобы получить:\n"
            "• 150 запросов в день\n"
            "• Реальную торговлю\n"
            "• Приоритетную поддержку\n\n"
            "👇 Ознакомьтесь с тарифами в разделе «Профиль → Подписка»."
        )
        await message.answer(warning, parse_mode="HTML")
    elif is_paid and sub_end:
        date_str = sub_end.strftime("%d.%m.%Y")
        await message.answer(f"💎 <b>Ваша подписка активна до {date_str}!</b>", parse_mode="HTML")

    text = (
        "👋 <b>Добро пожаловать в CryptoPilot!</b>\n\n"
        "Твой личный AI-ассистент для торговли и анализа криптовалют.\n\n"
        "🤖 <b>Что я умею:</b>\n"
        "📊 <b>Анализ</b> — отправь фото графика, и я дам прогноз.\n"
        "📚 <b>Библиотека</b> — загрузи книги, и я буду их использовать.\n"
        "📈 <b>Стратегии</b> — создавай правила и тестируй на истории.\n"
        "💼 <b>Торговля</b> — открывай сделки на Demo (или Mainnet с Premium).\n"
        "🎮 <b>Бонусы и Магазин</b> — зарабатывай монеты и трать их.\n\n"
        "Выбери раздел в меню ниже 👇"
    )
    await message.answer(text, reply_markup=main_reply_keyboard(), parse_mode="HTML")
    await message.answer("📌 <b>Главное меню:</b>", reply_markup=main_menu_keyboard(user_id, user_id in ADMINS), parse_mode="HTML")
    await show_ad_if_needed(message, is_admin=user_id in ADMINS)