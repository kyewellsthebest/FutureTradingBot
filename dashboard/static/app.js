/* HFT Bot dashboard — Fib 50% frontend.
   Polls /api/data (full snapshot) every 5s. Renders all tabs from one blob. */

const POLL_MS = 5000;
let state = { data: null, candles: null, trades: null };
let chart = null, candleSeries = null;

// ---- Tab routing ---------------------------------------------------------
function activateTab(name) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach(p =>
    p.classList.toggle("active", p.id === `pane-${name}`));
  // lazy init chart when chart tab first shown
  if (name === "chart" && !chart) initChart();
  // re-render performance graphs when performance tab opens
  if (name === "performance") renderPerformanceGraphs();
}
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => activateTab(t.dataset.tab));
});

// ---- Utilities -----------------------------------------------------------
const fmtUsd = (n) => {
  if (n === undefined || n === null || isNaN(n)) return "—";
  const s = Math.abs(n) >= 1000 ? n.toFixed(0) : n.toFixed(2);
  return (n >= 0 ? "+$" : "-$") + Math.abs(parseFloat(s)).toLocaleString();
};
const fmtUsdPlain = (n) => {
  if (n === undefined || n === null || isNaN(n)) return "$—";
  return "$" + Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
};
const fmtPct = (n, decimals=1) =>
  (n === undefined || n === null || isNaN(n)) ? "—" : (n * 100).toFixed(decimals) + "%";
const fmtNum = (n) =>
  (n === undefined || n === null || isNaN(n)) ? "—" : n.toLocaleString();
const fmtHold = (s) => {
  if (s === undefined || s === null || isNaN(s)) return "—";
  if (s < 60) return s.toFixed(0) + "s";
  if (s < 3600) return (s / 60).toFixed(1) + "m";
  return (s / 3600).toFixed(1) + "h";
};
const setText = (id, t) => { const el = document.getElementById(id); if (el) el.textContent = t; };
const setClass = (id, cls) => { const el = document.getElementById(id); if (el) el.className = cls; };

// ---- Polling -------------------------------------------------------------
async function poll() {
  try {
    const r = await fetch("/api/data");
    if (r.ok) {
      state.data = await r.json();
      renderAll();
    }
  } catch (e) { console.error("poll failed", e); }
}
async function pollCandles() {
  try {
    const r = await fetch("/api/candles");
    if (r.ok) {
      state.candles = await r.json();
      if (candleSeries && state.candles && Array.isArray(state.candles)) {
        candleSeries.setData(state.candles);
      }
    }
  } catch (e) {}
}
async function pollTrades() {
  try {
    const r = await fetch("/api/trades");
    if (r.ok) state.trades = await r.json();
    renderTradesTable();
    renderPerformanceGraphs();
  } catch (e) {}
}
setInterval(poll, POLL_MS);
setInterval(pollCandles, 30_000);
setInterval(pollTrades, 15_000);
poll(); pollCandles(); pollTrades();

// ---- TOPBAR + LIVE ------------------------------------------------------
function renderTopbar(d) {
  setText("kpi-price", d.price ? d.price.toFixed(2) : "—");
  const acc = d.lucid_account || {};
  const bal = acc.balance ?? 50000;
  setText("kpi-balance", fmtUsdPlain(bal));
  const today = acc.today_pnl ?? 0;
  const todayEl = document.getElementById("kpi-today");
  todayEl.textContent = fmtUsd(today);
  todayEl.className = "kpi-value " + (today > 0 ? "pos" : today < 0 ? "neg" : "");
  const fib = d.fib || {};
  const at = fib.active_trade;
  const posText = at ? `${at.side} ${at.n_mnq}` : "FLAT";
  setText("kpi-position", posText);
  const posEl = document.getElementById("kpi-position");
  posEl.className = "kpi-value " + (at ? (at.side === "LONG" ? "pos" : "neg") : "");
  setText("kpi-updated", d.ts ? new Date(d.ts).toLocaleTimeString() : "—");
  setText("badge-mode", d.mode || "shadow");
  const modeBadge = document.getElementById("badge-mode");
  modeBadge.className = "badge badge-mode" + (d.mode === "live" ? " live" : "");
  setText("badge-version", "fib");
}

function renderLive(d) {
  const fib = d.fib || {};
  const acc = d.lucid_account || {};

  // active trade card
  const activeBox = document.getElementById("live-active");
  if (fib.active_trade) {
    const a = fib.active_trade;
    activeBox.innerHTML = `
      <div class="kv-list">
        <div class="kv-row"><span>Side</span><b class="${a.side === 'LONG' ? 'kpi-value pos' : 'kpi-value neg'}">${a.side}</b></div>
        <div class="kv-row"><span>Size</span><b>${a.n_mnq} MNQ</b></div>
        <div class="kv-row"><span>Entry</span><b>${a.entry_px.toFixed(2)}</b></div>
        <div class="kv-row"><span>Stop</span><b>${a.stop_px.toFixed(2)}</b></div>
        <div class="kv-row"><span>Target</span><b>${a.target_px.toFixed(2)}</b></div>
        <div class="kv-row"><span>Held</span><b>${fmtHold(a.hold_s)}</b></div>
      </div>`;
  } else {
    activeBox.innerHTML = '<div class="muted">No open position.</div>';
  }

  // pending setups
  setText("live-pending-n", fib.pending_setups ?? 0);

  // microscalp gauge
  const ratio = fib.microscalp_ratio_30d ?? 0;
  const arc = document.getElementById("gauge-arc");
  const arcMax = 141;  // path length
  const pct = Math.min(ratio / 0.5, 1);
  arc.style.strokeDashoffset = (arcMax - arcMax * pct).toFixed(1);
  arc.classList.remove("warn", "danger");
  if (ratio >= 0.40) arc.classList.add("danger");
  else if (ratio >= 0.30) arc.classList.add("warn");
  setText("gauge-text", (ratio * 100).toFixed(1) + "%");
  setText("gauge-status",
    fib.circuit_breaker_tripped
      ? `CIRCUIT BREAKER TRIPPED: ${fib.circuit_breaker_reason || ''}`
      : `Lucid ban threshold: 50% · safety cap: 40%`);

  // today
  setText("today-fired", d.signals_fired ?? 0);
  setText("today-closed", (d.recent_trades || []).filter(t =>
    new Date(t.ts).toDateString() === new Date().toDateString()).length);
  setText("today-pnl", fmtUsd(acc.today_pnl ?? 0));

  // system
  setText("sys-cycle", d.cycle ?? 0);
  setText("sys-breaker", fib.circuit_breaker_tripped ? "TRIPPED" : "armed");
  setText("sys-error", d.last_error || "none");
}

// ---- Funded tab ----------------------------------------------------------
function renderFunded(d) {
  const acc = d.lucid_account || {};
  const bal = acc.balance ?? 50000;
  const trail = acc.trail_floor ?? 48000;
  const pnl = bal - 50000;
  setText("funded-balance", fmtUsdPlain(bal));
  setText("funded-pnl", fmtUsd(pnl));
  setText("funded-trail", fmtUsdPlain(trail));
  setText("funded-buffer", fmtUsdPlain(bal - trail));
  const todayLoss = Math.max(0, -(acc.today_pnl ?? 0));
  setText("funded-dll", fmtUsdPlain(todayLoss) + " / $1,200");
  const dllPct = Math.min(todayLoss / 1200, 1) * 100;
  const bar = document.getElementById("funded-dll-bar");
  bar.style.width = dllPct.toFixed(1) + "%";
  bar.classList.remove("warn", "danger");
  if (dllPct >= 75) bar.classList.add("danger");
  else if (dllPct >= 50) bar.classList.add("warn");
  setText("funded-peak", fmtUsdPlain(acc.peak_eod ?? bal));
  setText("funded-locked", acc.trail_locked ? "Yes (at $50k)" : "No");
  setText("funded-days", acc.days_traded ?? 0);
  const fib = d.fib || {};
  setText("funded-micro", fmtPct(fib.microscalp_ratio_30d || 0, 1));
}

// ---- Trades tab ----------------------------------------------------------
function renderTradesTable() {
  const tbody = document.querySelector("#trades-table tbody");
  const trades = (state.data && state.data.recent_trades) || [];
  if (!trades.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="muted">No trades yet.</td></tr>';
    return;
  }
  tbody.innerHTML = trades.map(t => {
    const pnl = t.pnl_usd ?? 0;
    const sideClass = t.side === "LONG" ? "side-long" : "side-short";
    const pnlClass = pnl >= 0 ? "pos" : "neg";
    return `<tr>
      <td>${new Date(t.ts).toLocaleString()}</td>
      <td class="${sideClass}"><b>${t.side}</b></td>
      <td>${t.n_mnq}</td>
      <td>${(t.entry_px ?? 0).toFixed(2)}</td>
      <td>${(t.exit_px ?? 0).toFixed(2)}</td>
      <td>${t.exit_reason}</td>
      <td>${fmtHold(t.hold_s)}</td>
      <td class="${pnlClass}">${fmtUsd(pnl)}</td>
    </tr>`;
  }).join("");
}

// ---- Chart tab -----------------------------------------------------------
function initChart() {
  const el = document.getElementById("chart-container");
  if (!el || typeof LightweightCharts === "undefined") return;
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: "#0c1320" }, textColor: "#a4b1c7" },
    grid: { vertLines: { color: "rgba(255,255,255,0.04)" },
            horzLines: { color: "rgba(255,255,255,0.04)" } },
    timeScale: { borderColor: "rgba(255,255,255,0.1)" },
    rightPriceScale: { borderColor: "rgba(255,255,255,0.1)" },
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#22d39a", downColor: "#ff5470",
    wickUpColor: "#22d39a", wickDownColor: "#ff5470",
    borderVisible: false,
  });
  if (state.candles) candleSeries.setData(state.candles);
  window.addEventListener("resize", () => {
    chart.resize(el.clientWidth, el.clientHeight);
  });
}

// ---- Performance graphs --------------------------------------------------
function renderPerformanceGraphs() {
  if (!state.trades && !state.data) return;
  const trades = (state.data && state.data.recent_trades) || [];
  drawEquityCurve(trades);
  drawMonthlyPnl(trades);
  drawHoldHistogram(trades);
  drawWinLossHistogram(trades);
}

function _setupCanvas(id) {
  const c = document.getElementById(id);
  if (!c) return null;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = c.clientHeight;
  c.width = w * dpr; c.height = h * dpr;
  const ctx = c.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

function drawEquityCurve(trades) {
  const r = _setupCanvas("chart-equity"); if (!r) return;
  const { ctx, w, h } = r;
  const start = 50000;
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const sorted = trades.slice().reverse();
  let bal = start;
  const points = [start];
  sorted.forEach(t => { bal += (t.pnl_usd || 0); points.push(bal); });
  const minV = Math.min(...points), maxV = Math.max(...points);
  const range = Math.max(maxV - minV, 1);
  const padX = 30, padY = 20;
  // grid line at $50k
  ctx.strokeStyle = "rgba(255,255,255,0.08)"; ctx.lineWidth = 1;
  const y50k = h - padY - ((50000 - minV) / range) * (h - 2 * padY);
  ctx.beginPath(); ctx.setLineDash([3, 4]); ctx.moveTo(padX, y50k); ctx.lineTo(w - padX, y50k); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#5d6b85"; ctx.font = "10px sans-serif"; ctx.textAlign = "left";
  ctx.fillText("$50k start", padX + 4, y50k - 4);
  // line
  const gradient = ctx.createLinearGradient(0, 0, 0, h);
  gradient.addColorStop(0, "rgba(34,211,154,0.4)");
  gradient.addColorStop(1, "rgba(34,211,154,0.02)");
  ctx.beginPath();
  points.forEach((v, i) => {
    const x = padX + (i / (points.length - 1)) * (w - 2 * padX);
    const y = h - padY - ((v - minV) / range) * (h - 2 * padY);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  // fill under
  ctx.lineTo(w - padX, h - padY); ctx.lineTo(padX, h - padY); ctx.closePath();
  ctx.fillStyle = gradient; ctx.fill();
  // line on top
  ctx.beginPath();
  points.forEach((v, i) => {
    const x = padX + (i / (points.length - 1)) * (w - 2 * padX);
    const y = h - padY - ((v - minV) / range) * (h - 2 * padY);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#22d39a"; ctx.lineWidth = 2; ctx.stroke();
}

function drawMonthlyPnl(trades) {
  const r = _setupCanvas("chart-monthly"); if (!r) return;
  const { ctx, w, h } = r;
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const months = {};
  trades.forEach(t => {
    const d = new Date(t.ts);
    const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    months[key] = (months[key] || 0) + (t.pnl_usd || 0);
  });
  const keys = Object.keys(months).sort();
  const vals = keys.map(k => months[k]);
  if (!vals.length) return;
  const padX = 30, padY = 20;
  const maxV = Math.max(...vals.map(Math.abs), 1);
  const bw = (w - 2 * padX) / Math.max(keys.length, 1);
  // zero line
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  const yZero = h / 2;
  ctx.beginPath(); ctx.moveTo(padX, yZero); ctx.lineTo(w - padX, yZero); ctx.stroke();
  // bars
  vals.forEach((v, i) => {
    const x = padX + i * bw + 2;
    const bh = (Math.abs(v) / maxV) * (h / 2 - padY);
    ctx.fillStyle = v >= 0 ? "#22d39a" : "#ff5470";
    if (v >= 0) ctx.fillRect(x, yZero - bh, bw - 4, bh);
    else ctx.fillRect(x, yZero, bw - 4, bh);
  });
  // x labels (every other if many)
  ctx.fillStyle = "#5d6b85"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  const step = keys.length > 12 ? Math.ceil(keys.length / 12) : 1;
  keys.forEach((k, i) => {
    if (i % step === 0) ctx.fillText(k.slice(2), padX + i * bw + bw / 2, h - 4);
  });
}

function drawHoldHistogram(trades) {
  const r = _setupCanvas("chart-holds"); if (!r) return;
  const { ctx, w, h } = r;
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const buckets = [
    { label: "≤10s", lo: 0,    hi: 10,   c: 0 },
    { label: "10-30s", lo: 10, hi: 30,   c: 0 },
    { label: "30-60s", lo: 30, hi: 60,   c: 0 },
    { label: "1-5m",   lo: 60, hi: 300,  c: 0 },
    { label: "5-30m",  lo: 300, hi: 1800, c: 0 },
    { label: "30m-2h", lo: 1800, hi: 7200, c: 0 },
    { label: "2-8h",   lo: 7200, hi: 28800, c: 0 },
  ];
  trades.forEach(t => {
    const s = t.hold_s ?? 0;
    for (const b of buckets) if (s >= b.lo && s < b.hi) { b.c++; break; }
  });
  const maxC = Math.max(...buckets.map(b => b.c), 1);
  const padX = 30, padY = 30;
  const bw = (w - 2 * padX) / buckets.length;
  buckets.forEach((b, i) => {
    const x = padX + i * bw + 4;
    const bh = (b.c / maxC) * (h - 2 * padY);
    // bar
    const isMicro = b.label === "≤10s";
    ctx.fillStyle = isMicro ? "#ffb648" : "#56d4ff";
    ctx.fillRect(x, h - padY - bh, bw - 8, bh);
    // count above bar
    ctx.fillStyle = "#a4b1c7"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
    if (b.c > 0) ctx.fillText(b.c, x + (bw - 8) / 2, h - padY - bh - 4);
    // label below
    ctx.fillStyle = "#5d6b85";
    ctx.fillText(b.label, x + (bw - 8) / 2, h - 8);
  });
}

function drawWinLossHistogram(trades) {
  const r = _setupCanvas("chart-wlhist"); if (!r) return;
  const { ctx, w, h } = r;
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const wins = trades.filter(t => (t.pnl_usd || 0) > 0);
  const losses = trades.filter(t => (t.pnl_usd || 0) < 0);
  const padX = 30, padY = 30;
  const lanes = [
    { label: `Wins (${wins.length})`, color: "#22d39a",
      avg: wins.length ? wins.reduce((s, t) => s + t.pnl_usd, 0) / wins.length : 0 },
    { label: `Losses (${losses.length})`, color: "#ff5470",
      avg: losses.length ? losses.reduce((s, t) => s + t.pnl_usd, 0) / losses.length : 0 },
  ];
  const maxV = Math.max(...lanes.map(l => Math.abs(l.avg)), 1);
  const bw = (w - 2 * padX) / 2;
  lanes.forEach((lane, i) => {
    const x = padX + i * bw + 20;
    const bh = (Math.abs(lane.avg) / maxV) * (h - 2 * padY);
    ctx.fillStyle = lane.color;
    ctx.fillRect(x, h - padY - bh, bw - 40, bh);
    ctx.fillStyle = lane.color; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(fmtUsd(lane.avg), x + (bw - 40) / 2, h - padY - bh - 6);
    ctx.fillStyle = "#a4b1c7"; ctx.font = "11px sans-serif";
    ctx.fillText(lane.label, x + (bw - 40) / 2, h - 10);
  });
}

// ---- Master render ------------------------------------------------------
function renderAll() {
  if (!state.data) return;
  renderTopbar(state.data);
  renderLive(state.data);
  renderFunded(state.data);
  renderTradesTable();
  renderPerformanceGraphs();
}
