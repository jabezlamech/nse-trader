# NSE Candle Analyzer

Real-time NSE stock analyzer with candlestick pattern detection, backtesting, and trading signals.

## Features

- **Real-time prices** — Live NSE stock quotes via Yahoo Finance (yfinance)
- **Candlestick pattern detection** — 20+ patterns including:
  - Single-candle: Doji, Hammer, Inverted Hammer, Shooting Star, Hanging Man, Marubozu, Spinning Top
  - Two-candle: Bullish/Bearish Engulfing, Harami, Tweezer Top/Bottom, Piercing Line, Dark Cloud Cover, Inside/Outside Bar
  - Three-candle: Morning Star, Evening Star, Three White Soldiers, Three Black Crows
- **Backtesting** — Historical win rate, avg gain/loss, and expected return per pattern
- **Overall signal** — Aggregated BUY / SELL / NEUTRAL signal with confidence score
- **WebSocket feed** — Live pattern updates every 15 seconds
- **30 NSE stocks** — Pre-loaded watchlist (Nifty 50 blue chips)
- **Offline/demo mode** — Auto falls back to realistic mock data if network is unavailable

## Quick Start

```bash
# Install dependencies
pip install fastapi uvicorn yfinance pandas numpy python-multipart websockets

# Start the server
./start.sh
# or:
cd backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stocks` | List all available NSE stocks |
| GET | `/api/stocks/search?q=TCS` | Search by symbol or name |
| GET | `/api/quote/{symbol}` | Real-time quote |
| GET | `/api/candles/{symbol}?interval=1d&limit=100` | OHLCV candle data |
| GET | `/api/analyze/{symbol}?interval=1d&backtest=true` | Full analysis + backtest |
| GET | `/api/watchlist` | Quotes for top 10 stocks |
| WS  | `/ws/{symbol}?interval=1d` | Real-time updates (15s) |

Interactive API docs: **http://localhost:8000/docs**

## Supported Intervals

`1m` · `5m` · `15m` · `30m` · `1h` · `1d` · `1wk`

## Project Structure

```
nse-trader/
├── backend/
│   ├── main.py           # FastAPI app + WebSocket
│   ├── data_fetcher.py   # NSE data via yfinance (+ mock fallback)
│   ├── candle_patterns.py # 20+ pattern detectors
│   ├── backtester.py     # Historical win-rate engine
│   ├── mock_data.py      # Offline demo data generator
│   └── models.py         # Pydantic data models
├── frontend/
│   ├── index.html        # Dashboard UI
│   ├── style.css         # Dark theme styles
│   └── app.js            # Chart + WebSocket client
└── start.sh              # One-command startup
```

## How Backtesting Works

For each pattern, the backtester slides a window over historical data, detects pattern occurrences, then looks 5 candles forward to measure:
- **Win** = price moved ≥0.5% in the signal direction
- **Win rate** = wins / total occurrences
- **Expected return** = win_rate × avg_gain − (1−win_rate) × avg_loss

> **Disclaimer:** This tool is for educational purposes only. Past pattern performance does not guarantee future results. Always do your own research before trading.
