/* NSE Candle Analyzer – Frontend App */

const API = '';  // same origin; set to 'http://localhost:8000' if separate
let currentSymbol = null;
let currentInterval = '1d';
let chart = null;
let ws = null;
let wsReconnectTimer = null;

// ── Utility ──────────────────────────────────────────────────────────────────

function fmt(n) {
  if (n == null || isNaN(n)) return '--';
  if (n >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
  if (n >= 1e5) return (n / 1e5).toFixed(2) + ' L';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtPct(n) {
  if (n == null || isNaN(n)) return '--';
  const sign = n >= 0 ? '+' : '';
  return sign + n.toFixed(2) + '%';
}

function now() {
  return new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function signalColor(sig) {
  if (sig === 'BUY') return '#3fb950';
  if (sig === 'SELL') return '#f85149';
  return '#d29922';
}

// ── Market status ─────────────────────────────────────────────────────────────

function updateMarketStatus() {
  const el = document.getElementById('marketStatus');
  const now = new Date();
  // IST = UTC+5:30
  const ist = new Date(now.getTime() + (5.5 * 60 * 60 * 1000));
  const h = ist.getUTCHours(), m = ist.getUTCMinutes(), day = ist.getUTCDay();
  const open = (h > 9 || (h === 9 && m >= 15)) && (h < 15 || (h === 15 && m <= 30));
  const weekday = day >= 1 && day <= 5;
  if (weekday && open) {
    el.textContent = '● NSE Market Open';
    el.className = 'market-status open';
  } else {
    el.textContent = '● NSE Market Closed';
    el.className = 'market-status closed';
  }
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

async function loadWatchlist() {
  try {
    const res = await fetch(`${API}/api/watchlist`);
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
    const li = document.createElement('li');
    const up = q.change_pct >= 0;
    li.dataset.symbol = q.symbol;
    li.innerHTML = `
      <span class="wl-symbol">${(q.symbol || '').replace('.NS', '')}</span>
      <span class="wl-name">${q.company_name || ''}</span>
      <span class="wl-price">₹${fmt(q.current_price)}</span>
      <span class="wl-chg ${up ? 'up' : 'down'}">${fmtPct(q.change_pct)}</span>
    `;
    li.addEventListener('click', () => selectStock(q.symbol));
    ul.appendChild(li);
  });
}

// ── Search ────────────────────────────────────────────────────────────────────

const searchInput = document.getElementById('searchInput');
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
    const res = await fetch(`${API}/api/stocks/search?q=${encodeURIComponent(q)}`);
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

// ── Stock Selection ───────────────────────────────────────────────────────────

function selectStock(symbol) {
  currentSymbol = symbol;
  // Highlight watchlist
  document.querySelectorAll('.watchlist li').forEach(li => {
    li.classList.toggle('active', li.dataset.symbol === symbol);
  });
  document.getElementById('analyzeBtn').disabled = false;
  runAnalysis();
}

// ── Interval buttons ──────────────────────────────────────────────────────────

document.getElementById('intervalBtns').addEventListener('click', e => {
  const btn = e.target.closest('.int-btn');
  if (!btn) return;
  document.querySelectorAll('.int-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentInterval = btn.dataset.interval;
  if (currentSymbol) runAnalysis();
});

document.getElementById('analyzeBtn').addEventListener('click', () => {
  if (currentSymbol) runAnalysis();
});

// ── Analysis ──────────────────────────────────────────────────────────────────

async function runAnalysis() {
  if (!currentSymbol) return;

  showChartLoading(true);
  hideEmpty();
  document.getElementById('signalPanel').classList.add('hidden');
  document.getElementById('analysisSection').classList.add('hidden');

  try {
    const [candlesRes, analysisRes] = await Promise.all([
      fetch(`${API}/api/candles/${currentSymbol}?interval=${currentInterval}&limit=120`),
      fetch(`${API}/api/analyze/${currentSymbol}?interval=${currentInterval}&backtest=true`)
    ]);

    const candleData = await candlesRes.json();
    const analysis = await analysisRes.json();

    renderStockBar(analysis);
    renderChart(candleData.candles);
    renderSignalPanel(analysis);
    renderPatterns(analysis.patterns_detected || []);
    renderBacktest(analysis.backtest_results || []);

    document.getElementById('signalPanel').classList.remove('hidden');
    document.getElementById('analysisSection').classList.remove('hidden');

    connectWebSocket(currentSymbol);

  } catch (e) {
    console.error('Analysis error:', e);
    showChartLoading(false);
    showEmpty('Error loading data. Please try again.');
  } finally {
    showChartLoading(false);
  }
}

// ── Stock bar ─────────────────────────────────────────────────────────────────

function renderStockBar(data) {
  document.getElementById('stockName').textContent = data.company_name || data.symbol;
  document.getElementById('stockSymbol').textContent = (data.symbol || '').replace('.NS', '');
  document.getElementById('stockPrice').textContent = '₹' + fmt(data.current_price);
  const chgEl = document.getElementById('stockChange');
  const up = data.change >= 0;
  chgEl.textContent = `${up ? '+' : ''}${fmt(data.change)} (${fmtPct(data.change_pct)})`;
  chgEl.className = 'change ' + (up ? 'up' : 'down');
  document.getElementById('dayHigh').textContent = '₹' + fmt(data.day_high);
  document.getElementById('dayLow').textContent = '₹' + fmt(data.day_low);
  document.getElementById('stockVol').textContent = fmt(data.volume);
  document.getElementById('yearHigh').textContent = '₹' + fmt(data.year_high);
  document.getElementById('yearLow').textContent = '₹' + fmt(data.year_low);
}

// ── Chart ─────────────────────────────────────────────────────────────────────

function renderChart(candles) {
  const ctx = document.getElementById('candleChart').getContext('2d');

  if (chart) { chart.destroy(); chart = null; }

  // Build candlestick data
  const ohlc = candles.map(c => ({
    x: new Date(c.timestamp).getTime(),
    o: c.open, h: c.high, l: c.low, c: c.close
  }));

  const volData = candles.map(c => ({
    x: new Date(c.timestamp).getTime(),
    y: c.volume
  }));

  chart = new Chart(ctx, {
    type: 'candlestick',
    data: {
      datasets: [
        {
          label: 'Price',
          data: ohlc,
          color: {
            up: '#3fb950',
            down: '#f85149',
            unchanged: '#8b949e',
          },
          borderColor: {
            up: '#3fb950',
            down: '#f85149',
            unchanged: '#8b949e',
          },
          yAxisID: 'y',
        },
        {
          label: 'Volume',
          type: 'bar',
          data: volData,
          backgroundColor: candles.map(c =>
            c.close >= c.open ? 'rgba(63,185,80,0.25)' : 'rgba(248,81,73,0.25)'
          ),
          borderWidth: 0,
          yAxisID: 'volume',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => {
              if (ctx.dataset.label === 'Volume') return `Vol: ${fmt(ctx.raw.y)}`;
              const d = ctx.raw;
              return [`O: ${d.o}`, `H: ${d.h}`, `L: ${d.l}`, `C: ${d.c}`];
            }
          }
        }
      },
      scales: {
        x: {
          type: 'timeseries',
          ticks: { color: '#8b949e', maxTicksLimit: 10 },
          grid: { color: '#21262d' },
          time: { tooltipFormat: 'dd MMM yyyy' }
        },
        y: {
          position: 'right',
          ticks: { color: '#8b949e' },
          grid: { color: '#21262d' },
        },
        volume: {
          position: 'left',
          ticks: { color: '#8b949e', maxTicksLimit: 4 },
          grid: { drawOnChartArea: false },
          max: val => val * 4,
        }
      }
    }
  });
}

// ── Signal Panel ──────────────────────────────────────────────────────────────

function renderSignalPanel(data) {
  const sig = data.overall_signal || 'NEUTRAL';
  const badge = document.getElementById('signalBadge');
  badge.textContent = sig;
  badge.className = 'signal-badge ' + sig;

  document.getElementById('signalText').textContent =
    sig === 'BUY' ? 'Bullish Signal' :
    sig === 'SELL' ? 'Bearish Signal' : 'Neutral / Indecision';

  document.getElementById('signalConfidence').textContent =
    `Confidence: ${data.overall_confidence || 0}%`;

  document.getElementById('recommendation').textContent =
    data.recommendation || 'No recommendation available.';
}

// ── Patterns ──────────────────────────────────────────────────────────────────

function renderPatterns(patterns) {
  const container = document.getElementById('patternsList');
  if (!patterns.length) {
    container.innerHTML = '<p class="no-patterns">No classic candlestick patterns detected in recent candles.</p>';
    return;
  }

  container.innerHTML = patterns.map(p => `
    <div class="pattern-card">
      <div>
        <div class="p-name">${p.pattern_name}</div>
        <div class="p-desc">${p.description}</div>
        <div style="margin-top:4px;font-size:11px;color:var(--text-muted)">
          Candles: ${p.candles_involved}
        </div>
      </div>
      <span class="p-badge ${p.signal}">${p.signal}</span>
      <span class="p-conf">Confidence<br/><b>${p.confidence}%</b></span>
    </div>
  `).join('');
}

// ── Backtest ──────────────────────────────────────────────────────────────────

function renderBacktest(results) {
  const container = document.getElementById('backtestList');
  if (!results.length) {
    container.innerHTML = '<p class="no-patterns">Run analysis with more history to see backtest results.</p>';
    return;
  }

  const rows = results.map(r => {
    const erClass = r.expected_return >= 0 ? 'positive' : 'negative';
    const barW = Math.min(100, Math.round(r.win_rate)) + '%';
    const sigColor = signalColor(r.signal);
    return `
      <tr>
        <td><b>${r.pattern_name}</b></td>
        <td><span style="color:${sigColor};font-weight:700">${r.signal}</span></td>
        <td>
          ${r.win_rate}%
          <span class="win-rate-bar" style="width:${barW};background:${sigColor}"></span>
        </td>
        <td>${r.total_occurrences} <span style="color:var(--text-muted)">(${r.successful_trades} wins)</span></td>
        <td style="color:var(--green)">+${r.avg_gain_pct}%</td>
        <td style="color:var(--red)">-${r.avg_loss_pct}%</td>
        <td class="er ${erClass}">${r.expected_return >= 0 ? '+' : ''}${r.expected_return}%</td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <table class="bt-table">
      <thead>
        <tr>
          <th>Pattern</th><th>Signal</th><th>Win Rate</th><th>Trades</th>
          <th>Avg Gain</th><th>Avg Loss</th><th>Exp. Return</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
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
  const host = location.host || 'localhost:8000';
  const url = `${proto}://${host}/ws/${symbol}?interval=${currentInterval}`;

  ws = new WebSocket(url);

  ws.onopen = () => {
    document.getElementById('wsStatus').textContent = '● Live (15s updates)';
    document.getElementById('wsStatus').className = 'ws-status connected';
  };

  ws.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'update' && data.symbol === currentSymbol) {
        handleLiveUpdate(data);
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    document.getElementById('wsStatus').textContent = '○ Reconnecting...';
    document.getElementById('wsStatus').className = 'ws-status';
    wsReconnectTimer = setTimeout(() => {
      if (currentSymbol) connectWebSocket(currentSymbol);
    }, 5000);
  };

  ws.onerror = () => ws.close();
}

function handleLiveUpdate(data) {
  // Update price in stock bar
  if (data.quote && data.quote.current_price) {
    document.getElementById('stockPrice').textContent = '₹' + fmt(data.quote.current_price);
    const chgEl = document.getElementById('stockChange');
    const up = data.quote.change >= 0;
    chgEl.textContent = `${up ? '+' : ''}${fmt(data.quote.change)} (${fmtPct(data.quote.change_pct)})`;
    chgEl.className = 'change ' + (up ? 'up' : 'down');
  }

  // Add to live feed
  if (data.patterns && data.patterns.length) {
    addFeedItem(data);
  }
}

function addFeedItem(data) {
  const feed = document.getElementById('liveFeed');
  const placeholder = feed.querySelector('.feed-placeholder');
  if (placeholder) placeholder.remove();

  const sig = data.overall_signal || 'NEUTRAL';
  const topPattern = data.patterns[0]?.pattern_name || 'Update';
  const price = data.quote?.current_price || '--';

  const div = document.createElement('div');
  div.className = `feed-item ${sig}`;
  div.innerHTML = `
    <b>${(data.symbol || '').replace('.NS', '')}</b> — ${topPattern}
    <span style="color:${signalColor(sig)};font-weight:700"> ${sig}</span>
    <span style="float:right;color:var(--text-muted)">₹${fmt(price)}</span>
    <span class="feed-time">${now()}</span>
  `;

  feed.insertBefore(div, feed.firstChild);

  // Keep feed max 20 items
  while (feed.children.length > 20) feed.removeChild(feed.lastChild);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function showChartLoading(show) {
  document.getElementById('chartLoading').classList.toggle('hidden', !show);
}

function hideEmpty() {
  document.getElementById('chartEmpty').classList.add('hidden');
}

function showEmpty(msg) {
  const el = document.getElementById('chartEmpty');
  el.textContent = msg || '▲ Select a stock to start analysis';
  el.classList.remove('hidden');
}

// ── Init ──────────────────────────────────────────────────────────────────────

updateMarketStatus();
setInterval(updateMarketStatus, 60000);
loadWatchlist();

// Auto-refresh watchlist every 2 minutes
setInterval(loadWatchlist, 120000);
