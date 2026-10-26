import asyncio
import logging
from datetime import datetime
from aiogram import Bot
from database import get_pool
from config import ADMINS
from services.news import get_crypto_news
from services.market_data import fetch_ohlcv

logger = logging.getLogger(__name__)

async def send_daily_report(bot: Bot):
    """Отправляет статистику всем админам раз в день."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        paid = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_paid = TRUE")
        trial = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_used = TRUE")
        stars = await conn.fetchval("SELECT COALESCE(SUM(stars_paid), 0) FROM payments")
        new_today = await conn.fetchval("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE")
        stars_today = await conn.fetchval("SELECT COALESCE(SUM(stars_paid), 0) FROM payments WHERE created_at >= CURRENT_DATE")

    text = (
        "🌅 <b>УТРЕННИЙ ОТЧЕТ АДМИНА</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"👥 Всего юзеров: <b>{total}</b>\n"
        f"💎 Платных: <b>{paid}</b>\n"
        f"🎁 На триале: <b>{trial}</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"🆕 Новых вчера: <b>{new_today}</b>\n"
        f"⭐ Заработано вчера: <b>{stars_today} ⭐</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"<i>Общий баланс: {stars} ⭐</i>"
    )
    
    for admin_id in ADMINS:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отчета для {admin_id}: {e}")

async def send_market_digest(bot: Bot):
    """Отправляет дайджест рынка всем подписанным юзерам."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE is_banned = FALSE")
        
    if not users:
        return

    # 1. Новости
    news_res = await get_crypto_news(limit=5)
    news_text = ""
    if news_res.get("ok"):
        for n in news_res.get("news", []):
            news_text += f"• <a href='{n['link']}'>{n['title']}</a>\n"

    # 2. Топ монет (по объему и изменению)
    # Для простоты берем несколько популярных пар
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
    market_text = ""
    
    for sym in symbols:
        try:
            df = await fetch_ohlcv(sym, "1d", limit=2)
            if not df.empty and len(df) >= 2:
                today_close = df.iloc[-1]["close"]
                yesterday_close = df.iloc[-2]["close"]
                change = (today_close - yesterday_close) / yesterday_close * 100
                icon = "🟢" if change >= 0 else "🔴"
                market_text += f"{icon} {sym}: <b>{change:+.2f}%</b>\n"
        except Exception:
            pass

    text = (
        "☀️ <b>УТРЕННИЙ ДАЙДЖЕСТ РЫНКА</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"<b>📈 ТОП-5 МОНЕТ (24ч):</b>\n{market_text}\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"<b>📰 ГЛАВНЫЕ НОВОСТИ:</b>\n{news_text}\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "<i>Хорошего дня и профитных сделок!</i>"
    )

    for u in users:
        try:
            await bot.send_message(u["user_id"], text, parse_mode="HTML", disable_web_page_preview=True)
            await asyncio.sleep(0.05)
        except Exception:
            pass

async def daily_scheduler(bot: Bot):
    logger.info("⏰ Планировщик запущен")
    last_report_date = None
    last_digest_date = None

    while True:
        now = datetime.utcnow()
        
        # Отчет админам в 09:00 UTC
        if now.hour == 9 and now.minute == 0 and last_report_date != now.date():
            logger.info("Отправка утреннего отчета админам...")
            await send_daily_report(bot)
            last_report_date = now.date()
            await asyncio.sleep(61)
            
        # Дайджест рынка в 08:00 UTC
        elif now.hour == 8 and now.minute == 0 and last_digest_date != now.date():
            logger.info("Отправка дайджеста рынка...")
            await send_market_digest(bot)
            last_digest_date = now.date()
            await asyncio.sleep(61)
            
        await asyncio.sleep(30)

async def start_scheduler(bot: Bot):
    asyncio.create_task(daily_scheduler(bot))