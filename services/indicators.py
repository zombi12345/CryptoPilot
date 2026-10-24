import logging
import pandas as pd

logger = logging.getLogger(__name__)


def sma(series, period):
    return series.rolling(period).mean()


def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - 100 / (1 + rs)


def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(high, low, close, period=14):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def bollinger(series, period=20, std=2):
    mid = sma(series, period)
    stdev = series.rolling(period).std()
    upper = mid + std * stdev
    lower = mid - std * stdev
    return upper, mid, lower


def compute_indicators(df, specs):
    """
    specs: [{"name": "RSI", "period": 14}, {"name": "EMA", "period": 50}, ...]
    Возвращает df с колонками вида RSI_14, EMA_50, MACD_12_26_9, BB_20_2_UPPER и т.д.
    Все индикаторы сдвинуты на 1 свечу (shift(1)), чтобы не было look-ahead bias.
    """
    for spec in specs:
        name = spec.get("name", "").upper()
        if name == "RSI":
            period = int(spec.get("period", 14))
            df[f"RSI_{period}"] = rsi(df["close"], period).shift(1)
        elif name == "EMA":
            period = int(spec.get("period", 20))
            df[f"EMA_{period}"] = ema(df["close"], period).shift(1)
        elif name == "SMA":
            period = int(spec.get("period", 20))
            df[f"SMA_{period}"] = sma(df["close"], period).shift(1)
        elif name == "MACD":
            fast = int(spec.get("fast", 12))
            slow = int(spec.get("slow", 26))
            sig = int(spec.get("signal", 9))
            m, s, h = macd(df["close"], fast, slow, sig)
            df[f"MACD_{fast}_{slow}_{sig}"] = m.shift(1)
            df[f"MACD_{fast}_{slow}_{sig}_SIGNAL"] = s.shift(1)
        elif name == "ATR":
            period = int(spec.get("period", 14))
            df[f"ATR_{period}"] = atr(df["high"], df["low"], df["close"], period).shift(1)
        elif name == "BB":
            period = int(spec.get("period", 20))
            std = int(spec.get("std", 2))
            u, m, l = bollinger(df["close"], period, std)
            df[f"BB_{period}_{std}_UPPER"] = u.shift(1)
            df[f"BB_{period}_{std}_MID"] = m.shift(1)
            df[f"BB_{period}_{std}_LOWER"] = l.shift(1)
    return df