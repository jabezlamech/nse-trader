import yfinance as yf
import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Popular NSE stocks with company names
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

INTERVALS = {
    "1m": "1 minute",
    "5m": "5 minutes",
    "15m": "15 minutes",
    "30m": "30 minutes",
    "1h": "1 hour",
    "1d": "1 day",
    "1wk": "1 week",
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


def get_stock_data(symbol: str, interval: str = "1d", period: Optional[str] = None) -> pd.DataFrame:
    """Fetch OHLCV data for an NSE stock. Falls back to mock data if network unavailable."""
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    if period is None:
        period = PERIOD_FOR_INTERVAL.get(interval, "1y")

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            logger.warning(f"No data returned for {symbol}, using mock data")
            return _get_mock_data(symbol, interval)

        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "timestamp"
        df = df.dropna()
        return df
    except Exception as e:
        logger.warning(f"Network error for {symbol} ({e}), using mock data")
        return _get_mock_data(symbol, interval)


def _get_mock_data(symbol: str, interval: str) -> pd.DataFrame:
    """Return mock OHLCV data for demo/offline mode."""
    try:
        from mock_data import generate_mock_ohlcv
        n_map = {"1m": 200, "5m": 200, "15m": 200, "30m": 150, "1h": 200, "1d": 500, "1wk": 260}
        n = n_map.get(interval, 252)
        return generate_mock_ohlcv(symbol, n=n, interval=interval)
    except Exception as e:
        logger.error(f"Mock data generation failed: {e}")
        return pd.DataFrame()


def get_realtime_quote(symbol: str) -> dict:
    """Get current price info for a stock. Falls back to mock data if network unavailable."""
    if not symbol.endswith(".NS"):
        symbol = symbol + ".NS"

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        hist = ticker.history(period="2d", interval="1d")

        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else 0.0
        current = float(info.get("lastPrice", 0) or info.get("regularMarketPreviousClose", 0))

        if current == 0 and not hist.empty:
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
            "day_high": round(float(info.get("dayHigh", current) or current), 2),
            "day_low": round(float(info.get("dayLow", current) or current), 2),
            "volume": int(info.get("lastVolume", 0) or 0),
            "year_high": round(float(info.get("yearHigh", 0) or 0), 2),
            "year_low": round(float(info.get("yearLow", 0) or 0), 2),
            "market_cap": int(info.get("marketCap", 0) or 0),
        }
    except Exception as e:
        logger.warning(f"Quote fetch failed for {symbol} ({e}), using mock")
        try:
            from mock_data import generate_mock_quote
            return generate_mock_quote(symbol)
        except Exception:
            return {"symbol": symbol, "error": str(e)}


def get_all_stocks() -> list:
    """Return list of available NSE stocks."""
    return [{"symbol": sym, "name": name} for sym, name in NSE_STOCKS.items()]


def search_stock(query: str) -> list:
    """Search stocks by symbol or name."""
    query = query.upper()
    results = []
    for sym, name in NSE_STOCKS.items():
        if query in sym or query in name.upper():
            results.append({"symbol": sym, "name": name})
    return results
