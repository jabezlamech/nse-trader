"""
Zerodha Kite Connect data fetcher.

Provides:
  - get_kite()              → authenticated KiteConnect instance (or None)
  - get_login_url()         → Kite login URL for the user to open
  - complete_login()        → exchange request_token → access_token
  - kite_quote()            → real-time quote for a symbol
  - kite_historical()       → OHLCV DataFrame
  - KiteLiveTicker          → wraps KiteTicker for background use
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional
import pandas as pd
from kiteconnect import KiteConnect, KiteTicker
import kite_config as cfg

logger = logging.getLogger(__name__)

# ── Interval mapping: our names → Kite names ─────────────────────────────────
KITE_INTERVAL = {
    "1m":  "minute",
    "5m":  "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h":  "60minute",
    "1d":  "day",
    "1wk": "week",
}

# ── Instrument token cache ────────────────────────────────────────────────────
# Pre-seeded with Nifty-50 blue chips (avoids an instruments() API call on startup)
# token → {"symbol": "NSE:RELIANCE", "tradingsymbol": "RELIANCE"}
_TOKEN_CACHE: dict[str, int] = {}   # tradingsymbol → instrument_token
_CACHE_LOADED = False


def _ensure_instrument_cache(kite: KiteConnect) -> None:
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    try:
        instruments = kite.instruments("NSE")
        for inst in instruments:
            _TOKEN_CACHE[inst["tradingsymbol"]] = inst["instrument_token"]
        _CACHE_LOADED = True
        logger.info(f"Loaded {len(_TOKEN_CACHE)} NSE instruments from Kite")
    except Exception as e:
        logger.warning(f"Could not load instrument list: {e}")


def _get_token(kite: KiteConnect, tradingsymbol: str) -> Optional[int]:
    _ensure_instrument_cache(kite)
    sym = tradingsymbol.replace(".NS", "").upper()
    token = _TOKEN_CACHE.get(sym)
    if token is None:
        logger.warning(f"Instrument token not found for {sym}")
    return token


# ── KiteConnect singleton ─────────────────────────────────────────────────────
_kite_instance: Optional[KiteConnect] = None


def get_kite() -> Optional[KiteConnect]:
    """Return an authenticated KiteConnect instance, or None if not configured."""
    global _kite_instance

    if not cfg.is_configured():
        return None

    if _kite_instance is None:
        _kite_instance = KiteConnect(api_key=cfg.get_api_key())

    token = cfg.load_access_token()
    if token:
        _kite_instance.set_access_token(token)
        return _kite_instance

    return None


def get_login_url() -> str:
    """Generate Kite login URL. User must open this in browser."""
    if not cfg.is_configured():
        raise ValueError("KITE_API_KEY and KITE_API_SECRET must be set in .env")
    kite = KiteConnect(api_key=cfg.get_api_key())
    return kite.login_url()


def complete_login(request_token: str) -> str:
    """
    Exchange request_token (from Kite redirect) for access_token.
    Saves the token and returns it.
    """
    kite = KiteConnect(api_key=cfg.get_api_key())
    data = kite.generate_session(request_token, api_secret=cfg.get_api_secret())
    access_token = data["access_token"]
    cfg.save_access_token(access_token)
    global _kite_instance
    _kite_instance = kite
    kite.set_access_token(access_token)
    logger.info("Kite login complete — access token saved")
    return access_token


# ── Quote ─────────────────────────────────────────────────────────────────────

def kite_quote(symbol: str) -> Optional[dict]:
    """
    Return a real-time quote dict for the given NSE symbol.
    symbol can be 'RELIANCE' or 'RELIANCE.NS'.
    """
    kite = get_kite()
    if kite is None:
        return None

    tradingsymbol = symbol.replace(".NS", "").upper()
    kite_symbol = f"NSE:{tradingsymbol}"

    try:
        raw = kite.quote([kite_symbol])
        q = raw.get(kite_symbol, {})
        if not q:
            return None

        ohlc = q.get("ohlc", {})
        prev_close = ohlc.get("close", 0)
        current = q.get("last_price", 0)
        change = current - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0

        from data_fetcher import NSE_STOCKS
        sym_key = tradingsymbol + ".NS"

        return {
            "symbol": sym_key,
            "company_name": NSE_STOCKS.get(sym_key, tradingsymbol),
            "current_price": round(current, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "day_high": round(ohlc.get("high", current), 2),
            "day_low": round(ohlc.get("low", current), 2),
            "volume": int(q.get("volume", 0)),
            "year_high": round(q.get("upper_circuit_limit", 0), 2),
            "year_low": round(q.get("lower_circuit_limit", 0), 2),
            "market_cap": 0,
            "_source": "kite",
        }
    except Exception as e:
        logger.error(f"Kite quote error for {symbol}: {e}")
        return None


# ── Historical OHLCV ──────────────────────────────────────────────────────────

def kite_historical(symbol: str, interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV candle data from Kite for the given symbol and interval.
    Returns a DataFrame with columns [open, high, low, close, volume] or None.
    """
    kite = get_kite()
    if kite is None:
        return None

    tradingsymbol = symbol.replace(".NS", "").upper()
    token = _get_token(kite, tradingsymbol)
    if token is None:
        return None

    kite_interval = KITE_INTERVAL.get(interval, "day")

    # Determine from/to dates based on interval
    now = datetime.now()
    period_days = {
        "1m": 7, "5m": 60, "15m": 60, "30m": 60,
        "1h": 400, "1d": 730, "1wk": 1825,
    }
    from_date = now - timedelta(days=period_days.get(interval, 730))

    try:
        records = kite.historical_data(
            instrument_token=token,
            from_date=from_date.strftime("%Y-%m-%d %H:%M:%S"),
            to_date=now.strftime("%Y-%m-%d %H:%M:%S"),
            interval=kite_interval,
            continuous=False,
            oi=False,
        )
        if not records:
            return None

        df = pd.DataFrame(records)
        df = df.rename(columns={
            "date": "timestamp", "open": "open", "high": "high",
            "low": "low", "close": "close", "volume": "volume"
        })
        df = df.set_index("timestamp")
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        logger.info(f"Kite: fetched {len(df)} candles for {tradingsymbol} [{interval}]")
        return df
    except Exception as e:
        logger.error(f"Kite historical error for {symbol}: {e}")
        return None


# ── Live Ticker ───────────────────────────────────────────────────────────────

class KiteLiveTicker:
    """
    Wraps KiteTicker to stream live ticks for subscribed symbols.
    Call start() once; register on_tick callbacks to receive updates.
    """

    def __init__(self):
        self._ticker: Optional[KiteTicker] = None
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._subscribed_tokens: set[int] = set()
        self._symbol_token_map: dict[str, int] = {}   # tradingsymbol → token
        self._token_symbol_map: dict[int, str] = {}   # token → tradingsymbol

    def register_callback(self, fn: Callable) -> None:
        """Register a function(ticks: list[dict]) that gets called on each tick."""
        self._callbacks.append(fn)

    def subscribe(self, symbol: str) -> bool:
        """Add a symbol to the live feed. Returns True if successful."""
        kite = get_kite()
        if kite is None:
            return False

        tradingsymbol = symbol.replace(".NS", "").upper()
        if tradingsymbol in self._symbol_token_map:
            return True  # already subscribed

        token = _get_token(kite, tradingsymbol)
        if token is None:
            return False

        self._symbol_token_map[tradingsymbol] = token
        self._token_symbol_map[token] = tradingsymbol
        self._subscribed_tokens.add(token)

        if self._ticker and self._ticker.is_connected():
            self._ticker.subscribe(list(self._subscribed_tokens))
            self._ticker.set_mode(self._ticker.MODE_FULL, list(self._subscribed_tokens))

        return True

    def start(self) -> None:
        """Start the KiteTicker in a background thread."""
        kite = get_kite()
        if kite is None:
            logger.warning("Kite not authenticated — live ticker not started")
            return

        if self._ticker and self._ticker.is_connected():
            return  # already running

        self._ticker = KiteTicker(
            api_key=cfg.get_api_key(),
            access_token=cfg.load_access_token(),
        )

        def on_ticks(ws, ticks):
            enriched = []
            for tick in ticks:
                token = tick.get("instrument_token")
                sym = self._token_symbol_map.get(token, str(token))
                enriched.append({
                    "symbol": sym + ".NS",
                    "last_price": tick.get("last_price", 0),
                    "change": tick.get("net_change", 0),
                    "volume": tick.get("volume_traded", 0),
                    "ohlc": tick.get("ohlc", {}),
                })
            for fn in self._callbacks:
                try:
                    fn(enriched)
                except Exception as exc:
                    logger.error(f"Ticker callback error: {exc}")

        def on_connect(ws, response):
            logger.info("KiteTicker connected")
            if self._subscribed_tokens:
                tokens = list(self._subscribed_tokens)
                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)

        def on_error(ws, code, reason):
            logger.error(f"KiteTicker error {code}: {reason}")

        def on_close(ws, code, reason):
            logger.info(f"KiteTicker closed: {code} {reason}")

        self._ticker.on_ticks = on_ticks
        self._ticker.on_connect = on_connect
        self._ticker.on_error = on_error
        self._ticker.on_close = on_close

        self._thread = threading.Thread(
            target=self._ticker.connect, kwargs={"threaded": False}, daemon=True
        )
        self._thread.start()
        logger.info("KiteTicker thread started")

    def stop(self) -> None:
        if self._ticker:
            self._ticker.close()
            self._ticker = None


# Module-level singleton — imported by main.py
live_ticker = KiteLiveTicker()
