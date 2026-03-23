/* NSE Candle Analyzer — Frontend */

const API = '';   // same origin; change to 'http://localhost:8000' if running separately
let currentSymbol  = null;
let currentInterval = '1d';
let chart          = null;
let candleSeries   = null;
let volumeSeries   = null;
let ws             = null;
let wsReconnectTimer = null;

// ── Utilities ─────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null || isNaN(n)) return '--';
  if (n >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
  if (n >= 1e5) return (n / 1e5).toFixed(2) + ' L';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return '--';
  return (n >= 0 ? '+' : '') + Number(n).toFixed(2) + '%';
}

function nowTime() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function signalColor(sig) {
  return sig === 'BUY' ? '#3fb950' : sig === 'SELL' ? '#f85149' : '#d29922';
}

// ── Market status ─────────────────────────────────────────────────────────────

function updateMarketStatus() {
  const el  = document.getElementById('marketStatus');
  const now = new Date();
  const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
  const h   = ist.getUTCHours(), m = ist.getUTCMinutes(), day = ist.getUTCDay();
  const open = day >= 1 && day <= 5 && (h > 9 || (h === 9 && m >= 15)) && (h < 15 || (h === 15 && m <= 30));
  el.textContent  = open ? '● NSE Market Open' : '● NSE Market Closed';
  el.className    = 'market-status ' + (open ? 'open' : 'closed');
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

async function loadWatchlist() {
  try {
    const res    = await fetch(`${API}/api/watchlist`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const quotes = await res.json();
    renderWatchlist(quotes);
  } catch (e) {
    console.error('Watchlist error:', e);
  }
}

function renderWatchlist(quotes) {
  const ul = document.getElementById('watchlist');
  ul.innerHTML = '';
  quotes.forEach(q => {
    const up = (q.change_pct || 0) >= 0;
    const li = document.createElement('li');
    li.dataset.symbol = q.symbol;
    li.innerHTML = `
      <span class="wl-symbol">${(q.symbol || '').replace('.NS', '')}</span>
      <span class="wl-name">${q.company_name || ''}</span>
      <span class="wl-price">₹${fmt(q.current_price)}</span>
      <span class="wl-chg ${up ? 'up' : 'down'}">${fmtPct(q.change_pct)}</span>`;
    li.addEventListener('click', () => selectStock(q.symbol));
    ul.appendChild(li);
  });
}

// ── Search ────────────────────────────────────────────────────────────────────

const searchInput    = document.getElementById('searchInput');
const searchDropdown = document.getElementById('searchDropdown');
let searchTimer = null;

searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  const q = searchInput.value.trim();
  if (!q) { searchDropdown.classList.add('hidden'); return; }
  searchTimer = setTimeout(() => doSearch(q), 300);
});

searchInput.addEventListener('keydown', e => {
  if (e.key === 'Escape') { searchDropdown.classList.add('hidden'); searchInput.blur(); }
});

document.addEventListener('click', e => {
  if (!e.target.closest('.search-wrap')) searchDropdown.classList.add('hidden');
});

async function doSearch(q) {
  try {
    const res    = await fetch(`${API}/api/stocks/search?q=${encodeURIComponent(q)}`);
    const stocks = await res.json();
    renderDropdown(stocks);
  } catch (e) { console.error(e); }
}

function renderDropdown(stocks) {
  searchDropdown.innerHTML = '';
  if (!stocks.length) {
    searchDropdown.innerHTML = '<li style="color:var(--text-muted);cursor:default;">No results</li>';
  } else {
    stocks.slice(0, 10).forEach(s => {
      const li = document.createElement('li');
      li.innerHTML = `<span class="sym">${s.symbol.replace('.NS','')}</span><span class="nm">${s.name}</span>`;
      li.addEventListener('click', () => {
        selectStock(s.symbol);
        searchInput.value = '';
        searchDropdown.classList.add('hidden');
      });
      searchDropdown.appendChild(li);
    });
  }
  searchDropdown.classList.remove('hidden');
}

// ── Stock selection ───────────────────────────────────────────────────────────

function selectStock(symbol) {
  currentSymbol = symbol;
  document.querySelectorAll('.watchlist li').forEach(li =>
    li.classList.toggle('active', li.dataset.symbol === symbol));
  document.getElementById('analyzeBtn').disabled = false;
  loadCandlesAndQuote();   // step 1: chart + quote
}

// ── Interval buttons ──────────────────────────────────────────────────────────

document.getElementById('intervalBtns').addEventListener('click', e => {
  const btn = e.target.closest('.int-btn');
  if (!btn) return;
  document.querySelectorAll('.int-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentInterval = btn.dataset.interval;
  if (currentSymbol) loadCandlesAndQuote();
});

document.getElementById('analyzeBtn').addEventListener('click', () => {
  if (currentSymbol) runAnalysis();
});

// ── Step 1: load chart + quote (fast) ─────────────────────────────────────────

async function loadCandlesAndQuote() {
  if (!currentSymbol) return;

  setChartLoading(true);
  hideChartError();
  hideEmpty();
  document.getElementById('signalPanel').classList.add('hidden');
  document.getElementById('analysisSection').classList.add('hidden');

  try {
    const [candlesRes, quoteRes] = await Promise.all([
      fetch(`${API}/api/candles/${currentSymbol}?interval=${currentInterval}&limit=150`),
      fetch(`${API}/api/quote/${currentSymbol}`)
    ]);

    if (!candlesRes.ok) {
      const err = await candlesRes.json().catch(() => ({}));
      throw new Error(err.detail || `Candles API returned ${candlesRes.status}`);
    }

    const candleData = await candlesRes.json();
    const quote      = quoteRes.ok ? await quoteRes.json() : {};

    renderStockBar(quote);
    renderChart(candleData.candles, candleData.symbol);
    connectWebSocket(currentSymbol);

  } catch (e) {
    console.error('Chart load error:', e);
    setChartLoading(false);
    showChartError(`Could not load chart: ${e.message}`);
  } finally {
    setChartLoading(false);
  }
}

// ── Step 2: run full analysis + backtest (slow, on demand) ────────────────────

async function runAnalysis() {
  if (!currentSymbol) return;

  document.getElementById('analyzeLoading').classList.remove('hidden');
  document.getElementById('signalPanel').classList.add('hidden');
  document.getElementById('analysisSection').classList.add('hidden');

  try {
    const res = await fetch(
      `${API}/api/analyze/${currentSymbol}?interval=${currentInterval}&backtest=true`
    );

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Analysis API returned ${res.status}`);
    }

    const analysis = await res.json();

    renderStockBar(analysis);
    renderSignalPanel(analysis);
    renderPatterns(analysis.patterns_detected || []);
    renderBacktest(analysis.backtest_results || []);

    document.getElementById('signalPanel').classList.remove('hidden');
    document.getElementById('analysisSection').classList.remove('hidden');

  } catch (e) {
    console.error('Analysis error:', e);
    alert(`Analysis failed: ${e.message}`);
  } finally {
    document.getElementById('analyzeLoading').classList.add('hidden');
  }
}

// ── Stock bar ─────────────────────────────────────────────────────────────────

function renderStockBar(data) {
  if (!data || !data.symbol) return;

  document.getElementById('stockName').textContent   = data.company_name || data.symbol;
  document.getElementById('stockSymbol').textContent = (data.symbol || '').replace('.NS', '');

  // Data source badge
  const badge = document.getElementById('dataSourceBadge');
  const src   = data.data_source || data._source;
  if (src) {
    badge.textContent = src === 'kite' ? '● Kite Live' : src === 'yfinance' ? 'Yahoo Finance' : 'Demo Mode';
    badge.className   = 'source-badge ' + (src === 'kite' ? 'live' : src === 'yfinance' ? 'yfin' : 'demo');
  } else {
    badge.classList.add('hidden');
  }

  const price = data.current_price || 0;
  document.getElementById('stockPrice').textContent = '₹' + fmt(price);

  const chgEl = document.getElementById('stockChange');
  const up    = (data.change || 0) >= 0;
  chgEl.textContent = `${up ? '+' : ''}${fmt(data.change)} (${fmtPct(data.change_pct)})`;
  chgEl.className   = 'change ' + (up ? 'up' : 'down');

  document.getElementById('dayHigh').textContent  = '₹' + fmt(data.day_high);
  document.getElementById('dayLow').textContent   = '₹' + fmt(data.day_low);
  document.getElementById('stockVol').textContent = fmt(data.volume);
  document.getElementById('yearHigh').textContent = '₹' + fmt(data.year_high);
  document.getElementById('yearLow').textContent  = '₹' + fmt(data.year_low);
}

// ── TradingView Lightweight Chart ─────────────────────────────────────────────

function renderChart(candles, symbol) {
  const container = document.getElementById('candleChart');
  container.innerHTML = '';   // clear old chart

  if (!candles || !candles.length) {
    showChartError('No candle data returned for this symbol/interval.');
    return;
  }

  // Create chart
  chart = LightweightCharts.createChart(container, {
    width:  container.clientWidth,
    height: container.clientHeight || 340,
    layout: {
      background: { color: '#161b22' },
      textColor:  '#8b949e',
    },
    grid: {
      vertLines: { color: '#21262d' },
      horzLines: { color: '#21262d' },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#30363d' },
    timeScale: {
      borderColor:     '#30363d',
      timeVisible:     true,
      secondsVisible:  false,
    },
  });

  // Candlestick series
  candleSeries = chart.addCandlestickSeries({
    upColor:      '#3fb950',
    downColor:    '#f85149',
    borderUpColor:   '#3fb950',
    borderDownColor: '#f85149',
    wickUpColor:     '#3fb950',
    wickDownColor:   '#f85149',
  });

  // Volume histogram
  volumeSeries = chart.addHistogramSeries({
    priceFormat:    { type: 'volume' },
    priceScaleId:   'vol',
    scaleMargins:   { top: 0.8, bottom: 0 },
  });
  chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  // Transform candle data for lightweight-charts
  const ohlc = [];
  const vols = [];

  candles.forEach(c => {
    // lightweight-charts wants Unix timestamp (seconds) for intraday, or 'YYYY-MM-DD' for daily
    const d   = new Date(c.timestamp);
    const ts  = Math.floor(d.getTime() / 1000);

    if (!isNaN(ts) && c.open != null) {
      ohlc.push({ time: ts, open: c.open, high: c.high, low: c.low, close: c.close });
      vols.push({
        time:  ts,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(63,185,80,0.35)' : 'rgba(248,81,73,0.35)',
      });
    }
  });

  // Sort ascending (required by lightweight-charts)
  ohlc.sort((a, b) => a.time - b.time);
  vols.sort((a, b) => a.time - b.time);

  candleSeries.setData(ohlc);
  volumeSeries.setData(vols);
  chart.timeScale().fitContent();

  // Resize on window resize
  window.addEventListener('resize', () => {
    if (chart) chart.applyOptions({ width: container.clientWidth });
  });
}

// ── Signal Panel ──────────────────────────────────────────────────────────────

function renderSignalPanel(data) {
  const sig   = data.overall_signal || 'NEUTRAL';
  const badge = document.getElementById('signalBadge');
  badge.textContent = sig;
  badge.className   = 'signal-badge ' + sig;

  document.getElementById('signalText').textContent =
    sig === 'BUY' ? 'Bullish Signal' : sig === 'SELL' ? 'Bearish Signal' : 'Neutral / Indecision';

  document.getElementById('signalConfidence').textContent =
    `Confidence: ${data.overall_confidence || 0}%`;

  document.getElementById('recommendation').textContent =
    data.recommendation || 'No recommendation available.';
}

// ── Patterns ──────────────────────────────────────────────────────────────────

function renderPatterns(patterns) {
  const el = document.getElementById('patternsList');
  if (!patterns.length) {
    el.innerHTML = '<p class="no-patterns">No classic patterns detected in the latest candles.</p>';
    return;
  }
  el.innerHTML = patterns.map(p => `
    <div class="pattern-card">
      <div style="flex:1">
        <div class="p-name">${p.pattern_name}</div>
        <div class="p-desc">${p.description}</div>
        <div style="margin-top:4px;font-size:11px;color:var(--text-muted)">Candles: ${p.candles_involved}</div>
      </div>
      <span class="p-badge ${p.signal}">${p.signal}</span>
      <span class="p-conf">Confidence<br/><b>${p.confidence}%</b></span>
    </div>`).join('');
}

// ── Backtest ──────────────────────────────────────────────────────────────────

function renderBacktest(results) {
  const el = document.getElementById('backtestList');
  if (!results.length) {
    el.innerHTML = '<p class="no-patterns">Insufficient history for backtest. Try a longer interval (1D, 1W).</p>';
    return;
  }
  const rows = results.map(r => {
    const er  = r.expected_return;
    const col = signalColor(r.signal);
    return `<tr>
      <td><b>${r.pattern_name}</b></td>
      <td><span style="color:${col};font-weight:700">${r.signal}</span></td>
      <td>${r.win_rate}%
        <span class="win-rate-bar" style="width:${Math.min(r.win_rate,100)}%;background:${col}"></span>
      </td>
      <td>${r.total_occurrences} <span style="color:var(--text-muted)">(${r.successful_trades} wins)</span></td>
      <td style="color:var(--green)">+${r.avg_gain_pct}%</td>
      <td style="color:var(--red)">-${r.avg_loss_pct}%</td>
      <td class="er ${er >= 0 ? 'positive' : 'negative'}">${er >= 0 ? '+' : ''}${er}%</td>
    </tr>`;
  }).join('');

  el.innerHTML = `<table class="bt-table">
    <thead><tr>
      <th>Pattern</th><th>Signal</th><th>Win Rate</th><th>Trades</th>
      <th>Avg Gain</th><th>Avg Loss</th><th>Exp. Return</th>
    </tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab + 'Tab').classList.add('active');
  });
});

// ── WebSocket ─────────────────────────────────────────────────────────────────

function connectWebSocket(symbol) {
  if (ws) { ws.close(); ws = null; }
  clearTimeout(wsReconnectTimer);

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const host  = location.host || 'localhost:8000';
  ws = new WebSocket(`${proto}://${host}/ws/${symbol}?interval=${currentInterval}`);

  ws.onopen = () => {
    document.getElementById('wsStatus').textContent = '● Live updates on';
    document.getElementById('wsStatus').className   = 'ws-status connected';
  };

  ws.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'heartbeat') return;
      if ((data.type === 'update' || data.type === 'tick') && data.symbol === currentSymbol) {
        handleLiveData(data);
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    document.getElementById('wsStatus').textContent = '○ Reconnecting...';
    document.getElementById('wsStatus').className   = 'ws-status';
    wsReconnectTimer = setTimeout(() => { if (currentSymbol) connectWebSocket(currentSymbol); }, 5000);
  };

  ws.onerror = () => ws.close();
}

function handleLiveData(data) {
  const q = data.quote || data.tick || {};

  // Update price bar
  if (q.last_price || q.current_price) {
    const price = q.last_price || q.current_price;
    document.getElementById('stockPrice').textContent = '₹' + fmt(price);
  }

  if (q.change !== undefined || q.net_change !== undefined) {
    const chg    = q.change ?? q.net_change ?? 0;
    const chgPct = q.change_pct ?? 0;
    const up     = chg >= 0;
    const chgEl  = document.getElementById('stockChange');
    chgEl.textContent = `${up ? '+' : ''}${fmt(chg)} (${fmtPct(chgPct)})`;
    chgEl.className   = 'change ' + (up ? 'up' : 'down');
  }

  // Update live chart candle
  if (candleSeries && q.ohlc) {
    const ohlc = q.ohlc;
    const ts   = Math.floor(Date.now() / 1000);
    candleSeries.update({ time: ts, open: ohlc.open, high: ohlc.high, low: ohlc.low, close: q.last_price || ohlc.close });
  }

  // Live feed
  if (data.patterns && data.patterns.length) addFeedItem(data);
}

function addFeedItem(data) {
  const feed        = document.getElementById('liveFeed');
  const placeholder = feed.querySelector('.feed-placeholder');
  if (placeholder) placeholder.remove();

  const sig        = data.overall_signal || 'NEUTRAL';
  const topPattern = data.patterns[0]?.pattern_name || 'Update';
  const price      = data.quote?.current_price || data.tick?.last_price || '--';

  const div       = document.createElement('div');
  div.className   = `feed-item ${sig}`;
  div.innerHTML   = `
    <b>${(data.symbol || '').replace('.NS', '')}</b> — ${topPattern}
    <span style="color:${signalColor(sig)};font-weight:700"> ${sig}</span>
    <span style="float:right;color:var(--text-muted)">₹${fmt(price)}</span>
    <span class="feed-time">${nowTime()}</span>`;
  feed.insertBefore(div, feed.firstChild);
  while (feed.children.length > 20) feed.removeChild(feed.lastChild);
}

// ── Chart state helpers ───────────────────────────────────────────────────────

function setChartLoading(show) {
  document.getElementById('chartLoading').classList.toggle('hidden', !show);
}

function hideEmpty() {
  document.getElementById('chartEmpty').classList.add('hidden');
}

function showChartError(msg) {
  const el  = document.getElementById('chartError');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function hideChartError() {
  document.getElementById('chartError').classList.add('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────────

updateMarketStatus();
setInterval(updateMarketStatus, 60000);
loadWatchlist();
setInterval(loadWatchlist, 120000);
