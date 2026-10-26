import logging
import ccxt.async_support as ccxt
from services.crypto import decrypt
from database import get_exchange_keys

logger = logging.getLogger(__name__)

async def _get_creds(user_id, exchange_name, mode, market):
    keys = await get_exchange_keys(user_id, exchange_name, mode, market)
    if not keys:
        return None
    return decrypt(keys["api_key_enc"]), decrypt(keys["secret_enc"])

async def _get_exchange(user_id, exchange_name, mode, market):
    creds = await _get_creds(user_id, exchange_name, mode, market)
    if not creds:
        return None, "Нет API-ключей"
    
    api_key, secret = creds
    default_type = "future" if market == "futures" else "spot"
    
    ex = getattr(ccxt, exchange_name)({
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": True,
        "options": {"defaultType": default_type},
    })
    
    if mode == "testnet":
        if exchange_name.lower() == "binance":
            ex.enable_demo_trading(True)
        else:
            ex.set_sandbox_mode(True)
    
    return ex, None

async def place_order(user_id, exchange_name, symbol, side, amount, price, leverage, sl, tp, mode="testnet", market="futures"):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        await ex.load_markets()
        if market == "futures":
            try:
                await ex.set_leverage(int(leverage), symbol)
            except Exception as e:
                logger.warning(f"set_leverage: {e}")

        order = await ex.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=amount,
        )
        
        close_side = "sell" if side == "buy" else "buy"
        sl_id = None
        tp_id = None
        
        if market == "futures" and sl:
            try:
                sl_params = {"stopPrice": sl, "reduceOnly": True}
                sl_order = await ex.create_order(symbol, "STOP_MARKET", close_side, amount, None, sl_params)
                sl_id = sl_order.get("id")
            except Exception as e:
                logger.warning(f"SL order failed: {e}")
                
        if market == "futures" and tp:
            try:
                tp_params = {"stopPrice": tp, "reduceOnly": True}
                tp_order = await ex.create_order(symbol, "TAKE_PROFIT_MARKET", close_side, amount, None, tp_params)
                tp_id = tp_order.get("id")
            except Exception as e:
                logger.warning(f"TP order failed: {e}")

        return {"ok": True, "order": order, "sl_id": sl_id, "tp_id": tp_id}
    except Exception as e:
        logger.error(f"place_order: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass

async def fetch_positions(user_id, exchange_name, mode="testnet", market="futures"):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        await ex.load_markets()
        
        bal = await ex.fetch_balance()
        usdt = float(bal.get("total", {}).get("USDT", 0))
        
        positions = await ex.fetch_positions()
        open_orders = []
        try:
            open_orders = await ex.fetch_open_orders()
        except Exception:
            pass

        open_positions = []
        for p in positions:
            contracts = float(p.get("contracts") or 0)
            if contracts > 0:
                symbol = p.get("symbol")
                
                sl = None
                tp = None
                for o in open_orders:
                    if o.get("symbol") == symbol:
                        otype = o.get("type", "").lower()
                        oinfo = o.get("info", {})
                        if "stop" in otype or oinfo.get("type") == "STOP_MARKET":
                            sl = o.get("stopPrice") or o.get("price")
                        elif "take" in otype or oinfo.get("type") == "TAKE_PROFIT_MARKET":
                            tp = o.get("stopPrice") or o.get("price")
                
                if not sl and p.get("stopLossPrice"): sl = p.get("stopLossPrice")
                if not tp and p.get("takeProfitPrice"): tp = p.get("takeProfitPrice")

                lev = p.get("leverage") or p.get("info", {}).get("leverage") or "3"
                
                entry = float(p.get("entryPrice") or 0)
                mark = float(p.get("markPrice") or 0)
                
                roi = 0.0
                if entry > 0:
                    if p.get("side") == "long":
                        roi = (mark - entry) / entry * 100 * float(lev)
                    else:
                        roi = (entry - mark) / entry * 100 * float(lev)

                open_positions.append({
                    "symbol": symbol,
                    "side": p.get("side"),
                    "contracts": contracts,
                    "entry": entry,
                    "mark": mark,
                    "pnl": float(p.get("unrealizedPnl") or 0),
                    "leverage": lev,
                    "sl": sl,
                    "tp": tp,
                    "roi": roi,
                })
        return {"ok": True, "positions": open_positions, "balance": usdt}
    except Exception as e:
        logger.error(f"fetch_positions: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass

async def close_position(user_id, exchange_name, symbol, side, amount, mode="testnet", market="futures"):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        await ex.load_markets()
        close_side = "sell" if side == "long" else "buy"
        
        params = {"reduceOnly": True}
        order = await ex.create_order(
            symbol=symbol,
            type="market",
            side=close_side,
            amount=amount,
            params=params,
        )
        return {"ok": True, "order": order}
    except Exception as e:
        logger.error(f"close_position: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass

async def test_keys(user_id, exchange_name, mode, market):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        bal = await ex.fetch_balance()
        total = bal.get("total", {})
        return {"ok": True, "balance": total}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass

async def fetch_balance_full(user_id, exchange_name, mode="testnet", market="futures"):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        bal = await ex.fetch_balance()
        total = bal.get("total", {})
        coins = []
        for coin, amount in total.items():
            if amount and float(amount) > 0:
                coins.append({"coin": coin, "amount": float(amount)})
        coins.sort(key=lambda x: (x["coin"] != "USDT", -x["amount"]))
        return {"ok": True, "coins": coins}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass

async def transfer_spot_to_futures(user_id, exchange_name, mode, market, asset="USDT", amount=None):
    ex, err = await _get_exchange(user_id, exchange_name, mode, market)
    if err:
        return {"ok": False, "error": err}

    try:
        if amount is None:
            bal = await ex.fetch_balance()
            amount = float(bal.get("free", {}).get(asset, 0))
            if amount <= 0:
                return {"ok": False, "error": f"Нет свободного {asset} на споте"}

        res = await ex.transfer(asset, amount, "spot", "future")
        return {"ok": True, "amount": amount, "result": res}
    except Exception as e:
        logger.error(f"transfer_spot_to_futures: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            await ex.close()
        except Exception:
            pass