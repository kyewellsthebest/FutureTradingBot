/* Trading Bot dashboard — broker-only dark UI.
   Data: /api/broker/stats (10s), /api/broker/position (10s),
         /api/broker/trades (30s), /api/pause_status (15s).
   Charts: lightweight-charts v4 with crosshair readouts (tap on mobile). */

"use strict";

const $ = (id) => document.getElementById(id);
const account = localStorage.getItem("hftbot.account") || "1";
const af = (u) => u + (u.includes("?") ? "&" : "?") +
  "account=" + encodeURIComponent(account) + "&source=broker";

/* ---------- formatting ---------- */
const fmtUsd = (v, sign) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return (v < 0 ? "-" : (sign ? "+" : "")) + "$" +
    Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
};
const fmtUsd2 = (v, sign) => {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return (v < 0 ? "-" : (sign ? "+" : "")) + "$" +
    Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
const paint = (el, v) => {
  el.classList.remove("pos-t", "neg-t");
  if (v > 0) el.classList.add("pos-t");
  if (v < 0) el.classList.add("neg-t");
};
const reveal = (el) => { if (el) el.classList.add("done"); };
/* Lightweight-charts renders unix timestamps in UTC on the axis. Shift
   every point by the viewer's own UTC offset so the axis (and crosshair
   time tag) read in LOCAL time — Australian time on the user's phone —
   then un-shift before formatting readout text with Date (which is
   already local). */
const TZOFF = -new Date().getTimezoneOffset() * 60;
const fmtWhen = (shiftedSec) => {
  const d = new Date((shiftedSec - TZOFF) * 1000);
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) +
    " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
};

/* ---------- loading bar ---------- */
let loadTimer = null;
function loadStart() {
  const b = $("loadbar");
  b.classList.add("on"); b.style.width = "35%";
  clearTimeout(loadTimer);
  loadTimer = setTimeout(() => (b.style.width = "70%"), 350);
}
function loadDone() {
  const b = $("loadbar");
  b.style.width = "100%";
  clearTimeout(loadTimer);
  setTimeout(() => { b.classList.remove("on"); b.style.width = "0%"; }, 400);
}

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    document.querySelectorAll(".page").forEach((p) =>
      p.classList.toggle("active", p.id === "page-" + t.dataset.page));
    requestAnimationFrame(fitCharts);
  }));

/* ---------- lightweight-charts theming ---------- */
const CHART_OPTS = {
  layout: { background: { color: "transparent" }, textColor: "#656d84",
            fontFamily: "'Inter', sans-serif", fontSize: 11 },
  grid: { vertLines: { color: "rgba(255,255,255,0.04)" },
          horzLines: { color: "rgba(255,255,255,0.04)" } },
  rightPriceScale: { borderVisible: false },
  timeScale: { borderVisible: false, timeVisible: true, secondsVisible: false },
  crosshair: {
    mode: 0,
    vertLine: { color: "#9085e9", width: 1, style: 2, labelBackgroundColor: "#9085e9" },
    horzLine: { color: "#9085e9", width: 1, style: 2, labelBackgroundColor: "#9085e9" },
  },
  handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
  handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: false },
};

let LW = null;
let eqChart = null, eqSeries = null, eqData = [];
let dlChart = null, dlSeries = null, dlMap = {};
let spChart = null, spSeries = null;
let equityRange = "week";

function waitForLW(cb) {
  if (window.LightweightCharts) { LW = window.LightweightCharts; cb(); return; }
  setTimeout(() => waitForLW(cb), 120);
}

function makeCharts() {
  // equity
  eqChart = LW.createChart($("chart-equity"), CHART_OPTS);
  eqSeries = eqChart.addAreaSeries({
    lineColor: "#9085e9", lineWidth: 2,
    topColor: "rgba(144,133,233,0.28)", bottomColor: "rgba(144,133,233,0.02)",
    priceLineVisible: false, lastValueVisible: true,
    priceFormat: { type: "custom", formatter: (v) => fmtUsd(v) },
  });
  eqChart.subscribeCrosshairMove((p) => {
    const out = $("equity-readout");
    if (!p || !p.time || !p.seriesData || !p.seriesData.get(eqSeries)) {
      out.innerHTML = "&nbsp;"; return;
    }
    const v = p.seriesData.get(eqSeries).value;
    const pt = eqData.find((d) => d.time === p.time);
    out.innerHTML = `<b>${fmtWhen(p.time)}</b> · P&amp;L <b>${fmtUsd2(v, true)}</b>` +
      (pt && pt.trade !== undefined ? ` · trade ${fmtUsd2(pt.trade, true)}` : "");
  });

  // daily histogram
  dlChart = LW.createChart($("chart-daily"), { ...CHART_OPTS,
    timeScale: { ...CHART_OPTS.timeScale, timeVisible: false } });
  dlSeries = dlChart.addHistogramSeries({
    priceLineVisible: false, lastValueVisible: false,
    priceFormat: { type: "custom", formatter: (v) => fmtUsd(v) },
  });
  dlChart.subscribeCrosshairMove((p) => {
    const out = $("daily-readout");
    if (!p || !p.time || !p.seriesData || !p.seriesData.get(dlSeries)) {
      out.innerHTML = "&nbsp;"; return;
    }
    const t = p.time; // business-day object or 'yyyy-mm-dd'
    const key = typeof t === "string" ? t :
      `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;
    const d = dlMap[key];
    if (!d) { out.innerHTML = "&nbsp;"; return; }
    out.innerHTML = `<b>${key}</b> · P&amp;L <b>${fmtUsd2(d.pnl, true)}</b> · ` +
      `${d.n} trades · ${d.win_rate}% win`;
  });

  // balance sparkline (mini, no axes)
  spChart = LW.createChart($("spark-balance"), {
    layout: CHART_OPTS.layout,
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    rightPriceScale: { visible: false }, leftPriceScale: { visible: false },
    timeScale: { visible: false },
    crosshair: { mode: 2, vertLine: { visible: false }, horzLine: { visible: false } },
    handleScroll: false, handleScale: false,
  });
  spSeries = spChart.addAreaSeries({
    lineColor: "#3987e5", lineWidth: 2,
    topColor: "rgba(57,135,229,0.25)", bottomColor: "rgba(57,135,229,0.02)",
    priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
  });

  new ResizeObserver(fitCharts).observe(document.body);
  fitCharts();
}

function fitCharts() {
  [[eqChart, "chart-equity"], [dlChart, "chart-daily"], [spChart, "spark-balance"]]
    .forEach(([c, id]) => {
      const el = $(id);
      if (c && el && el.clientWidth > 0)
        c.resize(el.clientWidth, el.clientHeight);
    });
}

/* ---------- equity range ---------- */
$("equity-range").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  document.querySelectorAll("#equity-range button").forEach((x) =>
    x.classList.toggle("on", x === b));
  equityRange = b.dataset.r;
  renderEquity();
});

function renderEquity() {
  if (!eqSeries || !eqData.length) return;
  const now = Date.now() / 1000 + TZOFF;   // eqData times are TZ-shifted
  const spans = { day: 86400, week: 7 * 86400, month: 31 * 86400, all: Infinity };
  const cut = now - (spans[equityRange] || Infinity);
  let pts = eqData.filter((d) => d.time >= cut);
  if (pts.length < 2) pts = eqData.slice(-Math.min(eqData.length, 50));
  eqSeries.setData(pts.map((d) => ({ time: d.time, value: d.value })));
  eqChart.timeScale().fitContent();
}

/* ---------- stats / KPIs ---------- */
let firstStats = true;
async function pollStats() {
  try {
    loadStart();
    const r = await fetch(af("/api/broker/stats"));
    const s = await r.json();
    loadDone();
    if (!s || s.configured === false) return;

    const bal = s.net_liq ?? s.balance;
    $("kpi-balance").textContent = fmtUsd(bal);
    reveal($("kpi-balance"));
    const open = s.open_pnl || 0;
    $("kpi-open").textContent = open ? `open P&L ${fmtUsd2(open, true)}` : "no open P&L";

    const today = s.realized_pnl ?? 0;
    const t = $("kpi-today");
    t.textContent = fmtUsd(today, true); paint(t, today); reveal(t);
    $("kpi-today-ico").textContent = today >= 0 ? "↗" : "↘";

    const wk = s.week_realized ?? 0;
    const w = $("kpi-week");
    w.textContent = fmtUsd(wk, true); paint(w, wk); reveal(w);

    const sum = s.summary || {};
    $("kpi-today-n").textContent = `${sum.n_trades ?? 0} trades total`;
    $("kpi-week-sub").textContent =
      sum.win_rate !== undefined ? `${sum.win_rate}% win rate` : "";

    // stat chips
    const chip = (id, txt, v) => { const el = $(id); el.textContent = txt;
      if (v !== undefined) paint(el, v); reveal(el); };
    chip("st-n", String(sum.n_trades ?? "—"));
    chip("st-pf", sum.profit_factor != null ? Number(sum.profit_factor).toFixed(2) : "—");
    chip("st-aw", fmtUsd2(sum.avg_win, true), 1);
    chip("st-al", fmtUsd2(sum.avg_loss), -1);
    chip("st-dd", fmtUsd(-Math.abs(sum.max_drawdown ?? 0)), -1);
    chip("st-total", fmtUsd(sum.total_pnl, true), sum.total_pnl);

    // donut
    const wins = sum.wins || 0, losses = sum.losses || 0;
    const flat = Math.max(0, (sum.n_trades || 0) - wins - losses);
    drawDonut(wins, losses, flat, sum.win_rate ?? 0);
    $("lg-wins").textContent = wins;
    $("lg-losses").textContent = losses;
    $("lg-flat").textContent = flat;

    // equity curve
    const seen = new Set();
    eqData = (s.equity_curve || []).map((p) => {
      let ts = Math.floor(new Date(p.ts).getTime() / 1000) + TZOFF;
      while (seen.has(ts)) ts += 1;          // strictly increasing
      seen.add(ts);
      return { time: ts, value: p.cum_pnl, trade: p.trade_pnl };
    });
    if (eqData.length) { renderEquity(); $("equity-skel").classList.add("done"); }
    else if (firstStats) {
      $("equity-readout").textContent = "No closed trades yet.";
      $("equity-skel").classList.add("done");
    }

    // sparkline: balance path = starting + cum
    if (spSeries && eqData.length) {
      const last = eqData[eqData.length - 1].value;
      const base = (typeof s.starting === "number" ? s.starting : (bal - last)) ;
      spSeries.setData(eqData.slice(-40).map((d) => ({ time: d.time, value: base + d.value })));
      spChart.timeScale().fitContent();
    }

    // daily histogram
    dlMap = {};
    const bars = (s.daily || []).map((d) => {
      dlMap[d.date] = d;
      return { time: d.date, value: d.pnl,
               color: d.pnl >= 0 ? "#199e70" : "#e66767" };
    });
    if (dlSeries && bars.length) {
      dlSeries.setData(bars);
      dlChart.timeScale().fitContent();
      $("daily-skel").classList.add("done");
    } else if (firstStats) $("daily-skel").classList.add("done");

    firstStats = false;
  } catch (e) { loadDone(); }
}

function drawDonut(wins, losses, flat, wr) {
  const svg = $("donut");
  const total = Math.max(1, wins + losses + flat);
  const R = 53, C = 2 * Math.PI * R;
  const seg = (n, color, offset) =>
    `<circle cx="60" cy="60" r="${R}" stroke="${color}" ` +
    `stroke-dasharray="${Math.max(0.5, (n / total) * C - 3)} ${C}" ` +
    `stroke-dashoffset="${-offset * C}"></circle>`;
  let html = `<circle cx="60" cy="60" r="${R}" stroke="#1f2331" stroke-dasharray="${C}"></circle>`;
  let off = 0;
  [[wins, "#199e70"], [losses, "#e66767"], [flat, "#656d84"]].forEach(([n, c]) => {
    if (n > 0) { html += seg(n, c, off); off += n / total; }
  });
  svg.innerHTML = html;
  const el = $("donut-wr");
  el.textContent = `${Math.round(wr)}%`;
  reveal(el);
}

/* ---------- position ---------- */
async function pollPosition() {
  try {
    const r = await fetch(af("/api/broker/position"));
    const j = await r.json();
    const el = $("kpi-pos"), sub = $("kpi-pos-sub"), ico = $("kpi-pos-ico");
    const p = j && j.position;
    if (p && p.netPos) {
      const side = p.netPos > 0 ? "LONG" : "SHORT";
      el.textContent = `${side} ${Math.abs(p.netPos)}`;
      el.classList.toggle("pos-t", p.netPos > 0);
      el.classList.toggle("neg-t", p.netPos < 0);
      ico.textContent = p.netPos > 0 ? "▲" : "▼";
      sub.textContent = p.netPrice ? `avg ${Number(p.netPrice).toFixed(2)}` : "";
    } else {
      el.textContent = "FLAT";
      el.classList.remove("pos-t", "neg-t");
      ico.textContent = "▣";
      sub.textContent = "no open position";
    }
    reveal(el);
  } catch (e) { /* keep last */ }
}

/* ---------- trades ---------- */
let allTrades = [], shownTrades = 25;
async function pollTrades() {
  try {
    const r = await fetch(af("/api/broker/trades"));
    const j = await r.json();
    allTrades = Array.isArray(j) ? j : (j.trades || []);
    allTrades.sort((a, b) => String(b.exit_time || "").localeCompare(String(a.exit_time || "")));
    renderTrades();
  } catch (e) { /* retry next poll */ }
}
function renderTrades() {
  const list = $("trades-list");
  if (!allTrades.length) {
    list.innerHTML = `<div class="muted small" style="padding:14px 4px">No trades yet.</div>`;
    $("trades-count").textContent = "";
    return;
  }
  $("trades-count").textContent = `${allTrades.length} total`;
  const rows = allTrades.slice(0, shownTrades).map((t) => {
    const side = String(t.side || "").toUpperCase().startsWith("L") ? "L" : "S";
    const pnl = Number(t.pnl_usd || 0);
    const et = t.exit_time ? new Date(t.exit_time) : null;
    const when = et ? et.toLocaleDateString(undefined, { day: "numeric", month: "short" }) +
      " " + et.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—";
    return `<div class="trade-row">
      <div class="tr-side ${side}">${side}</div>
      <div class="tr-mid">
        <div class="tr-line1">${side === "L" ? "Long" : "Short"} ${t.qty || 1} · ${Number(t.entry_px).toFixed(2)} → ${Number(t.exit_px).toFixed(2)}</div>
        <div class="tr-line2">${when}</div>
      </div>
      <div class="tr-pnl ${pnl > 0 ? "pos-t" : pnl < 0 ? "neg-t" : ""}">${fmtUsd2(pnl, true)}</div>
    </div>`;
  }).join("");
  list.innerHTML = rows;
  $("trades-more").hidden = allTrades.length <= shownTrades;
}
$("trades-more").addEventListener("click", () => { shownTrades += 25; renderTrades(); });

/* ---------- pause ---------- */
async function pollPause() {
  try {
    const r = await fetch(af("/api/pause_status"));
    const j = await r.json();
    setPaused(!!j.paused);
  } catch (e) { /* ignore */ }
}
function setPaused(p) {
  const btn = $("btn-pause"), pill = $("pill-status");
  btn.dataset.paused = p ? "1" : "0";
  btn.textContent = p ? "Resume" : "Pause";
  pill.className = "pill " + (p ? "pill-paused" : "pill-live");
  pill.innerHTML = `<span class="dot"></span>${p ? "PAUSED" : "LIVE"}`;
}
$("btn-pause").addEventListener("click", async () => {
  const paused = $("btn-pause").dataset.paused === "1";
  if (!paused && !confirm("Pause the bot? No new entries until resumed.")) return;
  try {
    await fetch(af(paused ? "/api/resume" : "/api/pause"), { method: "POST" });
    setPaused(!paused);
  } catch (e) { alert("Request failed — try again."); }
});

/* ---------- tools ---------- */
$("dl-bundle").addEventListener("click", () => {
  window.location.href = af("/api/download/bundle");
});
document.querySelectorAll("[data-dl]").forEach((b) =>
  b.addEventListener("click", () => {
    window.location.href = af("/api/download/" + b.dataset.dl);
  }));

async function pollEngine() {
  try {
    const r = await fetch(af("/api/data"));
    const j = await r.json();
    const te = (j && (j.trend_engine ||
      (j.live_snapshot && j.live_snapshot.trend_engine))) || null;
    const kv = $("engine-kv");
    if (!te) { kv.innerHTML = `<div class="muted small">Engine snapshot unavailable.</div>`; return; }
    const c = te.counters || {};
    const row = (k, v) => `<div class="row"><span>${k}</span><b>${v}</b></div>`;
    kv.innerHTML =
      row("Strategy", te.strategy || "—") +
      row("Position", te.pos ? `${te.pos.side > 0 ? "LONG" : "SHORT"} ${te.pos.qty} @ ${te.pos.entry_px}` : "flat") +
      row("Pending order", te.pending ? `${te.pending.side > 0 ? "BUY" : "SELL"} ${te.pending.qty} @ ${te.pending.price}` : "none") +
      row("Signals", c.signals ?? "—") +
      row("Filled / canceled", `${c.filled ?? "—"} / ${c.canceled ?? "—"}`) +
      row("Exits", c.exits ?? "—") +
      row("Order errors", c.order_errors ?? "—") +
      row("Disaster exits", c.disaster ?? "—");
  } catch (e) { /* leave as is */ }
}

/* ---------- boot ---------- */
waitForLW(() => {
  makeCharts();
  pollStats(); pollPosition(); pollTrades(); pollPause(); pollEngine();
  setInterval(pollStats, 10000);
  setInterval(pollPosition, 10000);
  setInterval(pollTrades, 30000);
  setInterval(pollPause, 15000);
  setInterval(pollEngine, 30000);
});
