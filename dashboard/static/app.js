/* Futures Trading Bot dashboard — Fib 50% frontend.
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
        updateChartMarkers();
        updateTradeLineSegments();
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
    updateChartMarkers();
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
  // Compute today's P&L from actual closed trades — same authoritative
  // source the Activity card uses. acc.today_pnl had drift bugs.
  const today = (d.recent_trades || [])
    .filter(t => new Date(t.ts).toDateString() === new Date().toDateString())
    .reduce((s, t) => s + (t.pnl_usd || 0), 0);
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
  setText("badge-version", "pullback");

  // HTF trend + chop badges REMOVED — the pullback strategy doesn't
  // use either filter. We just look for the 5pt impulse and trade it.
  // (The strategy snapshot still emits htf_trend/chop_index for backwards
  // compat with old dashboard versions, but the UI no longer renders them.)

  // Data source badge — "real 1m" if Polygon/yfinance 1-min came through,
  // "synth 1m" if we're falling back to deriving from 5-min OHLC.
  const src = d.bars_1m_source || "synth";
  const srcEl = document.getElementById("badge-src");
  if (srcEl) {
    srcEl.textContent = (src === "real" ? "real 1m" : "synth 1m");
    srcEl.className = "badge badge-src " +
      (src === "real" ? "src-real" : "src-synth");
  }
}

function renderLive(d) {
  const fib = d.fib || {};
  const acc = d.lucid_account || {};

  // active trade card
  const activeBox = document.getElementById("live-active");
  if (fib.active_trade) {
    const a = fib.active_trade;
    const unrealised = a.unrealized_pnl_usd;
    const unrealisedPts = a.unrealized_pnl_pts;
    const cur = a.current_price ?? d.price;
    const hasLive = unrealised !== undefined && unrealised !== null && !isNaN(unrealised);
    const pnlClass = hasLive ? (unrealised >= 0 ? "pos" : "neg") : "";
    const boxClass = hasLive && unrealised < 0 ? "live-pnl-box neg" : "live-pnl-box";
    const liveBlock = hasLive ? `
      <div class="${boxClass}">
        <div class="live-pnl-label">Unrealised P&L</div>
        <div class="live-pnl-value ${pnlClass}">${fmtUsd(unrealised)}</div>
        <div class="live-pnl-sub">
          ${unrealisedPts >= 0 ? "+" : ""}${(unrealisedPts ?? 0).toFixed(2)} pts
          ${cur ? " · last " + cur.toFixed(2) : ""}
        </div>
      </div>` : "";
    activeBox.innerHTML = `
      ${liveBlock}
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
  const todayTrades = (d.recent_trades || []).filter(t =>
    new Date(t.ts).toDateString() === new Date().toDateString());
  setText("today-closed", todayTrades.length);
  // Compute today P&L from the actual trade records, not lucid.today_pnl.
  // The Lucid state had drift bugs in earlier sessions; the trade DB is
  // authoritative. This also matches what the monthly P&L tooltip shows.
  const todayPnlComputed = todayTrades.reduce((s, t) => s + (t.pnl_usd || 0), 0);
  setText("today-pnl", fmtUsd(todayPnlComputed));
  // Win rate + avg hold (computed from today's recent trades, since
  // these aren't available in the LucidState snapshot)
  if (todayTrades.length > 0) {
    const wins = todayTrades.filter(t => (t.pnl_usd || 0) > 0).length;
    const wr = wins / todayTrades.length;
    setText("today-wr", (wr * 100).toFixed(1) + "%");
    const avgHold = todayTrades.reduce((s, t) => s + (t.hold_s || 0), 0)
                    / todayTrades.length;
    setText("today-hold", fmtHold(avgHold));
  } else {
    setText("today-wr", "—");
    setText("today-hold", "—");
  }

  // system
  setText("sys-cycle", d.cycle ?? 0);
  setText("sys-breaker", fib.circuit_breaker_tripped ? "TRIPPED" : "armed");
  setText("sys-error", d.last_error || "none");

  // Bot health diagnostics — surfaces bar source, cycle, counters, market hours
  renderBotHealth(d);

  // Sim baseline drift monitor — annualise from all completed trades
  renderDriftMonitor(d);
}

// CME globex schedule (NQ): Sun 18:00 ET open → Fri 17:00 ET close,
// with a daily 17:00-18:00 ET maintenance break Mon-Thu. All in NY tz.
function cmeMarketStatus() {
  const now = new Date();
  const ny = new Date(now.toLocaleString("en-US", {timeZone: "America/New_York"}));
  const dow = ny.getDay();  // 0=Sun, 6=Sat
  const hr  = ny.getHours();
  if (dow === 6) return {open: false, label: "CLOSED (Saturday)"};
  if (dow === 0 && hr < 18) return {open: false, label: `CLOSED — reopens ${18 - hr}h (Sun 6pm ET)`};
  if (dow === 5 && hr >= 17) return {open: false, label: "CLOSED (Fri 5pm ET → Sun 6pm ET)"};
  if (dow >= 1 && dow <= 4 && hr === 17) return {open: false, label: "DAILY BREAK (5-6pm ET)"};
  return {open: true, label: "OPEN ✓"};
}

function renderBotHealth(d) {
  const mkt = cmeMarketStatus();
  const mktEl = document.getElementById("health-market");
  mktEl.textContent = mkt.label;
  mktEl.className = mkt.open ? "pos" : "muted";

  const src = d.bars_1m_source || "—";
  const srcEl = document.getElementById("health-bar-source");
  srcEl.textContent = src === "real" ? "real (Polygon/yfinance) ✓" :
                      src === "synth" ? "SYNTH (1m derived from 5m bars)" : src;
  srcEl.className = src === "real" ? "pos" : "muted";

  // Last tick freshness
  const ageEl = document.getElementById("health-price-ts");
  if (d.price_ts) {
    const ageS = (Date.now() - new Date(d.price_ts).getTime()) / 1000;
    if (ageS < 0) ageEl.textContent = "future?";
    else if (ageS < 60)  { ageEl.textContent = `${ageS.toFixed(0)}s ago`; ageEl.className = "pos"; }
    else if (ageS < 600) { ageEl.textContent = `${(ageS/60).toFixed(1)}min ago`; ageEl.className = ""; }
    else                 { ageEl.textContent = `${(ageS/60).toFixed(0)}min ago (stale)`; ageEl.className = "neg"; }
  } else {
    ageEl.textContent = "no tick yet"; ageEl.className = "muted";
  }

  const snapEl = document.getElementById("health-snap-age");
  if (d.ts) {
    const ageS = (Date.now() - new Date(d.ts).getTime()) / 1000;
    if (ageS < 30)       { snapEl.textContent = `${ageS.toFixed(0)}s ago`; snapEl.className = "pos"; }
    else if (ageS < 300) { snapEl.textContent = `${(ageS/60).toFixed(1)}min ago`; snapEl.className = ""; }
    else                 { snapEl.textContent = `${(ageS/60).toFixed(0)}min ago — bot may be down!`; snapEl.className = "neg"; }
  } else { snapEl.textContent = "—"; }

  setText("health-cycle", (d.cycle ?? 0).toLocaleString());
  setText("health-bars", (d.bars_processed ?? 0).toLocaleString());
  setText("health-fired", d.signals_fired ?? 0);
  setText("health-blocked", d.signals_blocked ?? 0);
  setText("health-pending", (d.fib?.pending_setups ?? 0));
  const errEl = document.getElementById("health-error");
  errEl.textContent = d.last_error || "none";
  errEl.className = d.last_error ? "neg" : "muted";

  // Banner: top-line interpretation
  const banner = document.getElementById("health-banner");
  if (!d.ts || (Date.now() - new Date(d.ts).getTime())/1000 > 300) {
    banner.textContent = "⚠ bot may be down (no recent snapshot)";
    banner.className = "neg";
  } else if (!mkt.open) {
    banner.textContent = "market closed — bot idle";
    banner.className = "muted";
  } else if (src === "synth") {
    banner.textContent = "running on SYNTH bars — fewer signals expected";
    banner.className = "muted";
  } else if ((d.signals_fired ?? 0) === 0 && (d.bars_processed ?? 0) > 60) {
    banner.textContent = "open & processing but zero signals — recheck strategy params";
    banner.className = "neg";
  } else {
    banner.textContent = "trading ✓";
    banner.className = "pos";
  }
}

// Sim baseline (window=4, target=12pt, 2 MNQ, $0.74 RT, 0.25pt adv slip).
// Validated on 3-month NQ tick data + OOS split-half. Used for drift detection.
const SIM_BASELINE = {
  ret_mo: 21.19, dd_pct: 1.66, dd_usd: 828,
  wr: 43.0, rr: 1.65, trades_per_mo: 2998,
};

function renderDriftMonitor(d) {
  const all = (d.recent_trades || []).filter(t => t.exit_ts && t.pnl_usd !== undefined);
  if (all.length === 0) {
    setText("live-ret-mo", "—");
    setText("live-dd", "—");
    setText("live-wr-rr", "—");
    setText("live-trades-mo", "—");
    return;
  }
  const pnls = all.map(t => t.pnl_usd);
  const wins = pnls.filter(p => p > 0);
  const losses = pnls.filter(p => p < 0);
  const totalPnl = pnls.reduce((a, b) => a + b, 0);
  const wr = wins.length / pnls.length * 100;
  const avgW = wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
  const avgL = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : 0;
  const rr = avgL !== 0 ? Math.abs(avgW / avgL) : 0;
  // running DD
  let peak = 0, run = 0, maxDd = 0;
  for (const p of pnls) { run += p; if (run > peak) peak = run; if (peak - run > maxDd) maxDd = peak - run; }
  // annualise from elapsed time of the trade window
  const firstTs = new Date(all[all.length - 1].entry_ts || all[all.length - 1].ts).getTime();
  const lastTs  = new Date(all[0].exit_ts || all[0].ts).getTime();
  const days = Math.max(1, (lastTs - firstTs) / 86400000);
  const months = days / 30.44;
  const retMo = totalPnl / 50000 * 100 / months;
  const tradesMo = pnls.length / months;
  setText("live-ret-mo", (retMo >= 0 ? "+" : "") + retMo.toFixed(2) + "%");
  setText("live-dd", "$" + maxDd.toFixed(0) + " (" + (maxDd/50000*100).toFixed(2) + "%)");
  setText("live-wr-rr", wr.toFixed(1) + "% / " + rr.toFixed(2));
  setText("live-trades-mo", tradesMo.toFixed(0));
  // Verdict only when we have enough trades
  const el = document.getElementById("live-drift");
  if (!el) return;
  if (pnls.length < 30) {
    el.textContent = "need ≥30 trades to compare (" + pnls.length + ")";
    el.className = "muted";
    return;
  }
  const retDiff = retMo - SIM_BASELINE.ret_mo;
  if (Math.abs(retDiff) < 2) { el.textContent = "matching sim ✓"; el.className = "pos"; }
  else if (retDiff > 0) { el.textContent = "above sim by " + retDiff.toFixed(1) + "%/mo"; el.className = "pos"; }
  else { el.textContent = "below sim by " + Math.abs(retDiff).toFixed(1) + "%/mo"; el.className = "neg"; }
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
// Active price-line handles keyed by setup id (side|level50). Lets us
// remove lines whose setups have expired / fired / been Lucid-blocked
// without redrawing the whole chart on every poll.
const _setupLines = {};

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
  updateChartMarkers();
  updateSetupLines();
  updateTradeLineSegments();
  window.addEventListener("resize", () => {
    chart.resize(el.clientWidth, el.clientHeight);
  });
}

// DISABLED per user request — chart shows BUY/SELL arrows only, no lines.
// Pending-setup horizontal lines and active-trade level lines were
// removed for chart clarity. Any previously-drawn lines are cleaned up
// here on each poll so the chart stays clean if the bot restarts with
// existing line state.
function updateSetupLines() {
  if (!candleSeries) return;
  Object.keys(_setupLines).forEach(key => {
    try { _setupLines[key].forEach(l => candleSeries.removePriceLine(l)); }
    catch (e) {}
    delete _setupLines[key];
  });
}

// DISABLED per user request — chart shows BUY/SELL arrows only, no lines.
// Stop/target/entry line segments removed for chart clarity. Cleans up
// any existing series on each poll so stale lines don't linger.
const _tradeLineSeries = {};   // kept for cleanup of any existing series
function updateTradeLineSegments() {
  if (!chart) return;
  Object.keys(_tradeLineSeries).forEach(key => {
    try { _tradeLineSeries[key].forEach(s => chart.removeSeries(s)); }
    catch (e) {}
    delete _tradeLineSeries[key];
  });
}

// Auto-expiring trade markers on the candle chart.
// LONG  → green up-arrow below the bar at entry, red/green down-arrow
//         above the bar at exit with the P&L as the marker text.
// SHORT → red down-arrow above the bar at entry, up-arrow below the
//         bar at exit with the P&L as the marker text.
// Markers are dropped once the trade is older than MARKER_TTL_MS so
// the chart doesn't fill up with stale arrows.
const MARKER_TTL_MS = 60 * 60 * 1000;  // 1 hour
function updateChartMarkers() {
  if (!candleSeries) return;
  const trades = (state.data && state.data.recent_trades) || [];
  const cutoff = Date.now() - MARKER_TTL_MS;
  const markers = [];
  trades.forEach(t => {
    const exitT = new Date(t.ts).getTime();
    if (exitT < cutoff) return;
    // Prefer armed_at_ts (the bar that first touched level50) so the
    // entry arrow lands on the candle that triggered the entry, not the
    // tick-later candle where the bot processed the fill. Fall back to
    // entry_ts for older records that don't have it yet.
    const entryT = new Date(t.armed_at_ts || t.entry_ts || t.ts).getTime();
    const pnl = t.pnl_usd || 0;
    const win = pnl >= 0;
    const pnlStr = (pnl >= 0 ? "+$" : "-$") +
      Math.abs(pnl).toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (t.side === "LONG") {
      markers.push({
        time: Math.floor(entryT / 1000),
        position: "belowBar", color: "#22d39a", shape: "arrowUp",
        text: `LONG ${t.entry_px?.toFixed(2) ?? ""}`,
      });
      markers.push({
        time: Math.floor(exitT / 1000),
        position: "aboveBar", color: win ? "#22d39a" : "#ff5470",
        shape: "arrowDown",
        text: `${pnlStr} · ${t.exit_reason}`,
      });
    } else {
      markers.push({
        time: Math.floor(entryT / 1000),
        position: "aboveBar", color: "#ff5470", shape: "arrowDown",
        text: `SHORT ${t.entry_px?.toFixed(2) ?? ""}`,
      });
      markers.push({
        time: Math.floor(exitT / 1000),
        position: "belowBar", color: win ? "#22d39a" : "#ff5470",
        shape: "arrowUp",
        text: `${pnlStr} · ${t.exit_reason}`,
      });
    }
  });
  // Lightweight Charts requires markers in ascending time order
  markers.sort((a, b) => a.time - b.time);
  try { candleSeries.setMarkers(markers); } catch (e) { /* series may not be ready */ }
}

// ---- Performance graphs --------------------------------------------------
// Hit-test regions for tooltips: { canvasId: [{x,y,r,html} | {x0,x1,y0,y1,html}, ...] }
const _hitRegions = {};

function renderPerformanceGraphs() {
  if (!state.trades && !state.data) return;
  const trades = (state.data && state.data.recent_trades) || [];
  drawEquityCurve(trades);
  drawMonthlyPnl(trades);
  drawHoldHistogram(trades);
  drawWinLossHistogram(trades);
}

function _attachTooltip(canvasId, tooltipId) {
  const c = document.getElementById(canvasId);
  const tt = document.getElementById(tooltipId);
  if (!c || !tt || c.dataset.ttBound === "1") return;
  c.dataset.ttBound = "1";
  const handleMove = (ev) => {
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    const regions = _hitRegions[canvasId] || [];
    let hit = null;
    for (const r of regions) {
      if (r.r !== undefined) {
        const dx = x - r.x, dy = y - r.y;
        if (dx*dx + dy*dy <= r.r * r.r) { hit = r; break; }
      } else if (x >= r.x0 && x <= r.x1 && y >= r.y0 && y <= r.y1) {
        hit = r; break;
      }
    }
    // also catch nearest line-point within 30px on equity curve
    if (!hit && (_hitRegions[canvasId] || []).length) {
      let best = null, bd = 30 * 30;
      for (const r of regions) {
        if (r.r === undefined) continue;
        const dx = x - r.x, dy = y - r.y;
        const d2 = dx*dx + dy*dy;
        if (d2 < bd) { bd = d2; best = r; }
      }
      if (best) hit = best;
    }
    if (hit) {
      tt.innerHTML = hit.html;
      tt.classList.add("show");
      // position to right of cursor unless near edge
      const ttW = tt.offsetWidth || 160;
      const ttH = tt.offsetHeight || 60;
      let tx = x + 12, ty = y - ttH - 8;
      if (tx + ttW > rect.width) tx = x - ttW - 12;
      if (ty < 0) ty = y + 12;
      tt.style.left = tx + "px";
      tt.style.top = ty + "px";
    } else {
      tt.classList.remove("show");
    }
  };
  c.addEventListener("mousemove", handleMove);
  c.addEventListener("mouseleave", () => tt.classList.remove("show"));
  c.addEventListener("click", handleMove);
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
  _hitRegions["chart-equity"] = [];
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const sorted = trades.slice().reverse();
  let bal = start;
  const points = [{ v: start, t: null, trade: null }];
  sorted.forEach(t => { bal += (t.pnl_usd || 0); points.push({ v: bal, t: t.ts, trade: t }); });
  const minV = Math.min(...points.map(p => p.v)), maxV = Math.max(...points.map(p => p.v));
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
  const xy = points.map((p, i) => ({
    p,
    x: padX + (i / Math.max(points.length - 1, 1)) * (w - 2 * padX),
    y: h - padY - ((p.v - minV) / range) * (h - 2 * padY),
  }));
  ctx.beginPath();
  xy.forEach(({x, y}, i) => { if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  // fill under
  ctx.lineTo(w - padX, h - padY); ctx.lineTo(padX, h - padY); ctx.closePath();
  ctx.fillStyle = gradient; ctx.fill();
  // line on top
  ctx.beginPath();
  xy.forEach(({x, y}, i) => { if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
  ctx.strokeStyle = "#22d39a"; ctx.lineWidth = 2; ctx.stroke();
  // hit regions: 6px radius at every point
  xy.forEach(({p, x, y}, i) => {
    const pnl = p.v - 50000;
    const pnlClass = pnl >= 0 ? "pos" : "neg";
    const date = p.t ? new Date(p.t).toLocaleString() : "Start";
    const tradeRow = p.trade
      ? `<div class="tt-row"><span class="tt-label">Trade</span><span class="tt-value ${(p.trade.pnl_usd||0) >= 0 ? 'pos' : 'neg'}">${p.trade.side} ${fmtUsd(p.trade.pnl_usd||0)}</span></div>`
      : "";
    _hitRegions["chart-equity"].push({
      x, y, r: 8,
      html: `
        <div class="tt-row"><span class="tt-label">Date</span><span class="tt-value">${date}</span></div>
        <div class="tt-row"><span class="tt-label">Balance</span><span class="tt-value">${fmtUsdPlain(p.v)}</span></div>
        <div class="tt-row"><span class="tt-label">P&L vs start</span><span class="tt-value ${pnlClass}">${fmtUsd(pnl)}</span></div>
        <div class="tt-row"><span class="tt-label">Trade #</span><span class="tt-value">${i}</span></div>
        ${tradeRow}`,
    });
  });
  _attachTooltip("chart-equity", "tt-equity");
}

function drawMonthlyPnl(trades) {
  const r = _setupCanvas("chart-monthly"); if (!r) return;
  const { ctx, w, h } = r;
  _hitRegions["chart-monthly"] = [];
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const months = {};
  trades.forEach(t => {
    const d = new Date(t.ts);
    const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    if (!months[key]) months[key] = { pnl: 0, n: 0, wins: 0, losses: 0 };
    const p = t.pnl_usd || 0;
    months[key].pnl += p;
    months[key].n++;
    if (p > 0) months[key].wins++;
    else if (p < 0) months[key].losses++;
  });
  const keys = Object.keys(months).sort();
  const vals = keys.map(k => months[k].pnl);
  if (!vals.length) return;
  const padX = 30, padY = 20;
  const maxV = Math.max(...vals.map(Math.abs), 1);
  const bw = (w - 2 * padX) / Math.max(keys.length, 1);
  // zero line
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  const yZero = h / 2;
  ctx.beginPath(); ctx.moveTo(padX, yZero); ctx.lineTo(w - padX, yZero); ctx.stroke();
  // bars
  keys.forEach((k, i) => {
    const v = months[k].pnl;
    const x = padX + i * bw + 2;
    const bh = (Math.abs(v) / maxV) * (h / 2 - padY);
    ctx.fillStyle = v >= 0 ? "#22d39a" : "#ff5470";
    const by = v >= 0 ? yZero - bh : yZero;
    ctx.fillRect(x, by, bw - 4, bh);
    // hit region for this month
    const wr = (v >= 0 ? months[k].wins : months[k].losses);
    const winRate = months[k].n ? months[k].wins / months[k].n : 0;
    _hitRegions["chart-monthly"].push({
      x0: x, x1: x + bw - 4,
      y0: Math.min(by, yZero), y1: Math.max(by + bh, yZero),
      html: `
        <div class="tt-row"><span class="tt-label">Month</span><span class="tt-value">${k}</span></div>
        <div class="tt-row"><span class="tt-label">P&L</span><span class="tt-value ${v >= 0 ? 'pos' : 'neg'}">${fmtUsd(v)}</span></div>
        <div class="tt-row"><span class="tt-label">Trades</span><span class="tt-value">${months[k].n}</span></div>
        <div class="tt-row"><span class="tt-label">Wins</span><span class="tt-value pos">${months[k].wins}</span></div>
        <div class="tt-row"><span class="tt-label">Losses</span><span class="tt-value neg">${months[k].losses}</span></div>
        <div class="tt-row"><span class="tt-label">Win rate</span><span class="tt-value">${fmtPct(winRate)}</span></div>`,
    });
  });
  // x labels (every other if many)
  ctx.fillStyle = "#5d6b85"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
  const step = keys.length > 12 ? Math.ceil(keys.length / 12) : 1;
  keys.forEach((k, i) => {
    if (i % step === 0) ctx.fillText(k.slice(2), padX + i * bw + bw / 2, h - 4);
  });
  _attachTooltip("chart-monthly", "tt-monthly");
}

function drawHoldHistogram(trades) {
  const r = _setupCanvas("chart-holds"); if (!r) return;
  const { ctx, w, h } = r;
  _hitRegions["chart-holds"] = [];
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const buckets = [
    { label: "≤10s", lo: 0,    hi: 10,   c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "10-30s", lo: 10, hi: 30,   c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "30-60s", lo: 30, hi: 60,   c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "1-5m",   lo: 60, hi: 300,  c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "5-30m",  lo: 300, hi: 1800, c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "30m-2h", lo: 1800, hi: 7200, c: 0, pnl: 0, wins: 0, losses: 0 },
    { label: "2-8h",   lo: 7200, hi: 28800, c: 0, pnl: 0, wins: 0, losses: 0 },
  ];
  trades.forEach(t => {
    const s = t.hold_s ?? 0;
    const p = t.pnl_usd || 0;
    for (const b of buckets) if (s >= b.lo && s < b.hi) {
      b.c++; b.pnl += p;
      if (p > 0) b.wins++; else if (p < 0) b.losses++;
      break;
    }
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
    // hit region
    _hitRegions["chart-holds"].push({
      x0: x, x1: x + bw - 8,
      y0: h - padY - bh - 14, y1: h - padY,
      html: `
        <div class="tt-row"><span class="tt-label">Bucket</span><span class="tt-value">${b.label}</span></div>
        <div class="tt-row"><span class="tt-label">Trades</span><span class="tt-value">${b.c}</span></div>
        <div class="tt-row"><span class="tt-label">P&L</span><span class="tt-value ${b.pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(b.pnl)}</span></div>
        <div class="tt-row"><span class="tt-label">Wins</span><span class="tt-value pos">${b.wins}</span></div>
        <div class="tt-row"><span class="tt-label">Losses</span><span class="tt-value neg">${b.losses}</span></div>
        ${isMicro ? '<div class="tt-row"><span class="tt-label">Lucid</span><span class="tt-value neg">microscalp range</span></div>' : ''}`,
    });
  });
  _attachTooltip("chart-holds", "tt-holds");
}

function drawWinLossHistogram(trades) {
  const r = _setupCanvas("chart-wlhist"); if (!r) return;
  const { ctx, w, h } = r;
  _hitRegions["chart-wlhist"] = [];
  if (!trades.length) {
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const wins = trades.filter(t => (t.pnl_usd || 0) > 0);
  const losses = trades.filter(t => (t.pnl_usd || 0) < 0);
  const padX = 30, padY = 30;
  const winTotal = wins.reduce((s, t) => s + t.pnl_usd, 0);
  const lossTotal = losses.reduce((s, t) => s + t.pnl_usd, 0);
  const lanes = [
    { key: "wins", label: `Wins (${wins.length})`, color: "#22d39a",
      n: wins.length, avg: wins.length ? winTotal / wins.length : 0,
      total: winTotal, biggest: wins.length ? Math.max(...wins.map(t => t.pnl_usd)) : 0 },
    { key: "losses", label: `Losses (${losses.length})`, color: "#ff5470",
      n: losses.length, avg: losses.length ? lossTotal / losses.length : 0,
      total: lossTotal, biggest: losses.length ? Math.min(...losses.map(t => t.pnl_usd)) : 0 },
  ];
  // Bar heights + labels show TOTALs (not averages) — totals are the
  // metric that actually matters (your aggregate profit vs aggregate loss).
  const maxV = Math.max(...lanes.map(l => Math.abs(l.total)), 1);
  const bw = (w - 2 * padX) / 2;
  lanes.forEach((lane, i) => {
    const x = padX + i * bw + 20;
    const bh = (Math.abs(lane.total) / maxV) * (h - 2 * padY);
    ctx.fillStyle = lane.color;
    ctx.fillRect(x, h - padY - bh, bw - 40, bh);
    ctx.fillStyle = lane.color; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText(fmtUsd(lane.total), x + (bw - 40) / 2, h - padY - bh - 6);
    ctx.fillStyle = "#a4b1c7"; ctx.font = "11px sans-serif";
    ctx.fillText(lane.label, x + (bw - 40) / 2, h - 10);
    _hitRegions["chart-wlhist"].push({
      x0: x, x1: x + bw - 40,
      y0: h - padY - bh - 20, y1: h - padY,
      html: `
        <div class="tt-row"><span class="tt-label">Category</span><span class="tt-value">${lane.key === 'wins' ? 'Wins' : 'Losses'}</span></div>
        <div class="tt-row"><span class="tt-label">Count</span><span class="tt-value">${lane.n}</span></div>
        <div class="tt-row"><span class="tt-label">Average</span><span class="tt-value ${lane.key === 'wins' ? 'pos' : 'neg'}">${fmtUsd(lane.avg)}</span></div>
        <div class="tt-row"><span class="tt-label">Total</span><span class="tt-value ${lane.key === 'wins' ? 'pos' : 'neg'}">${fmtUsd(lane.total)}</span></div>
        <div class="tt-row"><span class="tt-label">Biggest</span><span class="tt-value ${lane.key === 'wins' ? 'pos' : 'neg'}">${fmtUsd(lane.biggest)}</span></div>`,
    });
  });
  _attachTooltip("chart-wlhist", "tt-wlhist");
}

// ---- Master render ------------------------------------------------------
function renderAll() {
  if (!state.data) return;
  renderTopbar(state.data);
  renderLive(state.data);
  renderFunded(state.data);
  renderTradesTable();
  renderPerformanceGraphs();
  updateChartMarkers();
  updateSetupLines();
  updateTradeLineSegments();
}
