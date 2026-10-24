import logging
import ccxt.async_support as ccxt
from config import (
    BINANCE_TESTNET_KEY, BINANCE_TESTNET_SECRET,
    BYBIT_TESTNET_KEY, BYBIT_TESTNET_SECRET,
)

logger = logging.getLogger(__name__)


def get_exchange(name: str, mode: str = "testnet"):
    name = name.lower()
    if name == "binance":
        ex = ccxt.binance({
            "apiKey": BINANCE_TESTNET_KEY,
            "secret": BINANCE_TESTNET_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        if mode == "testnet":
            ex.set_sandbox_mode(True)
        return ex
    if name == "bybit":
        ex = ccxt.bybit({
            "apiKey": BYBIT_TESTNET_KEY,
            "secret": BYBIT_TESTNET_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        if mode == "testnet":
            ex.set_sandbox_mode(True)
        return ex
    raise ValueError(f"Биржа не поддерживается: {name}")


async def place_order(exchange_name: str, symbol: str, side: str, amount: float, price: float, leverage: float, sl: float, tp: float, mode: str = "testnet") -> dict:
    ex = get_exchange(exchange_name, mode)
    try:
        await ex.load_markets()
        try:
            await ex.set_leverage(int(leverage), symbol)
        except Exception as e:
            logger.warning(f"set_leverage: {e}")

        params = {}
        if sl:
            params["stopLoss"] = {"triggerPrice": sl}
        if tp:
            params["takeProfit"] = {"triggerPrice": tp}

        order = await ex.create_order(
            symbol=symbol,
            type="market",
            side=side,
            amount=amount,
            params=params,
        )
        return {"ok": True, "order": order}
    except Exception as e:
        logger.error(f"place_order: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        await ex.close()


async def get_balance(exchange_name: str, mode: str = "testnet") -> dict:
    ex = get_exchange(exchange_name, mode)
    try:
        bal = await ex.fetch_balance()
        return {"ok": True, "balance": bal}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        await ex.close()