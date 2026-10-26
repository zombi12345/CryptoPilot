import asyncio
import logging
import sys
from loader import bot, dp, setup_bot, shutdown_bot
from database import init_db, init_payments_db, init_trader_db, init_portfolio_db, init_daily_bonus_db, init_shop_db, init_referral_db
from services.scheduler import start_scheduler
from handlers import (
    start_router, menu_router, analysis_router, books_router,
    strategies_router, api_keys_router, trading_router, news_router,
    payment_router, admin_router, ads_display_router, journal_router,
    portfolio_router, bonus_router, shop_router, referral_router,
    settings_router, help_router, stubs_router,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

async def main():
    await init_db()
    await init_payments_db()
    await init_trader_db()
    await init_portfolio_db()
    await init_daily_bonus_db()
    await init_shop_db()
    await init_referral_db()
    await setup_bot()

    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(analysis_router)
    dp.include_router(books_router)
    dp.include_router(strategies_router)
    dp.include_router(api_keys_router)
    dp.include_router(trading_router)
    dp.include_router(news_router)
    dp.include_router(payment_router)
    dp.include_router(admin_router)
    dp.include_router(ads_display_router)
    dp.include_router(journal_router)
    dp.include_router(portfolio_router)
    dp.include_router(bonus_router)
    dp.include_router(shop_router)
    dp.include_router(referral_router)
    dp.include_router(settings_router)
    dp.include_router(help_router)
    dp.include_router(stubs_router)

    from services.auto_trader import auto_trade_worker
    asyncio.create_task(auto_trade_worker(bot))
    await start_scheduler(bot)

    try:
        await dp.start_polling(bot)
    finally:
        await shutdown_bot()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: sys.exit(0)