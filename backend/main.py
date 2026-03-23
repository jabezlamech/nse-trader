"""
NSE Stock Candle Analyzer - FastAPI Backend
REST endpoints + WebSocket for real-time stock analysis.
Data source priority: Zerodha Kite → Yahoo Finance → Mock data
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
import os

from data_fetcher import (
    get_stock_data, get_realtime_quote, get_all_stocks, search_stock, NSE_STOCKS
)
from candle_patterns import detect_all_patterns, compute_overall_signal, build_recommendation
from backtester import run_backtest, get_pattern_stats_summary
from models import Signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NSE Candle Analyzer", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Kite ticker background task ───────────────────────────────────────────────
# Holds the asyncio loop reference so the KiteTicker thread can push ticks
_loop: Optional[asyncio.AbstractEventLoop] = None


@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_running_loop()

    import kite_config
    if kite_config.is_authenticated():
        from kite_fetcher import live_ticker

        def on_kite_ticks(ticks: list):
            """Called from KiteTicker thread — bridge ticks to async WebSocket manager."""
            for tick in ticks:
                sym = tick.get("symbol", "")
                if sym and _loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.push_tick(sym, tick), _loop
                    )

        live_ticker.register_callback(on_kite_ticks)
        live_ticker.start()
        logger.info("Kite live ticker started at startup")
    else:
        logger.info("Kite not authenticated — using poll-based WebSocket updates")


@app.on_event("shutdown")
async def shutdown():
    try:
        from kite_fetcher import live_ticker
        live_ticker.stop()
    except Exception:
        pass


# ── Kite Auth Endpoints ───────────────────────────────────────────────────────

@app.get("/api/kite/status")
def kite_status():
    """Check whether Kite Connect is configured and authenticated."""
    import kite_config
    return {
        "configured": kite_config.is_configured(),
        "authenticated": kite_config.is_authenticated(),
        "api_key_set": bool(kite_config.get_api_key()),
    }


@app.get("/api/kite/login")
def kite_login():
    """
    Generate the Kite login URL.
    Open this URL in your browser, log in, and you will be redirected
    to /api/kite/callback with a request_token.
    """
    import kite_config
    if not kite_config.is_configured():
        raise HTTPException(
            status_code=400,
            detail="KITE_API_KEY and KITE_API_SECRET not set. Add them to your .env file."
        )
    from kite_fetcher import get_login_url
    url = get_login_url()
    return {"login_url": url, "instructions": "Open login_url in your browser to authenticate."}


@app.get("/api/kite/callback")
def kite_callback(request_token: str = Query(...)):
    """
    Kite redirects here after login with ?request_token=xxx&action=login&status=success.
    Exchanges the token for an access token and saves it.
    """
    try:
        from kite_fetcher import complete_login, live_ticker
        access_token = complete_login(request_token)

        # Start live ticker now that we have a valid token
        def on_ticks(ticks):
            for tick in ticks:
                sym = tick.get("symbol", "")
                if sym and _loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.push_tick(sym, tick), _loop
                    )

        live_ticker.register_callback(on_ticks)
        live_ticker.start()

        return RedirectResponse(url="/?kite=connected")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Kite login failed: {e}")


@app.post("/api/kite/token")
def set_kite_token(access_token: str = Query(...)):
    """
    Manually set a Kite access token (if you already have one).
    Useful for day-trading — paste yesterday's valid token or a fresh one.
    """
    import kite_config
    if not kite_config.is_configured():
        raise HTTPException(status_code=400, detail="API key/secret not configured in .env")
    kite_config.save_access_token(access_token)
    return {"status": "ok", "message": "Access token saved. Restart the server or call /api/kite/status to verify."}


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/stocks")
def list_stocks():
    return get_all_stocks()


@app.get("/api/stocks/search")
def search_stocks(q: str = Query(..., min_length=1)):
    return search_stock(q)


@app.get("/api/quote/{symbol}")
def get_quote(symbol: str):
    quote = get_realtime_quote(symbol)
    if "error" in quote:
        raise HTTPException(status_code=404, detail=quote["error"])
    return quote


@app.get("/api/candles/{symbol}")
def get_candles(
    symbol: str,
    interval: str = Query("1d", pattern="^(1m|5m|15m|30m|1h|1d|1wk)$"),
    limit: int = Query(100, ge=10, le=500)
):
    df = get_stock_data(symbol, interval=interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    df = df.tail(limit)
    records = [
        {
            "timestamp": str(ts),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        }
        for ts, row in df.iterrows()
    ]
    return {"symbol": symbol, "interval": interval, "candles": records}


@app.get("/api/analyze/{symbol}")
def analyze_stock(
    symbol: str,
    interval: str = Query("1d", pattern="^(1m|5m|15m|30m|1h|1d|1wk)$"),
    run_bt: bool = Query(True, alias="backtest")
):
    """Full analysis: patterns + backtest + overall signal + recommendation."""
    df = get_stock_data(symbol, interval=interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    patterns = detect_all_patterns(df)
    overall_signal, overall_confidence = compute_overall_signal(patterns)
    recommendation = build_recommendation(overall_signal, overall_confidence, patterns)
    quote = get_realtime_quote(symbol)

    backtest_results = run_backtest(df) if run_bt and len(df) >= 30 else []

    sym_key = symbol if symbol.endswith(".NS") else symbol + ".NS"

    return {
        "symbol": sym_key,
        "company_name": NSE_STOCKS.get(sym_key, sym_key.replace(".NS", "")),
        "interval": interval,
        "data_source": quote.get("_source", "mock"),
        "current_price": quote.get("current_price", 0),
        "change": quote.get("change", 0),
        "change_pct": quote.get("change_pct", 0),
        "day_high": quote.get("day_high", 0),
        "day_low": quote.get("day_low", 0),
        "year_high": quote.get("year_high", 0),
        "year_low": quote.get("year_low", 0),
        "volume": quote.get("volume", 0),
        "patterns_detected": [p.model_dump() for p in patterns],
        "backtest_results": [r.model_dump() for r in backtest_results],
        "backtest_summary": get_pattern_stats_summary(backtest_results),
        "overall_signal": overall_signal,
        "overall_confidence": overall_confidence,
        "recommendation": recommendation,
    }


@app.get("/api/watchlist")
def get_watchlist_quotes():
    default_symbols = list(NSE_STOCKS.keys())[:10]
    return [get_realtime_quote(sym) for sym in default_symbols]


# ── WebSocket ─────────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}   # symbol → [ws, ...]

    async def connect(self, symbol: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(symbol, []).append(ws)
        # Tell Kite ticker to subscribe to this symbol
        try:
            import kite_config
            if kite_config.is_authenticated():
                from kite_fetcher import live_ticker
                live_ticker.subscribe(symbol)
        except Exception:
            pass
        logger.info(f"WS connected: {symbol} (total={len(self.active[symbol])})")

    def disconnect(self, symbol: str, ws: WebSocket):
        if symbol in self.active:
            self.active[symbol] = [w for w in self.active[symbol] if w != ws]

    async def broadcast(self, symbol: str, data: dict):
        dead = []
        for ws in list(self.active.get(symbol, [])):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active[symbol].remove(ws)

    async def push_tick(self, symbol: str, tick: dict):
        """Called from KiteTicker thread via run_coroutine_threadsafe."""
        payload = {"type": "tick", "symbol": symbol, "tick": tick}
        await self.broadcast(symbol, payload)


manager = ConnectionManager()


@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str, interval: str = "1d"):
    """
    WebSocket endpoint.
    - With Kite: pushes real-time ticks from KiteTicker (sub-second latency)
    - Without Kite: polls every 15 seconds
    """
    await manager.connect(symbol, websocket)
    try:
        import kite_config
        use_kite = kite_config.is_authenticated()
    except Exception:
        use_kite = False

    if use_kite:
        # Kite pushes ticks via manager.push_tick(); just keep connection alive
        try:
            while True:
                # Send a heartbeat every 30s so the connection doesn't time out
                await asyncio.sleep(30)
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
        except WebSocketDisconnect:
            manager.disconnect(symbol, websocket)
    else:
        # Poll mode: fetch + analyse every 15 seconds
        try:
            while True:
                try:
                    quote = get_realtime_quote(symbol)
                    df = get_stock_data(symbol, interval=interval)
                    patterns = detect_all_patterns(df) if not df.empty else []
                    sig, conf = compute_overall_signal(patterns)
                    await websocket.send_text(json.dumps({
                        "type": "update",
                        "symbol": symbol,
                        "quote": quote,
                        "patterns": [p.model_dump() for p in patterns[:5]],
                        "overall_signal": sig,
                        "overall_confidence": conf,
                    }))
                except Exception as e:
                    logger.error(f"WS poll error for {symbol}: {e}")
                await asyncio.sleep(15)
        except WebSocketDisconnect:
            manager.disconnect(symbol, websocket)


# ── Frontend static files ─────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
