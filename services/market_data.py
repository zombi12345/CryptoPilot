import logging
import requests
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Маппинг тикеров (BTC/USDT -> bitcoin)
COIN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "BNB": "binancecoin",
    "XRP": "ripple", "DOGE": "dogecoin", "ADA": "cardano", "AVAX": "avalanche-2",
    "DOT": "polkadot", "MATIC": "matic-network", "LTC": "litecoin", "LINK": "chainlink",
}

def _to_coingecko_id(symbol: str) -> str:
    base = symbol.split("/")[0].upper()
    return COIN_MAP.get(base, base.lower())

async def fetch_ohlcv(symbol, timeframe="1h", limit=1000, exchange_name=None):
    """Загружает свечи с CoinGecko (бесплатно, без ключа)."""
    coin_id = _to_coingecko_id(symbol)
    
    # CoinGecko даёт OHLC по дням (1d), для часовых надо использовать market_chart
    # Упрощаем: берём дневные свечи
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": "30"}  # 30 дней дневных свечей
    
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            logger.error(f"CoinGecko error: {r.status_code}")
            return pd.DataFrame()
            
        data = r.json()
        # CoinGecko OHLC: [timestamp, open, high, low, close]
        df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        df["volume"] = 0  # CoinGecko не даёт объёмы в этом эндпоинте
        return df
    except Exception as e:
        logger.error(f"fetch_ohlcv error: {e}")
        return pd.DataFrame()