import logging
import pandas as pd
import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


async def fetch_ohlcv(symbol, timeframe="1h", limit=1000, exchange_name="binance"):
    exchange = getattr(ccxt, exchange_name)({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    try:
        candles = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        logger.error(f"fetch_ohlcv error: {e}")
        candles = []
    finally:
        await exchange.close()

    if not candles:
        return pd.DataFrame()

    df = pd.DataFrame(candles, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df