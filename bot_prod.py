import os
import logging
import asyncio
from flask import Flask, request
from aiogram.types import Update
from loader import bot, dp, setup_bot
from handlers import start_router, menu_router, analysis_router, stubs_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

dp.include_router(start_router)
dp.include_router(menu_router)
dp.include_router(analysis_router)
dp.include_router(stubs_router)

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.model_validate(data, context={"bot": bot})
        future = asyncio.run_coroutine_threadsafe(dp.feed_update(bot, update), loop)
        future.result(timeout=30)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500


@app.route("/health")
def health():
    return "OK", 200


@app.route("/")
def home():
    return "Trading Bot is running", 200


async def setup_webhook():
    await setup_bot()
    external_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not external_url:
        external_url = os.environ.get("WEBHOOK_URL", "").rstrip("/")
    if not external_url:
        logger.warning("RENDER_EXTERNAL_URL не установлен")
        return
    webhook_url = f"{external_url}/webhook"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info(f"Webhook: {webhook_url}")


def run_loop():
    loop.run_forever()


if __name__ == "__main__":
    import threading
    loop.run_until_complete(setup_webhook())
    threading.Thread(target=run_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Flask на порту {port}")
    app.run(host="0.0.0.0", port=port, debug=False)