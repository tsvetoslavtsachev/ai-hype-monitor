/**
 * app.js — AI Hype Monitor Dashboard
 * Зарежда JSON данни и рендира всички визуализации
 */

// ── Конфигурация ──────────────────────────────────────────────────────────
const DATA_BASE = './data/';
const FILES = {
  hypeIndex:   DATA_BASE + 'hype_index.json',
  dailyPrices: DATA_BASE + 'daily_prices.json',
  rhetoric:    DATA_BASE + 'rhetoric.json',
};

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

  // Draw zone arcs
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

  // Draw needle
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

    // Center dot
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

  // Zone reference lines (annotations via custom plugin)
  const zoneLines = [30, 50, 70, 85];
  const zoneColors = ['#3b82f6', '#22c55e', '#eab308', '#f97316'];
  // (simplified — full annotation plugin would require extra lib)
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
      <div class="heatmap-cell" style="border-color:${bg}40" title="${s.name}">
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

let allStocks = [];
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
      <tr>
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

function renderRhetoricChart(sectorTrend) {
  const ctx = document.getElementById('rhetoricChart');
  if (!ctx || !sectorTrend || !sectorTrend.length) return;

  const labels = sectorTrend.map(t => t.quarter);
  const data   = sectorTrend.map(t => t.sector_avg_rhetoric_score);

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

  const sorted = Object.values(companies)
    .filter(c => c.latest_rhetoric_score !== null)
    .sort((a, b) => (b.latest_rhetoric_score || 0) - (a.latest_rhetoric_score || 0));

  if (!sorted.length) {
    container.innerHTML = '<p style="color:#64748b;font-size:13px">Rhetoric данните ще бъдат налични след следващия earnings сезон.</p>';
    return;
  }

  container.innerHTML = sorted.map(c => {
    const score = c.latest_rhetoric_score;
    const color = scoreColor(score);
    const trend = c.rhetoric_trend === 'rising' ? '↑' : c.rhetoric_trend === 'falling' ? '↓' : '→';
    const trendColor = c.rhetoric_trend === 'rising' ? '#ef4444' : c.rhetoric_trend === 'falling' ? '#22c55e' : '#64748b';

    return `
      <div class="rhetoric-card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="rhetoric-symbol">${c.symbol}</span>
          <span style="color:${trendColor};font-size:14px">${trend}</span>
        </div>
        <div class="rhetoric-name">${c.name}</div>
        <div class="rhetoric-score-bar">
          <div class="rhetoric-score-fill" style="width:${score}%;background:${color}"></div>
        </div>
        <div class="rhetoric-score-val">Score: <strong style="color:${color}">${score.toFixed(1)}</strong></div>
      </div>
    `;
  }).join('');
}

// ── Главна инициализация ──────────────────────────────────────────────────

async function init() {
  // Зареждаме всички данни паралелно
  const [hypeData, pricesData, rhetoricData] = await Promise.all([
    fetchJSON(FILES.hypeIndex),
    fetchJSON(FILES.dailyPrices),
    fetchJSON(FILES.rhetoric),
  ]);

  // ── Hype Index ──
  if (hypeData) {
    const score = hypeData.hype_score;
    const zone  = hypeData.zone;

    document.getElementById('hype-score').textContent = score !== null ? score.toFixed(1) : '—';
    document.getElementById('hype-zone').textContent  = zone?.label || '—';
    document.getElementById('hype-zone').style.color  = zone?.color || '#64748b';

    drawGauge(score);

    // Components
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

    // Interpretation
    const interp = hypeData.interpretation || {};
    const zoneDesc = document.getElementById('zone-description');
    if (zoneDesc) zoneDesc.textContent = interp.zone_description || '';

    const signalsList = document.getElementById('signals-list');
    if (signalsList && interp.key_signals?.length) {
      signalsList.innerHTML = interp.key_signals
        .map(s => `<li>${s}</li>`)
        .join('');
    }

    // Last updated
    const upd = document.getElementById('last-updated');
    if (upd) upd.textContent = `Обновено: ${hypeData.updated_at || '—'}`;

    // History chart
    const history = hypeData.history || [];
    if (history.length) {
      renderHistoryChart(history, 90);

      // Period tabs
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

    // ETF Table
    renderETFTable(etfs, bench);

    // Heatmap
    renderLayerTabs(stocks, layers);
    renderHeatmap(stocks, '');

    // Stocks Table
    allStocks = stocks;
    populateLayerFilter(stocks);
    filterAndSortStocks();

    // Event listeners
    document.getElementById('stock-search')?.addEventListener('input', filterAndSortStocks);
    document.getElementById('layer-filter')?.addEventListener('change', filterAndSortStocks);
    document.getElementById('sort-select')?.addEventListener('change', filterAndSortStocks);
  }

  // ── Rhetoric ──
  if (rhetoricData) {
    renderRhetoricChart(rhetoricData.sector_trend || []);
    renderRhetoricCompanies(rhetoricData.companies || {});
  } else {
    // Placeholder message
    const container = document.getElementById('rhetoric-companies');
    if (container) {
      container.innerHTML = '<p style="color:#64748b;font-size:13px;padding:20px 0">Rhetoric данните ще бъдат налични след стартиране на quarterly pipeline.</p>';
    }
  }
}

// Стартираме при зареждане
document.addEventListener('DOMContentLoaded', init);
