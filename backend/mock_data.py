"""
Mock data generator for offline / demo mode.
Generates realistic OHLCV data for NSE stocks when Yahoo Finance is unreachable.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_mock_ohlcv(symbol: str, n: int = 252, interval: str = "1d") -> pd.DataFrame:
    """Generate realistic OHLCV data using a random walk with momentum."""
    rng = np.random.default_rng(seed=hash(symbol) % (2**31))

    # Base price per symbol
    seed_prices = {
        "RELIANCE.NS": 2850, "TCS.NS": 3920, "HDFCBANK.NS": 1650,
        "INFY.NS": 1820, "ICICIBANK.NS": 1120, "HINDUNILVR.NS": 2650,
        "SBIN.NS": 780, "BHARTIARTL.NS": 1580, "ITC.NS": 465,
        "KOTAKBANK.NS": 1890, "LT.NS": 3450, "AXISBANK.NS": 1180,
    }
    base = seed_prices.get(symbol, 1000)

    # Generate daily log-returns (drift + volatility)
    daily_vol = 0.015
    drift = 0.0003
    returns = rng.normal(drift, daily_vol, n)

    # Add occasional momentum bursts
    burst_idx = rng.choice(n, size=n // 20, replace=False)
    returns[burst_idx] *= rng.choice([-3, 3], size=len(burst_idx))

    prices = base * np.exp(np.cumsum(returns))

    # Build OHLCV
    opens, highs, lows, closes, vols = [], [], [], [], []
    prev = prices[0]
    for i, close in enumerate(prices):
        o = prev * (1 + rng.normal(0, 0.003))
        h = max(o, close) * (1 + abs(rng.normal(0, 0.005)))
        l = min(o, close) * (1 - abs(rng.normal(0, 0.005)))
        vol = int(abs(rng.normal(1e6, 3e5)))
        opens.append(round(o, 2))
        highs.append(round(h, 2))
        lows.append(round(l, 2))
        closes.append(round(close, 2))
        vols.append(vol)
        prev = close

    # Build datetime index based on interval
    end = datetime.now().replace(hour=15, minute=30, second=0, microsecond=0)
    if interval == "1d":
        dates = pd.bdate_range(end=end, periods=n)
    elif interval == "1wk":
        dates = pd.date_range(end=end, periods=n, freq="W-FRI")
    elif interval == "1h":
        dates = pd.date_range(end=end, periods=n, freq="h")
    elif interval in ("15m", "30m"):
        freq = "15min" if interval == "15m" else "30min"
        dates = pd.date_range(end=end, periods=n, freq=freq)
    else:  # 5m, 1m
        freq = "5min" if interval == "5m" else "1min"
        dates = pd.date_range(end=end, periods=n, freq=freq)

    df = pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": vols
    }, index=dates[:n])
    df.index.name = "timestamp"
    return df


def generate_mock_quote(symbol: str) -> dict:
    """Generate a realistic mock quote."""
    from data_fetcher import NSE_STOCKS
    df = generate_mock_ohlcv(symbol, n=5)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    change = last["close"] - prev["close"]
    return {
        "symbol": symbol,
        "company_name": NSE_STOCKS.get(symbol, symbol.replace(".NS", "")),
        "current_price": round(last["close"], 2),
        "prev_close": round(prev["close"], 2),
        "change": round(change, 2),
        "change_pct": round(change / prev["close"] * 100, 2),
        "day_high": round(last["high"], 2),
        "day_low": round(last["low"], 2),
        "volume": int(last["volume"]),
        "year_high": round(df["high"].max(), 2),
        "year_low": round(df["low"].min(), 2),
        "market_cap": 0,
        "_demo": True,
    }
