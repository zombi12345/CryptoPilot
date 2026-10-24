import asyncio
import logging
import sys
from loader import bot, dp, setup_bot, shutdown_bot
from database import init_db
from handlers import start_router, menu_router, analysis_router, strategies_router, stubs_router
from config import ADMINS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def backfill_admins():
    from database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        for admin_id in ADMINS:
            await conn.execute("""
                INSERT INTO users (user_id, username, first_name, is_admin, agreed_at)
                VALUES ($1, 'admin', 'admin', TRUE, NOW())
                ON CONFLICT (user_id) DO UPDATE SET is_admin = TRUE
            """, admin_id)


async def main():
    logger.info("Запуск Trading Bot (polling)")
    await init_db()
    await backfill_admins()
    await setup_bot()

    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(analysis_router)
    dp.include_router(strategies_router)
    dp.include_router(stubs_router)

    try:
        await dp.start_polling(bot)
    finally:
        await shutdown_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлено")
        sys.exit(0)