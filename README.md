# NSE Candle Analyzer

Real-time NSE stock dashboard with candlestick pattern detection, backtesting, and AI-driven trading signals — powered by **Zerodha Kite Connect**.

---

## How to Run (Windows)

### Step 1 — Install Python dependencies

Open **Command Prompt** (not PowerShell) in the project folder:

```cmd
pip install fastapi uvicorn kiteconnect yfinance pandas numpy python-multipart websockets python-dotenv
```

### Step 2 — Configure Zerodha Kite credentials

1. Go to [https://developers.kite.trade/apps](https://developers.kite.trade/apps)
2. Create a new app — set the **Redirect URL** to `http://localhost:8000/api/kite/callback`
3. Copy your **API Key** and **API Secret**
4. Copy `.env.example` to `.env` in the project root and fill in your values:

```
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
```

### Step 3 — Start the server

Double-click **`start.bat`** or run from Command Prompt:

```cmd
start.bat
```

Then open **http://localhost:8000** in your browser.

---

## Zerodha Kite Login (Daily)

Kite access tokens expire at the end of each trading day. Each morning:

1. Open **http://localhost:8000/api/kite/login** in your browser
2. Click the `login_url` link — it opens Zerodha's login page
3. Log in with your Zerodha credentials and 2FA
4. You will be redirected back to the app automatically
5. The app saves the token and starts live streaming

**Alternative** — if you already have a fresh access token:

```
http://localhost:8000/api/kite/token?access_token=YOUR_TOKEN
```

---

## Features

| Feature | Details |
|---------|---------|
| **Real-time prices** | Live tick data via Kite WebSocket (sub-second) |
| **Historical data** | Up to 2 years of OHLCV via Kite historical API |
| **Pattern detection** | 20+ candlestick patterns with BUY/SELL signals |
| **Backtesting** | Win rate, avg gain/loss, expected return per pattern |
| **Overall signal** | Aggregated confidence-weighted BUY / SELL / NEUTRAL |
| **Live feed** | WebSocket feed updates on every Kite tick |
| **Fallback mode** | Uses Yahoo Finance or realistic mock data if Kite is offline |

---

## Candlestick Patterns Detected

**Single-candle**
Doji · Gravestone Doji · Dragonfly Doji · Hammer · Inverted Hammer · Shooting Star · Hanging Man · Bullish Marubozu · Bearish Marubozu · Spinning Top

**Two-candle**
Bullish Engulfing · Bearish Engulfing · Bullish Harami · Bearish Harami · Tweezer Top · Tweezer Bottom · Piercing Line · Dark Cloud Cover · Inside Bar · Outside Bar

**Three-candle**
Morning Star · Evening Star · Three White Soldiers · Three Black Crows

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/kite/status` | Kite connection status |
| GET | `/api/kite/login` | Get Kite login URL |
| GET | `/api/kite/callback?request_token=` | Kite OAuth callback (auto-called) |
| POST | `/api/kite/token?access_token=` | Manually set access token |
| GET | `/api/stocks` | List all 30 NSE stocks |
| GET | `/api/stocks/search?q=TCS` | Search by symbol or name |
| GET | `/api/quote/{symbol}` | Real-time quote |
| GET | `/api/candles/{symbol}?interval=1d&limit=100` | OHLCV candle data |
| GET | `/api/analyze/{symbol}?interval=1d&backtest=true` | Full analysis |
| GET | `/api/watchlist` | Quotes for top 10 stocks |
| WS  | `/ws/{symbol}?interval=1d` | Live updates |

Interactive API docs: **http://localhost:8000/docs**

---

## Supported Intervals

`1m` · `5m` · `15m` · `30m` · `1h` · `1d` · `1wk`

---

## Project Structure

```
nse-trader/
├── .env.example           ← copy to .env and add your Kite credentials
├── start.bat              ← Windows one-click startup
├── backend/
│   ├── main.py            ← FastAPI app (REST + WebSocket)
│   ├── kite_fetcher.py    ← Kite quotes, historical data, live ticker
│   ├── kite_config.py     ← credential loading and token storage
│   ├── data_fetcher.py    ← Kite → yfinance → mock (priority order)
│   ├── candle_patterns.py ← 20+ pattern detectors
│   ├── backtester.py      ← historical win-rate engine
│   ├── mock_data.py       ← offline demo data generator
│   └── models.py          ← Pydantic data models
└── frontend/
    ├── index.html         ← dashboard UI
    ├── style.css          ← dark theme
    └── app.js             ← Chart.js candlestick chart + WebSocket client
```

---

## Where Is It Hosted?

This is a **local application** that runs on your own Windows machine — it is not hosted on any external server. This is intentional:

- Your Kite API credentials and access tokens stay on your machine
- No third party can see your trading data or positions
- You control when it runs and what it connects to

To access it: start `start.bat`, then open `http://localhost:8000`.

If you want to access it from another device on the same Wi-Fi network, use your PC's local IP address instead of `localhost` (e.g., `http://192.168.1.5:8000`). Find your IP with `ipconfig` in Command Prompt.

---

> **Disclaimer:** This tool is for educational and informational purposes only. Candlestick patterns are probabilistic signals, not guarantees. Always do your own research and manage your risk before trading.
