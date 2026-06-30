/**
 * app.js — AI Hype Monitor Dashboard
 * Зарежда JSON данни и рендира всички визуализации
 */

// ── Конфигурация ──────────────────────────────────────────────────────────
const DATA_BASE = './data/';
const FILES = {
  hypeIndex:    DATA_BASE + 'hype_index.json',
  dailyPrices:  DATA_BASE + 'daily_prices.json',
  rhetoric:     DATA_BASE + 'rhetoric.json',
  priceHistory: DATA_BASE + 'price_history.json',
};

// ── Глобален стейт ────────────────────────────────────────────────────────
let allStocks        = [];
let allRhetoric      = [];
let priceHistoryData = null;
let rhetoricData     = null;

// ── Помощни функции ───────────────────────────────────────────────────────

function fmt(val, decimals = 2, suffix = '') {
  if (val === null || val === undefined) return '—';
  return Number(val).toFixed(decimals) + suffix;
}

function fmtPct(val) {
  if (val === null || val === undefined) return '—';
  const n = Number(val);
  const cls = n > 0 ? 'positive' : n < 0 ? 'negative' : 'neutral';
  const sign = n > 0 ? '+' : '';
  return `<span class="${cls}">${sign}${n.toFixed(2)}%</span>`;
}

function fmtPrice(val) {
  if (val === null || val === undefined) return '—';
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function percentileColor(pct) {
  if (pct === null || pct === undefined) return '#374151';
  if (pct >= 80) return '#ef4444';
  if (pct >= 60) return '#f97316';
  if (pct >= 40) return '#eab308';
  if (pct >= 20) return '#22c55e';
  return '#3b82f6';
}

function scoreColor(score) {
  if (score === null || score === undefined) return '#64748b';
  if (score >= 85) return '#ef4444';
  if (score >= 70) return '#f97316';
  if (score >= 50) return '#eab308';
  if (score >= 30) return '#22c55e';
  return '#3b82f6';
}

function zonePill(zone) {
  if (!zone) return '';
  const map = {
    'AI Winter': 'pill-blue',
    'Балансиран': 'pill-green',
    'Повишен': 'pill-yellow',
    'Hype': 'pill-orange',
    'Балон': 'pill-red',
  };
  const cls = map[zone.label] || 'pill-blue';
  return `<span class="pill ${cls}">${zone.icon || ''} ${zone.label}</span>`;
}

async function fetchJSON(url) {
  try {
    const res = await fetch(url + '?t=' + Date.now());
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.warn('Could not fetch', url, e);
    return null;
  }
}

// ── Gauge Chart (полукръг) ─────────────────────────────────────────────────

function drawGauge(score) {
  const canvas = document.getElementById('gaugeChart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const zones = [
    { lo: 0,  hi: 30,  color: '#3b82f6' },
    { lo: 30, hi: 50,  color: '#22c55e' },
    { lo: 50, hi: 70,  color: '#eab308' },
    { lo: 70, hi: 85,  color: '#f97316' },
    { lo: 85, hi: 100, color: '#ef4444' },
  ];

  const W = canvas.width;
  const H = canvas.height;
  const cx = W / 2;
  const cy = H - 20;
  const r = Math.min(W, H * 2) / 2 - 20;
  const lineW = 18;

  ctx.clearRect(0, 0, W, H);

  zones.forEach(z => {
    const startAngle = Math.PI + (z.lo / 100) * Math.PI;
    const endAngle   = Math.PI + (z.hi / 100) * Math.PI;
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = z.color;
    ctx.lineWidth = lineW;
    ctx.lineCap = 'butt';
    ctx.stroke();
  });

  if (score !== null && score !== undefined) {
    const angle = Math.PI + (score / 100) * Math.PI;
    const nx = cx + (r - lineW / 2) * Math.cos(angle);
    const ny = cy + (r - lineW / 2) * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(nx, ny);
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, 5, 0, Math.PI * 2);
    ctx.fillStyle = '#ffffff';
    ctx.fill();
  }
}

// ── History Chart ─────────────────────────────────────────────────────────

let historyChartInstance = null;

function renderHistoryChart(history, days) {
  const filtered = days >= 9000 ? history : history.slice(-days);
  const labels = filtered.map(h => h.date);
  const data   = filtered.map(h => h.score);

  const ctx = document.getElementById('historyChart');
  if (!ctx) return;

  if (historyChartInstance) historyChartInstance.destroy();

  historyChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'AI Hype Score',
        data,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.08)',
        borderWidth: 2,
        pointRadius: filtered.length > 100 ? 0 : 3,
        pointHoverRadius: 5,
        fill: true,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: '#1e2d45',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#e2e8f0',
          callbacks: {
            label: ctx => `Score: ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 11 } },
          grid: { color: 'rgba(30,45,69,0.5)' },
        },
        y: {
          min: 0,
          max: 100,
          ticks: { color: '#64748b', font: { size: 11 } },
          grid: { color: 'rgba(30,45,69,0.5)' },
        },
      },
    },
  });
}

// ── Heatmap ───────────────────────────────────────────────────────────────

function renderHeatmap(stocks, filterLayer) {
  const container = document.getElementById('heatmap-container');
  if (!container) return;

  const filtered = filterLayer
    ? stocks.filter(s => s.layer === filterLayer)
    : stocks;

  container.innerHTML = filtered.map(s => {
    const pct = s.percentile_1y;
    const bg  = percentileColor(pct);
    const r1y = s.return_1y;
    const retCls = r1y > 0 ? 'positive' : r1y < 0 ? 'negative' : 'neutral';
    const retSign = r1y > 0 ? '+' : '';

    return `
      <div class="heatmap-cell" style="border-color:${bg}40;cursor:pointer" title="${s.name}" onclick="openModal('${s.symbol}')">
        <div style="position:absolute;inset:0;background:${bg};opacity:0.08;pointer-events:none;border-radius:10px;"></div>
        <span class="hm-symbol">${s.symbol}</span>
        <span class="hm-name">${s.name.split(' ').slice(0,2).join(' ')}</span>
        <span class="hm-percentile" style="color:${bg}">${pct !== null ? pct.toFixed(0) : '—'}</span>
        <span class="hm-return ${retCls}">${r1y !== null ? retSign + r1y.toFixed(1) + '%' : '—'}</span>
      </div>
    `;
  }).join('');
}

function renderLayerTabs(stocks, layers) {
  const container = document.getElementById('layer-tabs');
  if (!container) return;

  const uniqueLayers = [...new Set(stocks.map(s => s.layer))].sort();

  container.innerHTML = `
    <button class="tab active" data-layer="">Всички</button>
    ${uniqueLayers.map(l => `<button class="tab" data-layer="${l}">${l}</button>`).join('')}
  `;

  container.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderHeatmap(stocks, btn.dataset.layer);
    });
  });
}

// ── ETF Table ─────────────────────────────────────────────────────────────

function renderETFTable(etfs, benchmark) {
  const tbody = document.getElementById('etf-tbody');
  if (!tbody) return;

  const allEtfs = benchmark ? [{ ...benchmark, name: benchmark.name || 'S&P 500 (Benchmark)' }, ...etfs] : etfs;

  tbody.innerHTML = allEtfs.map(e => {
    const pct = e.percentile_1y;
    const pctColor = percentileColor(pct);
    const pctBar = pct !== null
      ? `<div style="display:flex;align-items:center;gap:6px">
           <div style="width:60px;height:4px;background:#1a2236;border-radius:2px;overflow:hidden">
             <div style="width:${pct}%;height:100%;background:${pctColor};border-radius:2px"></div>
           </div>
           <span style="color:${pctColor}">${pct.toFixed(0)}</span>
         </div>`
      : '—';

    return `
      <tr>
        <td><strong>${e.symbol}</strong></td>
        <td style="color:#94a3b8">${e.name}</td>
        <td>${fmtPrice(e.price)}</td>
        <td>${fmtPct(e.return_1d)}</td>
        <td>${fmtPct(e.return_1m)}</td>
        <td>${fmtPct(e.return_3m)}</td>
        <td>${fmtPct(e.return_1y)}</td>
        <td>${pctBar}</td>
        <td>${fmtPct(e.drawdown_1y)}</td>
      </tr>
    `;
  }).join('');
}

// ── Stocks Table ──────────────────────────────────────────────────────────

let currentSort = 'percentile_1y';

function renderStocksTable(stocks) {
  const tbody = document.getElementById('stocks-tbody');
  if (!tbody) return;

  tbody.innerHTML = stocks.map(s => {
    const pct = s.percentile_1y;
    const pctColor = percentileColor(pct);
    const pctBar = pct !== null
      ? `<div style="display:flex;align-items:center;gap:6px">
           <div style="width:50px;height:4px;background:#1a2236;border-radius:2px;overflow:hidden">
             <div style="width:${pct}%;height:100%;background:${pctColor};border-radius:2px"></div>
           </div>
           <span style="color:${pctColor};font-size:12px">${pct.toFixed(0)}</span>
         </div>`
      : '—';

    return `
      <tr style="cursor:pointer" onclick="openModal('${s.symbol}')">
        <td><strong>${s.symbol}</strong></td>
        <td style="color:#94a3b8;font-size:12px">${s.name}</td>
        <td><span style="font-size:11px;color:#64748b">${s.layer}</span></td>
        <td>${fmtPrice(s.price)}</td>
        <td>${fmtPct(s.return_1d)}</td>
        <td>${fmtPct(s.return_1m)}</td>
        <td>${fmtPct(s.return_3m)}</td>
        <td>${fmtPct(s.return_1y)}</td>
        <td>${pctBar}</td>
        <td>${fmtPct(s.drawdown_1y)}</td>
      </tr>
    `;
  }).join('');
}

function filterAndSortStocks() {
  const search = (document.getElementById('stock-search')?.value || '').toLowerCase();
  const layer  = document.getElementById('layer-filter')?.value || '';
  const sort   = document.getElementById('sort-select')?.value || 'percentile_1y';

  let filtered = allStocks.filter(s => {
    const matchSearch = !search || s.symbol.toLowerCase().includes(search) || s.name.toLowerCase().includes(search);
    const matchLayer  = !layer || s.layer === layer;
    return matchSearch && matchLayer;
  });

  filtered.sort((a, b) => {
    if (sort === 'symbol') return a.symbol.localeCompare(b.symbol);
    const av = a[sort] ?? -Infinity;
    const bv = b[sort] ?? -Infinity;
    return bv - av;
  });

  renderStocksTable(filtered);
}

function populateLayerFilter(stocks) {
  const sel = document.getElementById('layer-filter');
  if (!sel) return;
  const layers = [...new Set(stocks.map(s => s.layer))].sort();
  layers.forEach(l => {
    const opt = document.createElement('option');
    opt.value = l;
    opt.textContent = l;
    sel.appendChild(opt);
  });
}

// ── Rhetoric Chart ────────────────────────────────────────────────────────

let rhetoricChartInstance = null;

function renderRhetoricChart(sectorQuarterly) {
  const ctx = document.getElementById('rhetoricChart');
  if (!ctx || !sectorQuarterly || !sectorQuarterly.length) return;

  // rhetoric.json uses sector_quarterly with mean_score field
  const labels = sectorQuarterly.map(t => t.quarter);
  const data   = sectorQuarterly.map(t => t.mean_score);

  if (rhetoricChartInstance) rhetoricChartInstance.destroy();

  rhetoricChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Среден Rhetoric Score',
        data,
        backgroundColor: data.map(v => scoreColor(v) + 'cc'),
        borderColor: data.map(v => scoreColor(v)),
        borderWidth: 1,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: '#1e2d45',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#e2e8f0',
          callbacks: {
            label: ctx => `Score: ${ctx.parsed.y.toFixed(1)} | Документи: ${sectorQuarterly[ctx.dataIndex]?.doc_count || '—'}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 11 } },
          grid: { color: 'rgba(30,45,69,0.5)' },
        },
        y: {
          min: 0,
          max: 100,
          ticks: { color: '#64748b', font: { size: 11 } },
          grid: { color: 'rgba(30,45,69,0.5)' },
        },
      },
    },
  });
}

function renderRhetoricCompanies(companies) {
  const container = document.getElementById('rhetoric-companies');
  if (!container) return;

  // companies is an array with: symbol, name, score, trend, ai_density, substance_ratio, history
  const arr = Array.isArray(companies) ? companies : Object.values(companies);
  const sorted = arr
    .filter(c => c.score !== null && c.score !== undefined)
    .sort((a, b) => (b.score || 0) - (a.score || 0));

  if (!sorted.length) {
    container.innerHTML = '<p style="color:#64748b;font-size:13px">Rhetoric данните ще бъдат налични след следващия earnings сезон.</p>';
    return;
  }

  container.innerHTML = sorted.map(c => {
    const score = c.score;
    const color = scoreColor(score);
    // trend field is unicode arrow: ↑ ↓ →
    const trend = c.trend || '→';
    const trendColor = trend === '↑' ? '#ef4444' : trend === '↓' ? '#22c55e' : '#64748b';
    const substanceLabel = c.substance_ratio !== undefined
      ? `Конкретика: ${(c.substance_ratio * 100).toFixed(0)}%`
      : '';

    return `
      <div class="rhetoric-card" style="cursor:pointer" onclick="openModal('${c.symbol}')">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="rhetoric-symbol">${c.symbol}</span>
          <span style="color:${trendColor};font-size:14px">${trend}</span>
        </div>
        <div class="rhetoric-name">${c.name}</div>
        <div class="rhetoric-score-bar">
          <div class="rhetoric-score-fill" style="width:${score}%;background:${color}"></div>
        </div>
        <div class="rhetoric-score-val">Score: <strong style="color:${color}">${score.toFixed(1)}</strong></div>
        ${substanceLabel ? `<div style="font-size:11px;color:#64748b;margin-top:4px">${substanceLabel}</div>` : ''}
      </div>
    `;
  }).join('');
}

// ── Company Modal ─────────────────────────────────────────────────────────

let modalPriceChart   = null;
let modalRhetChart    = null;

function openModal(symbol) {
  // Find stock data
  const stock = allStocks.find(s => s.symbol === symbol);
  const rhet  = allRhetoric.find(c => c.symbol === symbol);

  const modal = document.getElementById('company-modal');
  if (!modal) return;

  // Header
  const name  = stock?.name || rhet?.name || symbol;
  const layer = stock?.layer || rhet?.layer || '';
  document.getElementById('modal-symbol').textContent = symbol;
  document.getElementById('modal-name').textContent   = name;
  document.getElementById('modal-layer').textContent  = layer;

  // Price metrics
  if (stock) {
    document.getElementById('modal-price').textContent      = fmtPrice(stock.price);
    document.getElementById('modal-ret1d').innerHTML        = fmtPct(stock.return_1d);
    document.getElementById('modal-ret1m').innerHTML        = fmtPct(stock.return_1m);
    document.getElementById('modal-ret3m').innerHTML        = fmtPct(stock.return_3m);
    document.getElementById('modal-ret1y').innerHTML        = fmtPct(stock.return_1y);
    document.getElementById('modal-drawdown').innerHTML     = fmtPct(stock.drawdown_1y);
    const pct = stock.percentile_1y;
    const pctEl = document.getElementById('modal-percentile');
    if (pctEl) {
      pctEl.textContent = pct !== null ? pct.toFixed(0) : '—';
      pctEl.style.color = percentileColor(pct);
    }
  }

  // Rhetoric metrics
  if (rhet) {
    const sc = rhet.score;
    const scEl = document.getElementById('modal-rhetoric-score');
    if (scEl) {
      scEl.textContent = sc !== null ? sc.toFixed(1) : '—';
      scEl.style.color = scoreColor(sc);
    }
    document.getElementById('modal-rhetoric-trend').textContent    = rhet.trend || '→';
    document.getElementById('modal-rhetoric-trend4q').textContent  = rhet.trend_4q || '—';
    document.getElementById('modal-ai-density').textContent        = rhet.ai_density !== undefined ? rhet.ai_density.toFixed(2) + '/1000' : '—';
    document.getElementById('modal-substance').textContent         = rhet.substance_ratio !== undefined ? (rhet.substance_ratio * 100).toFixed(0) + '%' : '—';
    document.getElementById('modal-doc-count').textContent         = rhet.doc_count !== undefined ? rhet.doc_count + ' filings' : '—';
    document.getElementById('modal-last-quarter').textContent      = rhet.last_quarter || '—';
  } else {
    // No rhetoric data for this symbol
    ['modal-rhetoric-score','modal-rhetoric-trend','modal-rhetoric-trend4q',
     'modal-ai-density','modal-substance','modal-doc-count','modal-last-quarter'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
  }

  // Price chart
  renderModalPriceChart(symbol);

  // Rhetoric history chart
  renderModalRhetChart(rhet);

  // Show modal
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const modal = document.getElementById('company-modal');
  if (modal) modal.style.display = 'none';
  document.body.style.overflow = '';
  if (modalPriceChart) { modalPriceChart.destroy(); modalPriceChart = null; }
  if (modalRhetChart)  { modalRhetChart.destroy();  modalRhetChart  = null; }
}

function renderModalPriceChart(symbol) {
  const ctx = document.getElementById('modal-price-chart');
  if (!ctx) return;

  if (modalPriceChart) { modalPriceChart.destroy(); modalPriceChart = null; }

  // Try stocks first, then etfs
  let prices = null;
  if (priceHistoryData) {
    prices = priceHistoryData.stocks?.[symbol]?.prices
          || priceHistoryData.etfs?.[symbol]?.prices
          || null;
  }

  if (!prices || !prices.length) {
    ctx.parentElement.innerHTML = '<p style="color:#64748b;text-align:center;padding:20px">Ценова история не е налична</p>';
    return;
  }

  const labels = prices.map(p => p.date);
  const data   = prices.map(p => p.close);

  modalPriceChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: symbol,
        data,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.06)',
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
        tension: 0.2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: '#1e2d45',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#e2e8f0',
          callbacks: {
            label: ctx => `$${ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', maxTicksLimit: 6, font: { size: 10 } },
          grid: { color: 'rgba(30,45,69,0.4)' },
        },
        y: {
          ticks: {
            color: '#64748b',
            font: { size: 10 },
            callback: v => '$' + v.toFixed(0),
          },
          grid: { color: 'rgba(30,45,69,0.4)' },
        },
      },
    },
  });
}

function renderModalRhetChart(rhet) {
  const ctx = document.getElementById('modal-rhet-chart');
  if (!ctx) return;

  if (modalRhetChart) { modalRhetChart.destroy(); modalRhetChart = null; }

  if (!rhet || !rhet.history || !rhet.history.length) {
    ctx.parentElement.innerHTML = '<p style="color:#64748b;text-align:center;padding:20px">Rhetoric история не е налична (компанията не подава 8-K в SEC)</p>';
    return;
  }

  const history = rhet.history.filter(h => h.score > 0);
  if (!history.length) {
    ctx.parentElement.innerHTML = '<p style="color:#64748b;text-align:center;padding:20px">Недостатъчно данни за rhetoric история</p>';
    return;
  }

  const labels   = history.map(h => h.quarter);
  const scores   = history.map(h => h.score);
  const density  = history.map(h => h.ai_density);

  modalRhetChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Rhetoric Score',
          data: scores,
          backgroundColor: scores.map(v => scoreColor(v) + 'bb'),
          borderColor: scores.map(v => scoreColor(v)),
          borderWidth: 1,
          borderRadius: 3,
          yAxisID: 'y',
        },
        {
          label: 'AI Density (mentions/1000)',
          data: density,
          type: 'line',
          borderColor: '#a78bfa',
          backgroundColor: 'rgba(167,139,250,0.1)',
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          fill: false,
          tension: 0.3,
          yAxisID: 'y2',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          labels: { color: '#94a3b8', font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: '#111827',
          borderColor: '#1e2d45',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#e2e8f0',
        },
      },
      scales: {
        x: {
          ticks: { color: '#64748b', font: { size: 10 } },
          grid: { color: 'rgba(30,45,69,0.4)' },
        },
        y: {
          min: 0,
          max: 100,
          position: 'left',
          ticks: { color: '#64748b', font: { size: 10 } },
          grid: { color: 'rgba(30,45,69,0.4)' },
          title: { display: true, text: 'Score', color: '#64748b', font: { size: 10 } },
        },
        y2: {
          position: 'right',
          ticks: { color: '#a78bfa', font: { size: 10 } },
          grid: { display: false },
          title: { display: true, text: 'Density', color: '#a78bfa', font: { size: 10 } },
        },
      },
    },
  });
}

// ── Главна инициализация ──────────────────────────────────────────────────

async function init() {
  const [hypeData, pricesData, rhet, priceHist] = await Promise.all([
    fetchJSON(FILES.hypeIndex),
    fetchJSON(FILES.dailyPrices),
    fetchJSON(FILES.rhetoric),
    fetchJSON(FILES.priceHistory),
  ]);

  rhetoricData     = rhet;
  priceHistoryData = priceHist;

  // ── Hype Index ──
  if (hypeData) {
    const score = hypeData.hype_score;
    const zone  = hypeData.zone;

    document.getElementById('hype-score').textContent = score !== null ? score.toFixed(1) : '—';
    document.getElementById('hype-zone').textContent  = zone?.label || '—';
    document.getElementById('hype-zone').style.color  = zone?.color || '#64748b';

    drawGauge(score);

    const comps = hypeData.components || {};
    const setComp = (key, barId, valId) => {
      const c = comps[key];
      if (!c) return;
      const bar = document.getElementById(barId);
      const val = document.getElementById(valId);
      if (bar) {
        bar.style.width = (c.score || 0) + '%';
        bar.style.background = scoreColor(c.score);
      }
      if (val) val.textContent = `Score: ${c.score?.toFixed(1) || '—'}`;
    };
    setComp('market_momentum', 'bar-momentum', 'val-momentum');
    setComp('rhetoric',        'bar-rhetoric',  'val-rhetoric');
    setComp('valuation',       'bar-valuation', 'val-valuation');

    const interp = hypeData.interpretation || {};
    const zoneDesc = document.getElementById('zone-description');
    if (zoneDesc) zoneDesc.textContent = interp.zone_description || '';

    const signalsList = document.getElementById('signals-list');
    if (signalsList && interp.key_signals?.length) {
      signalsList.innerHTML = interp.key_signals.map(s => `<li>${s}</li>`).join('');
    }

    const upd = document.getElementById('last-updated');
    if (upd) upd.textContent = `Обновено: ${hypeData.updated_at || '—'}`;

    const history = hypeData.history || [];
    if (history.length) {
      renderHistoryChart(history, 90);

      document.getElementById('period-tabs')?.querySelectorAll('.tab').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('#period-tabs .tab').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          renderHistoryChart(history, parseInt(btn.dataset.period));
        });
      });
    }
  }

  // ── Prices ──
  if (pricesData) {
    const stocks = pricesData.stocks || [];
    const etfs   = pricesData.etfs   || [];
    const bench  = pricesData.benchmark;
    const layers = pricesData.layers || {};

    renderETFTable(etfs, bench);
    renderLayerTabs(stocks, layers);
    renderHeatmap(stocks, '');

    allStocks = stocks;
    populateLayerFilter(stocks);
    filterAndSortStocks();

    document.getElementById('stock-search')?.addEventListener('input', filterAndSortStocks);
    document.getElementById('layer-filter')?.addEventListener('change', filterAndSortStocks);
    document.getElementById('sort-select')?.addEventListener('change', filterAndSortStocks);
  }

  // ── Rhetoric ──
  if (rhet) {
    renderRhetoricChart(rhet.sector_quarterly || []);
    allRhetoric = Array.isArray(rhet.companies) ? rhet.companies : Object.values(rhet.companies || {});
    renderRhetoricCompanies(allRhetoric);
  } else {
    const container = document.getElementById('rhetoric-companies');
    if (container) {
      container.innerHTML = '<p style="color:#64748b;font-size:13px;padding:20px 0">Rhetoric данните ще бъдат налични след стартиране на quarterly pipeline.</p>';
    }
  }

  // ── Modal close handlers ──
  document.getElementById('modal-close')?.addEventListener('click', closeModal);
  document.getElementById('company-modal')?.addEventListener('click', e => {
    if (e.target === document.getElementById('company-modal')) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
  });
}

document.addEventListener('DOMContentLoaded', init);
