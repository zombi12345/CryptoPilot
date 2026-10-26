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
    ef = ema(series, fast)
    es = ema(series, slow)
    m = ef - es
    s = ema(m, signal)
    return m, s, m - s


def atr(high, low, close, period=14):
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def bollinger(series, period=20, std=2):
    mid = sma(series, period)
    sd = series.rolling(period).std()
    return mid + std * sd, mid, mid - std * sd


def stoch(high, low, close, period=14):
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, 1e-10)


def compute_indicators(df, specs):
    for spec in specs:
        name = spec.get("name", "").upper()
        if name == "RSI":
            p = int(spec.get("period", 14))
            df[f"RSI_{p}"] = rsi(df["close"], p).shift(1)
        elif name == "EMA":
            p = int(spec.get("period", 20))
            df[f"EMA_{p}"] = ema(df["close"], p).shift(1)
        elif name == "SMA":
            p = int(spec.get("period", 20))
            df[f"SMA_{p}"] = sma(df["close"], p).shift(1)
        elif name == "MACD":
            fast = int(spec.get("fast", 12))
            slow = int(spec.get("slow", 26))
            sig = int(spec.get("signal", 9))
            m, s, h = macd(df["close"], fast, slow, sig)
            df[f"MACD_{fast}_{slow}_{sig}"] = m.shift(1)
            df[f"MACD_{fast}_{slow}_{sig}_SIGNAL"] = s.shift(1)
        elif name == "ATR":
            p = int(spec.get("period", 14))
            df[f"ATR_{p}"] = atr(df["high"], df["low"], df["close"], p).shift(1)
        elif name == "BB":
            p = int(spec.get("period", 20))
            sd = int(spec.get("std", 2))
            u, m, l = bollinger(df["close"], p, sd)
            df[f"BB_{p}_{sd}_UPPER"] = u.shift(1)
            df[f"BB_{p}_{sd}_MID"] = m.shift(1)
            df[f"BB_{p}_{sd}_LOWER"] = l.shift(1)
        elif name == "STOCH":
            p = int(spec.get("period", 14))
            df[f"STOCH_{p}"] = stoch(df["high"], df["low"], df["close"], p).shift(1)
    return df