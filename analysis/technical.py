"""
analysis/technical.py - Multi-timeframe technical analysis engine
"""
import numpy as np
import pandas as pd
from typing import Optional
from loguru import logger


# ─────────────────────────────────────────
# INDICATOR CALCULATIONS
# ─────────────────────────────────────────
def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    vol = df["Volume"].replace(0, np.nan)
    cumtp = (tp * vol).cumsum()
    cumvol = vol.cumsum()
    return cumtp / cumvol


def calc_bollinger(df: pd.DataFrame, period: int = 20, std: float = 2.0):
    mid = df["Close"].rolling(period).mean()
    sigma = df["Close"].rolling(period).std()
    return mid + std * sigma, mid, mid - std * sigma


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_dm[plus_dm < (-low.diff()).clip(lower=0)] = 0
    minus_dm[minus_dm < high.diff().clip(lower=0)] = 0

    atr = calc_atr(df, period)
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.rolling(period).mean()


def calc_pivot_points(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    pivot = (last["High"] + last["Low"] + last["Close"]) / 3
    r1 = 2 * pivot - last["Low"]
    r2 = pivot + (last["High"] - last["Low"])
    r3 = last["High"] + 2 * (pivot - last["Low"])
    s1 = 2 * pivot - last["High"]
    s2 = pivot - (last["High"] - last["Low"])
    s3 = last["Low"] - 2 * (last["High"] - pivot)
    return {"PP": pivot, "R1": r1, "R2": r2, "R3": r3, "S1": s1, "S2": s2, "S3": s3}


# ─────────────────────────────────────────
# MARKET STRUCTURE
# ─────────────────────────────────────────
def detect_market_structure(df: pd.DataFrame, lookback: int = 5) -> dict:
    """Detect HH/HL/LH/LL, BoS, CHoCH"""
    if len(df) < lookback * 3:
        return {"structure": "UNKNOWN", "bos": False, "choch": False}

    highs = df["High"].rolling(lookback).max()
    lows = df["Low"].rolling(lookback).min()

    recent_high = highs.iloc[-1]
    prev_high = highs.iloc[-lookback - 1]
    recent_low = lows.iloc[-1]
    prev_low = lows.iloc[-lookback - 1]

    hh = recent_high > prev_high
    hl = recent_low > prev_low
    lh = recent_high < prev_high
    ll = recent_low < prev_low

    if hh and hl:
        structure = "BULLISH"
    elif lh and ll:
        structure = "BEARISH"
    else:
        structure = "RANGING"

    # Break of Structure: price breaks last swing
    last_close = df["Close"].iloc[-1]
    bos = last_close > highs.iloc[-lookback] or last_close < lows.iloc[-lookback]

    # Change of Character: opposite break
    choch = (structure == "BULLISH" and last_close < lows.iloc[-lookback]) or \
            (structure == "BEARISH" and last_close > highs.iloc[-lookback])

    return {
        "structure": structure,
        "bos": bos,
        "choch": choch,
        "hh": hh, "hl": hl, "lh": lh, "ll": ll,
    }


# ─────────────────────────────────────────
# ORDER BLOCKS & FAIR VALUE GAPS
# ─────────────────────────────────────────
def find_order_blocks(df: pd.DataFrame, n: int = 3) -> list:
    """Find the last N bullish and bearish order blocks"""
    blocks = []
    for i in range(2, len(df) - 1):
        prev = df.iloc[i - 1]
        curr = df.iloc[i]
        nxt = df.iloc[i + 1]

        # Bullish OB: bearish candle before a strong bullish move
        if (prev["Close"] < prev["Open"] and
                nxt["Close"] > nxt["Open"] and
                nxt["Close"] > prev["High"]):
            blocks.append({
                "type": "BULLISH_OB",
                "top": prev["High"],
                "bottom": prev["Low"],
                "idx": i,
            })

        # Bearish OB: bullish candle before a strong bearish move
        if (prev["Close"] > prev["Open"] and
                nxt["Close"] < nxt["Open"] and
                nxt["Close"] < prev["Low"]):
            blocks.append({
                "type": "BEARISH_OB",
                "top": prev["High"],
                "bottom": prev["Low"],
                "idx": i,
            })

    return blocks[-n:] if blocks else []


def find_fvg(df: pd.DataFrame) -> list:
    """Find Fair Value Gaps (imbalances)"""
    fvgs = []
    for i in range(1, len(df) - 1):
        prev = df.iloc[i - 1]
        nxt = df.iloc[i + 1]
        if nxt["Low"] > prev["High"]:  # Bullish FVG
            fvgs.append({"type": "BULLISH_FVG", "top": nxt["Low"], "bottom": prev["High"], "idx": i})
        elif nxt["High"] < prev["Low"]:  # Bearish FVG
            fvgs.append({"type": "BEARISH_FVG", "top": prev["Low"], "bottom": nxt["High"], "idx": i})
    return fvgs[-5:]


# ─────────────────────────────────────────
# KEY LEVELS
# ─────────────────────────────────────────
def extract_key_levels(df_d1: pd.DataFrame, df_h4: Optional[pd.DataFrame] = None) -> dict:
    """Extract daily/weekly/monthly highs-lows and supply/demand zones"""
    if df_d1 is None or len(df_d1) < 5:
        return {}

    levels = {
        "daily_high": float(df_d1.iloc[-1]["High"]),
        "daily_low": float(df_d1.iloc[-1]["Low"]),
        "prev_day_high": float(df_d1.iloc[-2]["High"]),
        "prev_day_low": float(df_d1.iloc[-2]["Low"]),
    }

    if len(df_d1) >= 5:
        week_slice = df_d1.iloc[-5:]
        levels["weekly_high"] = float(week_slice["High"].max())
        levels["weekly_low"] = float(week_slice["Low"].min())

    if len(df_d1) >= 22:
        month_slice = df_d1.iloc[-22:]
        levels["monthly_high"] = float(month_slice["High"].max())
        levels["monthly_low"] = float(month_slice["Low"].min())

    pivots = calc_pivot_points(df_d1)
    levels.update(pivots)

    if df_h4 is not None and len(df_h4) >= 20:
        swing_highs = df_h4["High"].rolling(5).max().dropna()
        swing_lows = df_h4["Low"].rolling(5).min().dropna()
        levels["swing_high"] = float(swing_highs.iloc[-1])
        levels["swing_low"] = float(swing_lows.iloc[-1])

    return levels


# ─────────────────────────────────────────
# SINGLE TIMEFRAME ANALYSIS
# ─────────────────────────────────────────
def analyze_timeframe(df: pd.DataFrame, timeframe: str) -> dict:
    """Full analysis for a single timeframe"""
    if df is None or len(df) < 50:
        return {"trend": "UNKNOWN", "timeframe": timeframe}

    close = df["Close"]
    ema50 = calc_ema(close, 50)
    ema200 = calc_ema(close, 200) if len(df) >= 200 else ema50

    last_close = float(close.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    last_ema200 = float(ema200.iloc[-1])

    rsi = calc_rsi(close)
    last_rsi = float(rsi.iloc[-1])

    atr = calc_atr(df)
    last_atr = float(atr.iloc[-1])

    adx = calc_adx(df)
    last_adx = float(adx.iloc[-1]) if not adx.empty else 0

    vol = df["Volume"]
    avg_vol = float(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else 1
    last_vol = float(vol.iloc[-1])
    vol_spike = last_vol > avg_vol * 1.5

    if last_ema50 > last_ema200 and last_close > last_ema50:
        trend = "BULLISH"
    elif last_ema50 < last_ema200 and last_close < last_ema50:
        trend = "BEARISH"
    else:
        trend = "RANGING"

    structure = detect_market_structure(df)
    order_blocks = find_order_blocks(df)
    fvgs = find_fvg(df)

    vwap = float(calc_vwap(df).iloc[-1]) if len(df) >= 20 else last_close
    bb_upper, bb_mid, bb_lower = calc_bollinger(df)

    return {
        "timeframe": timeframe,
        "trend": trend,
        "close": last_close,
        "ema50": last_ema50,
        "ema200": last_ema200,
        "rsi": last_rsi,
        "atr": last_atr,
        "adx": last_adx,
        "vwap": vwap,
        "volume_spike": vol_spike,
        "structure": structure,
        "order_blocks": order_blocks,
        "fvgs": fvgs,
        "bb_upper": float(bb_upper.iloc[-1]),
        "bb_mid": float(bb_mid.iloc[-1]),
        "bb_lower": float(bb_lower.iloc[-1]),
    }
