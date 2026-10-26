import io
import logging
import mplfinance as mpf
import pandas as pd
from services.market_data import fetch_ohlcv
from services.indicators import ema, rsi

logger = logging.getLogger(__name__)

async def generate_chart_image(symbol: str, timeframe: str = "1h") -> io.BytesIO | None:
    """Генерирует красивый график с EMA и RSI."""
    try:
        df = await fetch_ohlcv(symbol, timeframe, limit=100)
        if df is None or df.empty:
            return None

        df.set_index("ts", inplace=True)
        
        df["EMA_50"] = ema(df["close"], 50)
        df["EMA_200"] = ema(df["close"], 200)
        df["RSI"] = rsi(df["close"], 14)

        mc = mpf.make_marketcolors(up='#22c55e', down='#ef4444', edge='inherit', wick='inherit', volume='in')
        style = mpf.make_mpf_style(marketcolors=mc, base_mpf_style='nightclouds', gridstyle=':', y_on_right=True)

        apds = [
            mpf.make_addplot(df["EMA_50"], color='#3b82f6', width=1.5, label='EMA 50'),
            mpf.make_addplot(df["EMA_200"], color='#eab308', width=1.5, label='EMA 200'),
            mpf.make_addplot(df["RSI"], panel=1, color='#a855f7', width=1.2, ylabel='RSI')
        ]

        buf = io.BytesIO()
        mpf.plot(
            df, type='candle', style=style, addplot=apds,
            volume=True, panel_ratios=(4, 1.5),
            title=f"\n{symbol} - {timeframe}",
            savefig=dict(fname=buf, dpi=120, bbox_inches='tight')
        )
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Ошибка генерации графика: {e}")
        return None