"""
NSE Stock Candle Analyzer - FastAPI Backend
Provides REST endpoints + WebSocket for real-time stock analysis.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from data_fetcher import (
    get_stock_data, get_realtime_quote, get_all_stocks, search_stock, NSE_STOCKS
)
from candle_patterns import detect_all_patterns, compute_overall_signal, build_recommendation
from backtester import run_backtest, get_pattern_stats_summary
from models import StockAnalysis, Signal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NSE Candle Analyzer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/stocks")
def list_stocks():
    """List all available NSE stocks."""
    return get_all_stocks()


@app.get("/api/stocks/search")
def search_stocks(q: str = Query(..., min_length=1)):
    """Search stocks by name or symbol."""
    return search_stock(q)


@app.get("/api/quote/{symbol}")
def get_quote(symbol: str):
    """Get real-time quote for a stock."""
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
    """Get OHLCV candle data for a stock."""
    df = get_stock_data(symbol, interval=interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    df = df.tail(limit)
    records = []
    for ts, row in df.iterrows():
        records.append({
            "timestamp": str(ts),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
        })
    return {"symbol": symbol, "interval": interval, "candles": records}


@app.get("/api/analyze/{symbol}")
def analyze_stock(
    symbol: str,
    interval: str = Query("1d", pattern="^(1m|5m|15m|30m|1h|1d|1wk)$"),
    run_bt: bool = Query(True, alias="backtest")
):
    """
    Full analysis: current patterns + backtest results + overall recommendation.
    """
    # Fetch historical data
    df = get_stock_data(symbol, interval=interval)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")

    # Detect patterns on latest candles
    patterns = detect_all_patterns(df)
    overall_signal, overall_confidence = compute_overall_signal(patterns)
    recommendation = build_recommendation(overall_signal, overall_confidence, patterns)

    # Real-time quote
    quote = get_realtime_quote(symbol)

    # Backtest (uses longer history for statistical validity)
    backtest_results = []
    if run_bt and len(df) >= 30:
        backtest_results = run_backtest(df)

    sym_key = symbol if symbol.endswith(".NS") else symbol + ".NS"
    company_name = NSE_STOCKS.get(sym_key, sym_key.replace(".NS", ""))

    return {
        "symbol": sym_key,
        "company_name": company_name,
        "interval": interval,
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
    """Get quotes for default watchlist (top 10 NSE stocks)."""
    default_symbols = list(NSE_STOCKS.keys())[:10]
    quotes = []
    for sym in default_symbols:
        quote = get_realtime_quote(sym)
        quotes.append(quote)
    return quotes


# ─── WebSocket for real-time updates ──────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, symbol: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(symbol, []).append(ws)
        logger.info(f"WS connected for {symbol}, total={len(self.active[symbol])}")

    def disconnect(self, symbol: str, ws: WebSocket):
        if symbol in self.active:
            self.active[symbol] = [w for w in self.active[symbol] if w != ws]

    async def broadcast(self, symbol: str, data: dict):
        for ws in list(self.active.get(symbol, [])):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                self.active[symbol].remove(ws)


manager = ConnectionManager()


@app.websocket("/ws/{symbol}")
async def websocket_endpoint(websocket: WebSocket, symbol: str, interval: str = "1d"):
    await manager.connect(symbol, websocket)
    try:
        while True:
            # Push update every 15 seconds
            try:
                quote = get_realtime_quote(symbol)
                df = get_stock_data(symbol, interval=interval)
                patterns = detect_all_patterns(df) if not df.empty else []
                overall_signal, overall_confidence = compute_overall_signal(patterns)

                payload = {
                    "type": "update",
                    "symbol": symbol,
                    "quote": quote,
                    "patterns": [p.model_dump() for p in patterns[:5]],  # top 5
                    "overall_signal": overall_signal,
                    "overall_confidence": overall_confidence,
                }
                await websocket.send_text(json.dumps(payload))
            except Exception as e:
                logger.error(f"WS update error for {symbol}: {e}")

            await asyncio.sleep(15)
    except WebSocketDisconnect:
        manager.disconnect(symbol, websocket)


# ─── Serve frontend ────────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
