import logging
import time
import requests
import pandas as pd

logger = logging.getLogger(__name__)

COIN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2",
    "DOT": "polkadot", "MATIC": "matic-network", "LTC": "litecoin", "LINK": "chainlink",
}

_cache = {}
_CACHE_TTL = 300  # 5 минут

def _to_coingecko_id(symbol: str) -> str:
    base = symbol.split("/")[0].upper()
    return COIN_MAP.get(base, base.lower())

async def fetch_ohlcv(symbol, timeframe="1h", limit=1000, exchange_name=None):
    coin_id = _to_coingecko_id(symbol)
    cache_key = f"{coin_id}_{timeframe}"
    
    # Проверяем кэш
    if cache_key in _cache:
        ts, df = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return df.copy()
    
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "30"}
    
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            logger.warning(f"CoinGecko rate limit, returning empty for {coin_id}")
            return pd.DataFrame()
        if r.status_code != 200:
            logger.error(f"CoinGecko error: {r.status_code}")
            return pd.DataFrame()
            
        data = r.json()
        df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df["volume"] = 0
        
        _cache[cache_key] = (time.time(), df)
        return df.copy()
    except Exception as e:
        logger.error(f"fetch_ohlcv error: {e}")
        return pd.DataFrame()