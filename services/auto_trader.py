import asyncio
import logging
import os
from datetime import datetime, timedelta
from services.market_data import fetch_ohlcv
from services.indicators import compute_indicators
from services.backtest import evaluate_rules
from services.exchange import place_order, fetch_positions
from services.risk_guard import check_trade
from services.news import get_crypto_news
from services.smart_money import get_congress_trades
from database import (
    get_auto_trade_users, list_strategies, get_user, get_daily_pnl,
    save_order, list_exchange_keys, get_orders_stats, toggle_auto_trade,
    get_pool
)

logger = logging.getLogger(__name__)

_last_check = {}
_last_news_check = {}

async def get_user_assets(user_id):
    """Возвращает список тикеров (BTC, ETH), которые у юзера в стратегиях или позициях."""
    assets = set()
    # Из стратегий
    strats = await list_strategies(user_id)
    for s in strats:
        if s["is_active"]:
            base = s["symbol"].split("/")[0].replace("USDT", "").upper()
            assets.add(base)
    # Из позиций (можно тоже добавить, но fetch_positions делает запрос к API)
    return list(assets)

async def check_news_and_insiders(bot, user_id):
    """Проверяет новости и конгресс по активам юзера. Раз в час."""
    now = datetime.now()
    if user_id in _last_news_check and (now - _last_news_check[user_id]).total_seconds() < 3600:
        return
    _last_news_check[user_id] = now

    assets = await get_user_assets(user_id)
    if not assets:
        return

    # 1. Проверка новостей
    news_res = get_crypto_news(limit=10)
    if news_res.get("ok"):
        for n in news_res.get("news", []):
            title = n["title"].upper()
            for asset in assets:
                if asset in title:
                    await bot.send_message(
                        user_id,
                        f"📰 <b>Новость по {asset}</b>\n\n{n['title']}\n\n<a href='{n['link']}'>Читать</a>",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    break

    # 2. Проверка конгресса (только для акций, не крипты)
    for asset in assets:
        if asset in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]:
            continue  # Конгресс торгует акциями, не криптой
        res = get_congress_trades(asset, limit=1)
        if res.get("ok") and res.get("trades"):
            t = res["trades"][0]
            date_str = t.get("transaction_date", "")
            # Проверяем, что сделка свежая (за последние 2 дня)
            try:
                trade_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (now - trade_date).days <= 2:
                    await bot.send_message(
                        user_id,
                        f"🏛 <b>Сделка конгресса по {asset}</b>\n\n"
                        f"{t.get('member')} — {t.get('type')} на {t.get('amount_range')}\n"
                        f"Дата: {date_str}",
                        parse_mode="HTML"
                    )
            except Exception:
                pass

async def auto_trade_worker(bot):
    logger.info("🤖 Автоторговля запущена")
    while True:
        try:
            users = await get_auto_trade_users()
            for user_id in users:
                now = datetime.now()
                if user_id in _last_check and (now - _last_check[user_id]).total_seconds() < 300:
                    continue
                _last_check[user_id] = now

                user = await get_user(user_id)
                if not user: continue

                # 0. Новости и конгресс (раз в час)
                await check_news_and_insiders(bot, user_id)

                # 1. Kill-switch
                daily_pnl = await get_daily_pnl(user_id)
                max_loss = float(user.get("deposit_limit", 100)) * float(user.get("daily_loss_limit_pct", 3)) / 100
                if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
                    await toggle_auto_trade(user_id, False)
                    await bot.send_message(user_id, f"🛑 <b>Автоторговля остановлена</b>\n\nСработал дневной лимит убытка: {daily_pnl:.2f} USDT.\nЛимит: {max_loss:.2f} USDT.", parse_mode="HTML")
                    continue

                # 2. Лимит сделок в день
                pool = await get_pool()
                async with pool.acquire() as conn:
                    today_trades = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE user_id = $1 AND created_at >= CURRENT_DATE", user_id)
                
                max_trades = int(user.get("daily_trades_limit", 10))
                if today_trades >= max_trades:
                    await toggle_auto_trade(user_id, False)
                    await bot.send_message(user_id, f"⚠️ Автоторговля остановлена: достигнут лимит {max_trades} сделок в день.")
                    continue

                # 3. Получаем ключи и позиции
                keys = await list_exchange_keys(user_id)
                if not keys: continue
                k = keys[0]
                
                pos_res = await fetch_positions(user_id, k["exchange"], k["mode"], k["market"])
                positions = pos_res.get("positions", []) if pos_res.get("ok") else []
                open_symbols = [p["symbol"] for p in positions]

                if len(positions) >= 3:
                    continue

                # 4. Активные стратегии
                strats = await list_strategies(user_id)
                active_strats = [s for s in strats if s["is_active"]]
                if not active_strats: continue

                for s in active_strats:
                    if s["symbol"] in open_symbols:
                        continue

                    df = await fetch_ohlcv(s["symbol"], s["timeframe"], limit=100)
                    if df.empty or len(df) < 30: continue

                    df = compute_indicators(df, s["indicators"])
                    row = df.iloc[-2]
                    prev = df.iloc[-3]
                    
                    if evaluate_rules(row, prev, s["entry_rules"], s.get("logic", "AND")):
                        price = float(row["close"])
                        risk = s.get("risk", {})
                        sl_pct = float(risk.get("stop_loss_pct", 2))
                        tp_pct = float(risk.get("take_profit_pct", 4))
                        risk_per_trade = float(risk.get("risk_per_trade_pct", 1))
                        
                        sl = price * (1 - sl_pct/100)
                        tp = price * (1 + tp_pct/100)
                        leverage = 3
                        
                        dep_limit = float(user.get("deposit_limit", 100))
                        risk_usdt = dep_limit * risk_per_trade / 100
                        position_usdt = risk_usdt / (sl_pct / 100)
                        amount = position_usdt / price

                        check = await check_trade(
                            user_id=user_id, symbol=s["symbol"], side="buy",
                            amount=amount, price=price, leverage=leverage, risk_pct=risk_per_trade,
                            has_sl=True, has_tp=True
                        )
                        if not check.get("ok"): continue

                        res = await place_order(
                            user_id=user_id, exchange_name=k["exchange"],
                            symbol=s["symbol"], side="buy", amount=round(amount, 4),
                            price=price, leverage=leverage, sl=round(sl, 2), tp=round(tp, 2),
                            mode=k["mode"], market=k["market"]
                        )
                        
                        if res.get("ok"):
                            await save_order(
                                user_id=user_id, exchange=k["exchange"], mode=k["mode"], market=k["market"],
                                symbol=s["symbol"], side="buy", amount=round(amount, 4),
                                entry_price=price, sl=sl, tp=tp, leverage=leverage, order_id=str(res["order"].get("id"))
                            )
                            await bot.send_message(user_id, f"🤖 <b>Автоторговля</b>\n\nОткрыта сделка по стратегии <b>{s['name']}</b>\nТикер: {s['symbol']}\nВход: {price:.2f}\nSL: {sl:.2f} | TP: {tp:.2f}", parse_mode="HTML")
                            
        except Exception as e:
            logger.error(f"AutoTrade error: {e}")
        
        await asyncio.sleep(60)