"""
Data fetcher — priority order:
  1. Zerodha Kite Connect  (real-time, official NSE feed)
  2. Yahoo Finance / yfinance  (fallback, free)
  3. Mock data generator  (offline demo)
"""

import yfinance as yf
import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ── NSE stock registry ────────────────────────────────────────────────────────
NSE_STOCKS = {
    "RELIANCE.NS": "Reliance Industries",
    "TCS.NS": "Tata Consultancy Services",
    "HDFCBANK.NS": "HDFC Bank",
    "INFY.NS": "Infosys",
    "ICICIBANK.NS": "ICICI Bank",
    "HINDUNILVR.NS": "Hindustan Unilever",
    "SBIN.NS": "State Bank of India",
    "BHARTIARTL.NS": "Bharti Airtel",
    "ITC.NS": "ITC Limited",
    "KOTAKBANK.NS": "Kotak Mahindra Bank",
    "LT.NS": "Larsen & Toubro",
    "AXISBANK.NS": "Axis Bank",
    "ASIANPAINT.NS": "Asian Paints",
    "MARUTI.NS": "Maruti Suzuki",
    "SUNPHARMA.NS": "Sun Pharmaceutical",
    "TITAN.NS": "Titan Company",
    "WIPRO.NS": "Wipro",
    "BAJFINANCE.NS": "Bajaj Finance",
    "NESTLEIND.NS": "Nestle India",
    "ULTRACEMCO.NS": "UltraTech Cement",
    "POWERGRID.NS": "Power Grid Corp",
    "NTPC.NS": "NTPC Limited",
    "ONGC.NS": "ONGC",
    "ADANIENT.NS": "Adani Enterprises",
    "TATAMOTORS.NS": "Tata Motors",
    "TATASTEEL.NS": "Tata Steel",
    "TECHM.NS": "Tech Mahindra",
    "HCLTECH.NS": "HCL Technologies",
    "BAJAJFINSV.NS": "Bajaj Finserv",
    "DIVISLAB.NS": "Divi's Laboratories",
}

PERIOD_FOR_INTERVAL = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "730d",
    "1d": "2y",
    "1wk": "5y",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def get_stock_data(symbol: str, interval: str = "1d", period: Optional[str] = None) -> pd.DataFrame:
    """Fetch OHLCV candle data. Tries Kite → yfinance → mock, in that order."""
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    # 1. Kite Connect
    df = _kite_data(symbol, interval)
    if df is not None and not df.empty:
        return df

    # 2. yfinance
    df = _yfinance_data(symbol, interval, period)
    if df is not None and not df.empty:
        return df

    # 3. Mock fallback
    logger.info(f"Using mock data for {symbol} [{interval}]")
    return _get_mock_data(symbol, interval)


def get_realtime_quote(symbol: str) -> dict:
    """Get current price quote. Tries Kite → yfinance → mock."""
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    # 1. Kite Connect
    quote = _kite_quote(symbol)
    if quote:
        return quote

    # 2. yfinance
    quote = _yfinance_quote(symbol)
    if quote:
        return quote

    # 3. Mock fallback
    try:
        from mock_data import generate_mock_quote
        return generate_mock_quote(symbol)
    except Exception:
        return {"symbol": symbol, "error": "All data sources failed"}


def get_all_stocks() -> list:
    return [{"symbol": sym, "name": name} for sym, name in NSE_STOCKS.items()]


def search_stock(query: str) -> list:
    query = query.upper()
    return [
        {"symbol": sym, "name": name}
        for sym, name in NSE_STOCKS.items()
        if query in sym or query in name.upper()
    ]


# ── Kite helpers ───────────────────────────────────────────────────────────────

def _kite_data(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        import kite_config
        if not kite_config.is_authenticated():
            return None
        from kite_fetcher import kite_historical
        return kite_historical(symbol, interval)
    except Exception as e:
        logger.debug(f"Kite historical skipped for {symbol}: {e}")
        return None


def _kite_quote(symbol: str) -> Optional[dict]:
    try:
        import kite_config
        if not kite_config.is_authenticated():
            return None
        from kite_fetcher import kite_quote
        return kite_quote(symbol)
    except Exception as e:
        logger.debug(f"Kite quote skipped for {symbol}: {e}")
        return None


# ── yfinance helpers ───────────────────────────────────────────────────────────

def _yfinance_data(symbol: str, interval: str, period: Optional[str]) -> Optional[pd.DataFrame]:
    if period is None:
        period = PERIOD_FOR_INTERVAL.get(interval, "1y")
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "timestamp"
        return df.dropna()
    except Exception as e:
        logger.debug(f"yfinance data failed for {symbol}: {e}")
        return None


def _yfinance_quote(symbol: str) -> Optional[dict]:
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        hist = ticker.history(period="2d", interval="1d")
        if hist.empty:
            return None

        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else 0.0
        current = float(info.get("lastPrice") or 0)
        if current == 0:
            current = float(hist["Close"].iloc[-1])

        change = current - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0

        return {
            "symbol": symbol,
            "company_name": NSE_STOCKS.get(symbol, symbol.replace(".NS", "")),
            "current_price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "day_high": round(float(info.get("dayHigh") or current), 2),
            "day_low": round(float(info.get("dayLow") or current), 2),
            "volume": int(info.get("lastVolume") or 0),
            "year_high": round(float(info.get("yearHigh") or 0), 2),
            "year_low": round(float(info.get("yearLow") or 0), 2),
            "market_cap": int(info.get("marketCap") or 0),
            "_source": "yfinance",
        }
    except Exception as e:
        logger.debug(f"yfinance quote failed for {symbol}: {e}")
        return None


# ── Mock helper ────────────────────────────────────────────────────────────────

def _get_mock_data(symbol: str, interval: str) -> pd.DataFrame:
    try:
        from mock_data import generate_mock_ohlcv
        n_map = {"1m": 200, "5m": 200, "15m": 200, "30m": 150, "1h": 200, "1d": 500, "1wk": 260}
        return generate_mock_ohlcv(symbol, n=n_map.get(interval, 252), interval=interval)
    except Exception as e:
        logger.error(f"Mock data generation failed: {e}")
        return pd.DataFrame()
