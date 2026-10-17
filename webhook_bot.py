import asyncio
import logging
import sys
from loader import bot, dp, setup_bot, shutdown_bot
from handlers import start_router, menu_router, analysis_router, stubs_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Запуск Trading Bot (polling)")
    await setup_bot()

    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(analysis_router)
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