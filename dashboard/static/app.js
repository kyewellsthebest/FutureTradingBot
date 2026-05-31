/* Futures Trading Bot dashboard — Fib 50% frontend.
   Polls /api/data (full snapshot) every 5s. Renders all tabs from one blob. */

const POLL_MS = 5000;
let state = { data: null, candles: null, trades: null };
let chart = null, candleSeries = null;

// Multi-account: every API request is namespaced by ?account=N. The
// active account is persisted in localStorage so a refresh keeps the
// user on whichever account they were viewing.
let currentAccount = localStorage.getItem("hftbot.account") || "1";

// Account-aware fetch wrapper — appends ?account=N to the URL.
function af(url) {
  const sep = url.includes("?") ? "&" : "?";
  return url + sep + "account=" + encodeURIComponent(currentAccount);
}
// Per-account strategy / sim baseline display values. Only the legacy
// account 1 is live; accounts 2/3 were removed by user request.
const ACCOUNT_STRATEGY = {
  "1": {
    label: "Original (target=12)",
    target_label: "12 NQ pts from entry (2.0 RR planned, 1.65 realised)",
    sim_ret: "+21.19%", sim_dd: "$828 (1.66%)",
    sim_wr_rr: "44.0% / 1.65", sim_trades_mo: "~3,300",
    mc_ret: "+21.19%", mc_range: "+17.46% to +25.17%",
    trail_prob: "0.1%", oos: "+12.59% / +30.13% (both beat baseline)",
    sim_ret_mo_num: 21.19, sim_dd_pct_num: 1.66, sim_dd_usd_num: 828,
  },
};

function renderAccountStrategyDisplay() {
  const s = ACCOUNT_STRATEGY[currentAccount] || ACCOUNT_STRATEGY["1"];
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set("strat-target",            s.target_label);
  set("strat-baseline-ret",      s.sim_ret);
  set("strat-baseline-dd",       s.sim_dd);
  set("strat-baseline-wrrr",     s.sim_wr_rr);
  set("strat-baseline-tradesmo", s.sim_trades_mo);
  set("strat-baseline-ret-mc",   s.mc_ret);
  set("strat-baseline-range",    s.mc_range);
  set("strat-baseline-trail",    s.trail_prob);
  set("strat-baseline-oos",      s.oos);
  // Drift Monitor uses the numeric values directly
  SIM_BASELINE.ret_mo = s.sim_ret_mo_num;
  SIM_BASELINE.dd_pct = s.sim_dd_pct_num;
  SIM_BASELINE.dd_usd = s.sim_dd_usd_num;
  // CRITICAL: keep the download links pointing at the current account.
  // Static <a href="/api/export/day"> would always fetch account 1 because
  // the server's before_request hook defaults missing ?account to "1".
  document.querySelectorAll(".js-export").forEach(a => {
    const period = a.dataset.period;
    a.href = `/api/export/${period}?account=${encodeURIComponent(currentAccount)}`;
  });
}

function setAccount(id) {
  if (id === currentAccount) return;
  currentAccount = id;
  localStorage.setItem("hftbot.account", id);
  // Wipe all caches so the new account's data loads fresh.
  state = { data: null, candles: null, trades: null };
  _allTradesCache = { trades: null, ts: 0 };
  if (candleSeries) { try { candleSeries.setData([]); candleSeries.setMarkers([]); } catch (e) {} }
  // Refresh everything immediately
  poll(); pollCandles(); pollTrades();
  renderAccountSwitcher();
  renderAccountStrategyDisplay();
  // Pause state is per-account, so re-fetch when switching.
  pollPauseStatus(true);
}
async function loadAccounts() {
  try {
    const r = await fetch("/api/accounts");
    if (!r.ok) return;
    const j = await r.json();
    window._knownAccounts = j.accounts || ["1"];
    renderAccountSwitcher();
  } catch (e) {}
}
function renderAccountSwitcher() {
  const accounts = window._knownAccounts || ["1"];
  // Label
  const label = document.getElementById("brand-text-label");
  if (label) label.textContent = currentAccount === "1" ? "Futures Trading Bot"
                                                        : `Futures Trading Bot ${currentAccount}`;
  const menu = document.getElementById("account-menu");
  if (!menu) return;
  menu.innerHTML = accounts.map(a => `
    <div class="account-item ${a === currentAccount ? 'active' : ''}" data-account="${a}">
      <span>${a === "1" ? "Futures Trading Bot" : "Futures Trading Bot " + a}</span>
      <span class="account-item-id">#${a}</span>
    </div>`).join("");
  menu.querySelectorAll(".account-item").forEach(el => {
    el.addEventListener("click", () => {
      setAccount(el.dataset.account);
      menu.hidden = true;
    });
  });
}
// Wire up the dropdown toggle once DOM is ready
function _wireAccountSwitcher() {
  const btn = document.getElementById("account-toggle");
  const menu = document.getElementById("account-menu");
  if (!btn || !menu || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.hidden = !menu.hidden;
  });
  document.addEventListener("click", () => { menu.hidden = true; });
}
document.addEventListener("DOMContentLoaded", () => {
  _wireAccountSwitcher();
  renderAccountSwitcher();
  renderAccountStrategyDisplay();  // populate Strategy tab + sim baseline for current account
  loadAccounts();
  setInterval(loadAccounts, 60_000);  // refresh in case ACCOUNTS env adds new ones
  _wirePauseButton();
  pollPauseStatus(true);
  setInterval(pollPauseStatus, 5000);
  _wireResetButton();
  _wireDownloadButtons();
});

// ---- Admin: Reset account ------------------------------------------------
async function _doResetAccount() {
  const btn = document.getElementById("btn-reset-account");
  if (!btn) return;
  const msg = "RESET THIS ACCOUNT?\n\n" +
              "This deletes ALL trade history, balance state, snapshots, " +
              "and pause flags for the currently selected account, and " +
              "removes any orphan account_2/3 data directories.\n\n" +
              "Next bot cycle will start fresh at $50,000.\n\n" +
              "There is no undo.";
  if (!confirm(msg)) return;
  if (!confirm("Are you absolutely sure? Click OK to reset.")) return;
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = "Resetting…";
  try {
    const r = await fetch(af("/api/admin/reset_all?confirm=YES"), { method: "POST" });
    const j = await r.json();
    if (r.ok && j.ok) {
      alert("Account reset.\n\nFiles deleted: " + (j.deleted || []).length +
            "\n\nThe bot will recreate a fresh $50k account on its next cycle. " +
            "Reloading the dashboard now.");
      // Wipe local caches and reload.
      try {
        state = { data: null, candles: null, trades: null };
        _allTradesCache = { trades: null, ts: 0 };
      } catch (e) {}
      window.location.reload();
    } else {
      btn.textContent = prev;
      btn.disabled = false;
      alert("Reset failed: " + (j.error || r.status));
    }
  } catch (e) {
    btn.textContent = prev;
    btn.disabled = false;
    alert("Reset error: " + e);
  }
}
function _wireResetButton() {
  const btn = document.getElementById("btn-reset-account");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", _doResetAccount);
}

// ---- Shadow engine summary (refreshed by main poll) -----------------------
function renderShadowSummary(data) {
  const el = document.getElementById("shadow-summary");
  if (!el) return;
  const s = data && data.shadow_engine;
  if (!s || !s.enabled) {
    el.innerHTML = '<div class="muted">Shadow engine not running (will appear once Railway redeploys).</div>';
    return;
  }
  const sign = (n) => (n >= 0 ? "+" : "");
  const liveTrades = (data && data.lifetime_stats && data.lifetime_stats.n_trades) || 0;
  const livePnl    = (data && data.lifetime_stats && data.lifetime_stats.total_pnl) || 0;
  el.innerHTML = `
    <div class="kv-row"><span>Engine trades</span><b>${s.trades_closed}</b></div>
    <div class="kv-row"><span>Engine win rate</span><b>${s.win_rate.toFixed(1)}%</b></div>
    <div class="kv-row"><span>Engine P&L</span><b class="${s.total_pnl_usd>=0?'pos':'neg'}">$${sign(s.total_pnl_usd)}${s.total_pnl_usd.toFixed(2)}</b></div>
    <div class="kv-row"><span>Live trades</span><b>${liveTrades}</b></div>
    <div class="kv-row"><span>Live P&L</span><b class="${livePnl>=0?'pos':'neg'}">$${sign(livePnl)}${livePnl.toFixed(2)}</b></div>
    <div class="kv-row"><span>Engine cycles</span><b>${s.cycles_processed}</b></div>
    ${s.errors>0 ? `<div class="kv-row"><span>Engine errors</span><b class="neg">${s.errors}</b></div>` : ''}
  `;
}

// ---- Downloads tab ----------------------------------------------------------
function _wireDownloadButtons() {
  document.querySelectorAll(".btn-dl").forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => _doDownload(btn));
  });
}

function _statusEl(message, status) {
  const el = document.getElementById("dl-status");
  if (!el) return;
  const cls = status === "ok"   ? "pos"
            : status === "bad"  ? "neg"
            :                     "muted";
  el.innerHTML = `<div class="${cls}">${message}</div>`;
}

async function _doDownload(btn) {
  const kind = btn.dataset.dl;
  const ext  = btn.dataset.ext || "json";
  const directUrl = btn.dataset.direct;   // for endpoints that already exist
  if (!kind) return;
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Preparing…";
  _statusEl(`Preparing ${kind} (.${ext})…`, "muted");
  try {
    let url;
    if (directUrl) {
      url = af(directUrl);
    } else {
      let q = "";
      if (kind === "bundle") {
        const cb = document.getElementById("dl-include-verify");
        const includeVerify = cb && cb.checked ? "1" : "0";
        q = `?verify=${includeVerify}`;
      }
      url = af(`/api/download/${kind}${q}`);
    }
    const r = await fetch(url, { method: "GET" });
    if (!r.ok) {
      const text = await r.text();
      _statusEl(`Failed (${r.status}): ${text.slice(0,200)}`, "bad");
      return;
    }
    // Extract filename from Content-Disposition if present
    const cd = r.headers.get("Content-Disposition") || "";
    const match = cd.match(/filename="([^"]+)"/);
    const filename = match
      ? match[1]
      : `hftbot_${kind.replace(/\./g,"_")}_${Date.now()}.${ext}`;
    const blob = await r.blob();
    // Trigger a save dialog
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
    const sizeKb = (blob.size / 1024).toFixed(1);
    _statusEl(`✅ Downloaded <code>${filename}</code> (${sizeKb} KB)`, "ok");
  } catch (e) {
    _statusEl(`Error: ${e}`, "bad");
  } finally {
    btn.textContent = original;
    btn.disabled = false;
  }
}

// ---- Pause / Resume ------------------------------------------------------
// User-controlled kill switch for new entries on the active account. Lets
// you skip a hot losing streak or sidestep an expected pump/dump without
// blowing the account. Active trade (if any) is NOT closed -- it runs to
// its existing stop or target. Pause state survives bot restarts (stored as
// a flag file in the account's data dir).
let _pauseBusy = false;
function _renderPauseBtn(paused, sinceIso) {
  const btn = document.getElementById("btn-pause");
  const badge = document.getElementById("badge-paused");
  if (!btn) return;
  btn.dataset.paused = paused ? "1" : "0";
  btn.textContent = paused ? "▶ Resume" : "⏸ Pause";
  if (badge) {
    badge.hidden = !paused;
    if (paused && sinceIso) {
      try {
        const d = new Date(sinceIso);
        badge.title = "Paused since " + d.toLocaleString();
      } catch (e) {}
    }
  }
}
async function pollPauseStatus(force) {
  try {
    const r = await fetch(af("/api/pause_status"));
    if (!r.ok) return;
    const j = await r.json();
    _renderPauseBtn(!!j.paused, j.since);
  } catch (e) {}
}
async function _togglePause() {
  if (_pauseBusy) return;
  const btn = document.getElementById("btn-pause");
  if (!btn) return;
  const isPaused = btn.dataset.paused === "1";
  // Pausing is silent; resuming during a losing streak is the dangerous one --
  // confirm so the user doesn't accidentally re-arm the bot mid-tantrum.
  if (isPaused && !confirm("Resume new entries on this account?")) return;
  _pauseBusy = true;
  btn.disabled = true;
  const prevLabel = btn.textContent;
  btn.textContent = isPaused ? "Resuming…" : "Pausing…";
  try {
    const url = af(isPaused ? "/api/resume" : "/api/pause");
    const r = await fetch(url, { method: "POST",
                                 headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify({ reason: "user_manual" }) });
    if (r.ok) {
      const j = await r.json();
      _renderPauseBtn(!!j.paused, j.since);
    } else {
      btn.textContent = prevLabel;
      alert("Pause/resume failed: " + r.status);
    }
  } catch (e) {
    btn.textContent = prevLabel;
    alert("Pause/resume error: " + e);
  } finally {
    _pauseBusy = false;
    btn.disabled = false;
  }
}
function _wirePauseButton() {
  const btn = document.getElementById("btn-pause");
  if (!btn || btn.dataset.bound) return;
  btn.dataset.bound = "1";
  btn.addEventListener("click", _togglePause);
}

// ---- Tab routing ---------------------------------------------------------
function activateTab(name) {
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tabpane").forEach(p =>
    p.classList.toggle("active", p.id === `pane-${name}`));
  // lazy init chart when chart tab first shown
  if (name === "chart" && !chart) initChart();
  // re-render performance graphs when performance tab opens
  if (name === "performance") {
    _resetChartAnimations();   // re-play entrance animations each visit
    renderPerformanceGraphs();
  }
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

// Smooth count-up animation. Targets any element with a numeric textContent.
// Stores the last-set value on the element so subsequent calls animate FROM
// that value. Reduced-motion users get instant update.
const _animBudget = 700; // ms per transition
function animateNumber(id, target, formatter) {
  const el = document.getElementById(id);
  if (!el) return;
  if (typeof target !== "number" || !isFinite(target)) {
    if (formatter) el.textContent = formatter(target);
    return;
  }
  const fmt = formatter || (n => String(Math.round(n)));
  const prefersReduced = window.matchMedia &&
                          window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced) {
    el.textContent = fmt(target);
    el._lastNum = target;
    return;
  }
  // Cancel any previous in-flight tween on this element
  if (el._tweenRaf) cancelAnimationFrame(el._tweenRaf);
  const from = (typeof el._lastNum === "number") ? el._lastNum : 0;
  if (Math.abs(target - from) < 0.005) {
    el.textContent = fmt(target);
    el._lastNum = target;
    return;
  }
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / _animBudget);
    // ease-out cubic
    const eased = 1 - Math.pow(1 - t, 3);
    const v = from + (target - from) * eased;
    el.textContent = fmt(v);
    if (t < 1) {
      el._tweenRaf = requestAnimationFrame(step);
    } else {
      el._lastNum = target;
      el._tweenRaf = null;
    }
  }
  el._tweenRaf = requestAnimationFrame(step);
}
// Convenience: animate USD with the existing formatter
const animateUsd = (id, n) => animateNumber(id, n, fmtUsd);
const animatePct = (id, n, d=1) => animateNumber(id, n, (v) => fmtPct(v, d));

// ---- Polling -------------------------------------------------------------
async function poll() {
  try {
    const r = await fetch(af("/api/data"));
    if (r.ok) {
      state.data = await r.json();
      renderAll();
    }
  } catch (e) { console.error("poll failed", e); }
}
async function pollCandles() {
  try {
    const r = await fetch(af("/api/candles"));
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
    const r = await fetch(af("/api/trades"));
    if (r.ok) state.trades = await r.json();
    renderTradesTable();
    renderPerformanceGraphs();
    updateChartMarkers();
  } catch (e) {}
}
setInterval(poll, POLL_MS);
setInterval(pollCandles, 30_000);
setInterval(pollTrades, 15_000);
setInterval(pollPriceOnly, 1000);   // 1Hz price refresh -- decouples the
                                    // top-bar NQ tick from the heavier
                                    // 5s /api/data snapshot poll. Server
                                    // returns cached in-memory price so
                                    // there's zero external-API cost.
poll(); pollCandles(); pollTrades();

// Lightweight price-only poll. Hits /api/price (microseconds server-side
// since the value's in-memory) and updates kpi-price + the live current
// price the chart marker tooltips read from. Limited by the bot's own 3s
// PriceMonitor cadence -- true tick-by-tick would need Polygon Premium +
// a WebSocket subscriber, not just faster polling.
async function pollPriceOnly() {
  try {
    const r = await fetch(af("/api/price"));
    if (!r.ok) return;
    const j = await r.json();
    const px = j.price;
    if (px == null) return;
    const el = document.getElementById("kpi-price");
    if (el) el.textContent = (+px).toFixed(2);
    // Keep state.data.price in sync so the active-trade unrealised P&L
    // tooltip and any other readers stay live too.
    if (state.data) state.data.price = +px;
    // Update the live (in-progress) candle so the chart's last bar's
    // close/high/low tick with each price refresh, instead of snapping
    // only when a new 1-min bar arrives. Lightweight-charts' update()
    // replaces the bar with matching time in-place; we extend the
    // running high/low + set close = current price.
    if (candleSeries && state.candles && state.candles.length) {
      const last = state.candles[state.candles.length - 1];
      const newClose = +px;
      const newHigh = Math.max(last.high, newClose);
      const newLow  = Math.min(last.low,  newClose);
      try {
        candleSeries.update({
          time:  last.time,
          open:  last.open,
          high:  newHigh,
          low:   newLow,
          close: newClose,
        });
        // Persist in cache so the next /api/candles refresh doesn't
        // overwrite a partial bar with a stale one.
        last.high = newHigh; last.low = newLow; last.close = newClose;
      } catch (e) { /* chart not ready yet */ }
    }
  } catch (e) { /* network blip — next tick will retry */ }
}

// ---- TOPBAR + LIVE ------------------------------------------------------
function renderTopbar(d) {
  // NQ price: animate smoothly between ticks
  if (typeof d.price === "number") {
    animateNumber("kpi-price", d.price, (n) => n.toFixed(2));
  } else {
    setText("kpi-price", "—");
  }
  const acc = d.lucid_account || {};
  const bal = acc.balance ?? 50000;
  animateNumber("kpi-balance", bal, fmtUsdPlain);
  // Today's P&L and trade count -- computed from the FULL trades cache
  // using BROWSER LOCAL date (not server NY date). User is in AEST, so
  // their "today" is the AEST calendar day. NY-date filter was missing
  // the trades from before NY midnight (= 2pm AEST) and showing 68 when
  // 183 was the right number.
  const allT = _allTradesCache.trades || [];
  const todayStr = new Date().toDateString();
  const todayTrades = allT.filter(t => new Date(t.ts).toDateString() === todayStr);
  const today = todayTrades.reduce((s, t) => s + (t.pnl_usd || 0), 0);
  const todayEl = document.getElementById("kpi-today");
  if (todayEl) {
    todayEl.className = "kpi-value " + (today > 0 ? "pos" : today < 0 ? "neg" : "");
  }
  animateNumber("kpi-today", today, fmtUsd);
  animateNumber("kpi-trades-today", todayTrades.length, (n) => String(Math.round(n)));
  // Background-refresh the cache so kpi numbers stay live even if the
  // user never opens the Performance tab.
  if (Date.now() - _allTradesCache.ts > 30_000) {
    _allTradesCache.ts = Date.now();
    fetch(af("/api/all_trades")).then(r => r.json()).then(trades => {
      if (Array.isArray(trades)) _allTradesCache.trades = trades;
    }).catch(() => {});
  }
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
  // pending_setups is an ARRAY of setup dicts. Previously this just dumped
  // [object Object] because setText() coerces with toString(). Fix: show
  // the count, and render details for each setup in #live-pending-list.
  const pending = Array.isArray(fib.pending_setups) ? fib.pending_setups : [];
  setText("live-pending-n", pending.length);
  const listEl = document.getElementById("live-pending-list");
  if (listEl) {
    if (!pending.length) {
      listEl.innerHTML = "";
    } else {
      listEl.innerHTML = pending.map(s => {
        const side = s.side || "?";
        const entry = (s.level50 ?? s.pullback_entry ?? 0).toFixed(2);
        const stop  = (s.stop_px ?? 0).toFixed(2);
        const tgt   = (s.target_px ?? 0).toFixed(2);
        const cls   = side === "LONG" ? "side-long" : "side-short";
        const block = s.last_block_reason ? ` <span class="muted">· ${s.last_block_reason}</span>` : "";
        const armed = s.entry_armed ? ' <span class="pos">· armed</span>' : "";
        return `<div class="pending-row"><span class="${cls}">${side}</span>
          <span class="muted">entry</span> ${entry}
          <span class="muted">stop</span> ${stop}
          <span class="muted">tgt</span> ${tgt}${armed}${block}</div>`;
      }).join("");
    }
  }

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

  // Activity card -- lifetime stats from the trade DB, NOT filtered by
  // today's date and NOT capped by the 30-deep recent_trades deque. The
  // back-end aggregates every closed trade ever in one SQL pass and ships
  // the result as d.lifetime_stats.
  setText("today-fired", d.signals_fired ?? 0);
  const life = d.lifetime_stats || {};
  setText("today-closed", life.n_trades ?? 0);
  setText("today-pnl", fmtUsd(life.total_pnl ?? 0));
  if ((life.n_trades ?? 0) > 0) {
    setText("today-wr", (life.win_rate ?? 0).toFixed(1) + "%");
    setText("today-hold", fmtHold(life.avg_hold_s ?? 0));
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
  // Async: poll /api/diag for server-side process-alive verdict
  fetchDiag();

  // Sim baseline drift monitor — annualise from all completed trades
  renderDriftMonitor(d);

  // Shadow engine summary (Downloads tab)
  renderShadowSummary(d);
}

// Server-side process-alive check. Independent of d.ts because the bot
// process can die while Flask + CNBC poller keep serving stale prices.
let _diagLast = 0;
function fetchDiag() {
  if (Date.now() - _diagLast < 15000) return;  // throttle to 15s
  _diagLast = Date.now();
  fetch(af("/api/diag")).then(r => r.json()).then(diag => {
    const v = document.getElementById("health-verdict");
    if (!v) return;
    v.textContent = diag.verdict || "—";
    v.className = diag.verdict && diag.verdict.startsWith("bot is alive") ? "pos" :
                  diag.verdict && diag.verdict.includes("starting up") ? "" : "neg";
    const fa = diag.files?.["dashboard_data.json"]?.age_s;
    if (fa !== undefined) {
      const el = document.getElementById("health-file-age");
      if (el) {
        el.textContent = fa < 60 ? `${fa.toFixed(0)}s` :
                         fa < 3600 ? `${(fa/60).toFixed(1)}min` :
                                     `${(fa/3600).toFixed(1)}h`;
        el.className = fa < 120 ? "pos" : fa < 600 ? "" : "neg";
      }
    }
    const ls = diag.lucid?.applied_reset_serial;
    const el2 = document.getElementById("health-reset-serial");
    if (el2) el2.textContent = ls !== undefined ? `${ls}` : "—";
  }).catch(() => {});
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
  // Layer Lucid's window over CME's: if Lucid says closed but CME is open,
  // surface the more restrictive rule. d.fib.lucid_window_blocked is the
  // authoritative server-side check (uses pytz-correct DST).
  const lucidBlocked = (d.fib || {}).lucid_window_blocked === true;
  if (lucidBlocked) {
    mktEl.textContent = "LUCID WINDOW CLOSED (4:45-6pm ET / weekend)";
    mktEl.className = "neg";
  } else {
    mktEl.textContent = mkt.label;
    mktEl.className = mkt.open ? "pos" : "muted";
  }

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

// Sim baseline (window=4, target=18pt, 2 MNQ, $0.74 RT, 0.25pt adv slip).
// Validated on 3-month NQ tick data + OOS split-half + 1000-run Monte Carlo.
// Updated 2026-05-26 after strategy_bakeoff_tick.py showed target=18 beats
// target=12 on BOTH OOS halves with similar DD.
const SIM_BASELINE = {
  ret_mo: 27.04, dd_pct: 1.75, dd_usd: 875,
  wr: 37.3, rr: 2.19, trades_per_mo: 2767,
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
    // Guard against bad/NaN/missing timestamps -- if a trade's ts is
    // unparseable, Lightweight Charts treats the marker time as "newer
    // than every bar" and dumps it on the rightmost candle. Better to
    // silently drop the marker than to corrupt the chart.
    if (!Number.isFinite(exitT) || exitT < cutoff) return;
    // Prefer armed_at_ts (the bar that first touched level50) so the
    // entry arrow lands on the candle that triggered the entry, not the
    // tick-later candle where the bot processed the fill. Fall back to
    // entry_ts for older records that don't have it yet.
    const entryT = new Date(t.armed_at_ts || t.entry_ts || t.ts).getTime();
    if (!Number.isFinite(entryT)) return;
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

// All-trade history cache for the Performance tab. We fetch the full DB
// once per visit instead of reading the truncated recent_trades deque
// (which capped equity curve / monthly P&L / hold histogram / win-loss
// distribution at 30 trades). Refreshed on every renderPerformanceGraphs
// call, but only if last fetch was >30s ago.
let _allTradesCache = { trades: null, ts: 0 };
// Period selector state. Default "today" so the Performance panels match
// the top-bar "Trades Today" counter (user feedback: jarring when Win/Loss
// shows 183 while Trades Today says 68).
let _perfPeriod = "today";
function _filterByPeriod(trades, period) {
  if (period === "all" || !trades || !trades.length) return trades || [];
  if (period === "today") {
    // Browser local date -- matches the top-bar kpi-trades-today counter.
    const todayStr = new Date().toDateString();
    return trades.filter(t => new Date(t.ts).toDateString() === todayStr);
  }
  const lastT = new Date(trades[trades.length - 1].ts).getTime();
  if (period === "week")  return trades.filter(t => new Date(t.ts).getTime() >= lastT - 7*86400000);
  if (period === "month") return trades.filter(t => new Date(t.ts).getTime() >= lastT - 30*86400000);
  return trades;
}
function _renderPerfPanels(allTrades) {
  _renderLifetimeSummary(allTrades);
  const filtered = _filterByPeriod(allTrades, _perfPeriod);
  drawEquityCurve(filtered);
  drawMonthlyPnl(filtered);
  drawHoldHistogram(filtered);
  drawWinLossHistogram(filtered);
}

function _renderLifetimeSummary(trades) {
  // ALWAYS lifetime (since strategy deploy) -- ignores the period selector
  // by design; this is the "career totals" row.
  const el = (id) => document.getElementById(id);
  const pnlEl = el("lifetime-pnl"); if (!pnlEl) return;
  const stats = (state.data && state.data.lifetime_stats) || {};
  const dailyDd = stats.max_daily_dd ?? 0;
  const todayDd = stats.today_dd ?? 0;
  if (!trades || !trades.length) {
    pnlEl.textContent = "$0"; pnlEl.className = "lifetime-value";
    el("lifetime-trades").textContent = "0";
    el("lifetime-wr").textContent = "—";
    el("lifetime-dd").textContent = "—";
    if (el("lifetime-daily-dd")) el("lifetime-daily-dd").textContent = "—";
    if (el("lifetime-today-dd")) el("lifetime-today-dd").textContent = "—";
    return;
  }
  const pnls = trades.map(t => t.pnl_usd || 0);
  const total = pnls.reduce((s, p) => s + p, 0);
  const wins = pnls.filter(p => p > 0).length;
  // Lifetime drawdown computed from the trade equity curve
  let cum = 0, peak = 0, maxDd = 0;
  for (const p of pnls) { cum += p; if (cum > peak) peak = cum; if (peak - cum > maxDd) maxDd = peak - cum; }
  pnlEl.className = "lifetime-value " + (total > 0 ? "pos" : total < 0 ? "neg" : "");
  animateNumber("lifetime-pnl", total, fmtUsd);
  animateNumber("lifetime-trades", trades.length, (n) => Math.round(n).toLocaleString());
  animateNumber("lifetime-wr", wins / trades.length * 100, (n) => n.toFixed(1) + "%");
  animateNumber("lifetime-dd", maxDd, (n) => "-$" + Math.round(n).toLocaleString());
  // Daily DD stats come from the server (NY-date bucketed). Both refer
  // to intra-day peak-to-trough P&L, which is what Lucid effectively
  // monitors via the Daily Loss Limit.
  const ddEl = el("lifetime-daily-dd");
  if (ddEl) {
    ddEl.className = "lifetime-value " + (dailyDd > 0 ? "neg" : "");
    animateNumber("lifetime-daily-dd", dailyDd,
                   (n) => n > 0 ? ("-$" + Math.round(n).toLocaleString()) : "$0");
  }
  const tdEl = el("lifetime-today-dd");
  if (tdEl) {
    tdEl.textContent = todayDd > 0 ? "-$" + todayDd.toFixed(0) : "$0";
    tdEl.className = "lifetime-value " + (todayDd > 200 ? "neg" : "");
  }
}
function renderPerformanceGraphs() {
  // Wire up period buttons once
  document.querySelectorAll(".btn-period").forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      _perfPeriod = btn.dataset.period;
      document.querySelectorAll(".btn-period").forEach(b =>
        b.classList.toggle("active", b === btn));
      if (_allTradesCache.trades) _renderPerfPanels(_allTradesCache.trades);
    });
  });
  // Draw immediately with whatever's cached so the tab isn't blank on open
  const cached = _allTradesCache.trades
                 || (state.data && state.data.recent_trades) || [];
  _renderPerfPanels(cached);
  // Background refresh
  if (Date.now() - _allTradesCache.ts < 30_000) return;
  _allTradesCache.ts = Date.now();
  fetch(af("/api/all_trades")).then(r => r.json()).then(trades => {
    if (!Array.isArray(trades)) return;
    _allTradesCache.trades = trades;
    _renderPerfPanels(trades);
  }).catch(() => {});
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

// Chart entrance animation tracker -- only animate on first render or when
// the tab is re-entered, NOT on every 5s poll refresh.
const _chartAnimDone = new Set();
let _chartRafs = {};  // {canvasId: rafHandle}  -- cancel mid-flight

function _shouldAnimate(canvasId) {
  if (_chartAnimDone.has(canvasId)) return false;
  if (window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    _chartAnimDone.add(canvasId);
    return false;
  }
  return true;
}

// Animate any draw function. drawFn(ctx, w, h, progress) where progress is
// 0..1, eased. Cancels any in-flight animation on the same canvas.
function _animateChart(canvasId, drawFn, opts = {}) {
  const r = _setupCanvas(canvasId);
  if (!r) return;
  const { ctx, w, h } = r;
  if (!_shouldAnimate(canvasId)) {
    drawFn(ctx, w, h, 1);
    return;
  }
  if (_chartRafs[canvasId]) cancelAnimationFrame(_chartRafs[canvasId]);
  const duration = opts.duration || 850;
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);  // ease-out cubic
    ctx.clearRect(0, 0, w, h);
    drawFn(ctx, w, h, eased);
    if (t < 1) {
      _chartRafs[canvasId] = requestAnimationFrame(step);
    } else {
      _chartAnimDone.add(canvasId);
      _chartRafs[canvasId] = null;
    }
  }
  _chartRafs[canvasId] = requestAnimationFrame(step);
}

// Force-replay all chart entrance animations next time Performance tab opens
function _resetChartAnimations() {
  _chartAnimDone.clear();
  for (const id in _chartRafs) {
    if (_chartRafs[id]) cancelAnimationFrame(_chartRafs[id]);
  }
  _chartRafs = {};
}

function drawEquityCurve(trades) {
  const start = 50000;
  _hitRegions["chart-equity"] = [];
  if (!trades.length) {
    const r = _setupCanvas("chart-equity"); if (!r) return;
    const { ctx, w, h } = r;
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const sorted = trades.slice();
  // Build the equity series + a running-peak series for HWM line + drawdown
  let bal = start, peak = start;
  const points = [{ v: start, peak: start, t: null, trade: null }];
  sorted.forEach(t => {
    bal += (t.pnl_usd || 0);
    if (bal > peak) peak = bal;
    points.push({ v: bal, peak, t: t.ts, trade: t });
  });
  const minV = Math.min(...points.map(p => p.v));
  const maxV = Math.max(...points.map(p => p.v));
  const range = Math.max(maxV - minV, 1);
  const padX = 32, padY = 22;

  _animateChart("chart-equity", (ctx, w, h, progress) => {
    const yOf = (v) => h - padY - ((v - minV) / range) * (h - 2 * padY);
    // Background grid: 4 horizontal lines + $50k baseline
    ctx.strokeStyle = "rgba(255,255,255,0.04)"; ctx.lineWidth = 1;
    for (let i = 1; i <= 3; i++) {
      const y = padY + (i / 4) * (h - 2 * padY);
      ctx.beginPath(); ctx.moveTo(padX, y); ctx.lineTo(w - padX, y); ctx.stroke();
    }
    // $50k start dashed reference
    ctx.strokeStyle = "rgba(255,255,255,0.10)"; ctx.lineWidth = 1;
    const y50k = yOf(50000);
    ctx.beginPath(); ctx.setLineDash([3, 4]);
    ctx.moveTo(padX, y50k); ctx.lineTo(w - padX, y50k); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#5d6b85"; ctx.font = "10px sans-serif"; ctx.textAlign = "left";
    ctx.fillText("$50k start", padX + 4, y50k - 4);

    const xy = points.map((p, i) => ({
      p,
      x: padX + (i / Math.max(points.length - 1, 1)) * (w - 2 * padX),
      y: yOf(p.v),
      peakY: yOf(p.peak),
    }));
    const visibleCount = Math.max(2, Math.ceil(xy.length * progress));
    const visible = xy.slice(0, visibleCount);
    const lastX = visible[visible.length - 1].x;

    // ─── 1. DRAWDOWN VALLEY SHADING ─────────────────────────────────
    // Red translucent area between current equity (below) and the HWM
    // (above), showing the "underwater" portion of every drawdown.
    const ddGradient = ctx.createLinearGradient(0, 0, 0, h);
    ddGradient.addColorStop(0, "rgba(248, 113, 113, 0.28)");
    ddGradient.addColorStop(1, "rgba(248, 113, 113, 0.04)");
    ctx.beginPath();
    visible.forEach(({x, peakY}, i) => { if (i === 0) ctx.moveTo(x, peakY); else ctx.lineTo(x, peakY); });
    for (let i = visible.length - 1; i >= 0; i--) ctx.lineTo(visible[i].x, visible[i].y);
    ctx.closePath();
    ctx.fillStyle = ddGradient; ctx.fill();

    // ─── 2. EQUITY AREA (green gradient under the line) ────────────
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, "rgba(34,211,154,0.55)");
    gradient.addColorStop(0.5, "rgba(34,211,154,0.18)");
    gradient.addColorStop(1, "rgba(34,211,154,0.0)");
    ctx.beginPath();
    visible.forEach(({x, y}, i) => { if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.lineTo(lastX, h - padY); ctx.lineTo(padX, h - padY); ctx.closePath();
    ctx.fillStyle = gradient; ctx.fill();

    // ─── 3. HIGH-WATER-MARK DASHED LINE ────────────────────────────
    // Step-line tracing each peak.
    ctx.beginPath();
    visible.forEach(({x, peakY}, i) => { if (i === 0) ctx.moveTo(x, peakY); else ctx.lineTo(x, peakY); });
    ctx.strokeStyle = "rgba(251, 191, 36, 0.55)";   // amber
    ctx.lineWidth = 1.3;
    ctx.setLineDash([4, 4]);
    ctx.shadowColor = "rgba(251, 191, 36, 0.5)"; ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.shadowBlur = 0; ctx.setLineDash([]);

    // ─── 4. MAIN EQUITY LINE (double-pass glow) ────────────────────
    ctx.beginPath();
    visible.forEach(({x, y}, i) => { if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.strokeStyle = "rgba(34, 211, 154, 0.35)";
    ctx.lineWidth = 6;
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 14;
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = "#3df0c2"; ctx.lineWidth = 2;
    ctx.stroke();

    // ─── 5. TRADE MARKERS (small dots, only when many bars-per-pixel
    //                       allows -- skip in dense charts to avoid clutter)
    const pxBetweenTrades = visible.length > 1
      ? (visible[1].x - visible[0].x) : 99;
    if (pxBetweenTrades >= 4) {
      visible.forEach(({p, x, y}, i) => {
        if (i === 0 || !p.trade) return;
        const win = (p.trade.pnl_usd || 0) > 0;
        const r = 2.4;
        ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fillStyle = win ? "#3df0c2" : "#ff6b85";
        ctx.shadowColor = win ? "#22d39a" : "#ff5470";
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.shadowBlur = 0;
      });
    }

    // ─── 6. LEADING EDGE PULSE during animation ─────────────────────
    if (progress < 1) {
      const head = visible[visible.length - 1];
      // Outer halo ring
      ctx.beginPath();
      ctx.arc(head.x, head.y, 9, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(61, 240, 194, 0.18)";
      ctx.fill();
      // Inner bright dot
      ctx.beginPath();
      ctx.arc(head.x, head.y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = "#3df0c2";
      ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 16;
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    // ─── 7. ANNOTATIONS (only after animation complete) ─────────────
    if (progress >= 1) {
      // Find deepest drawdown point and label it
      let maxDdIdx = 0, maxDd = 0;
      xy.forEach((pt, i) => {
        const dd = pt.p.peak - pt.p.v;
        if (dd > maxDd) { maxDd = dd; maxDdIdx = i; }
      });
      if (maxDd > 0) {
        const dpt = xy[maxDdIdx];
        ctx.fillStyle = "rgba(248, 113, 113, 0.85)";
        ctx.font = "10px sans-serif"; ctx.textAlign = "center";
        ctx.fillText(`Max DD: ${fmtUsd(-maxDd)}`,
                     dpt.x, Math.min(h - padY - 4, dpt.y + 12));
      }
      // Hit regions
      xy.forEach(({p, x, y}, i) => {
        const pnl = p.v - 50000;
        const pnlClass = pnl >= 0 ? "pos" : "neg";
        const dd = p.peak - p.v;
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
            <div class="tt-row"><span class="tt-label">Peak</span><span class="tt-value">${fmtUsdPlain(p.peak)}</span></div>
            <div class="tt-row"><span class="tt-label">DD from peak</span><span class="tt-value ${dd > 0 ? 'neg' : ''}">${dd > 0 ? fmtUsd(-dd) : '$0'}</span></div>
            ${tradeRow}`,
        });
      });
      _attachTooltip("chart-equity", "tt-equity");
    }
  });
}

function drawMonthlyPnl(trades) {
  _hitRegions["chart-monthly"] = [];
  if (!trades.length) {
    const r = _setupCanvas("chart-monthly"); if (!r) return;
    const { ctx, w, h } = r;
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  // Bucket by month; split out wins vs losses TOTALS so we can show
  // composition (not just net P&L).
  const months = {};
  trades.forEach(t => {
    const d = new Date(t.ts);
    const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
    if (!months[key]) months[key] = {
      winsTotal: 0, lossesTotal: 0, n: 0, nWins: 0, nLosses: 0,
    };
    const p = t.pnl_usd || 0;
    months[key].n++;
    if (p > 0) { months[key].winsTotal  += p; months[key].nWins++; }
    if (p < 0) { months[key].lossesTotal += p; months[key].nLosses++; }
  });
  const keys = Object.keys(months).sort();
  // Y-axis scale is the LARGER of (max win column, max loss column) so the
  // top half and bottom half are proportional.
  const maxStack = Math.max(
    1,
    ...keys.map(k => Math.max(months[k].winsTotal, -months[k].lossesTotal))
  );

  _animateChart("chart-monthly", (ctx, w, h, progress) => {
    const padX = 36, padY = 22;
    const yZero = h / 2;
    const bw = (w - 2 * padX) / Math.max(keys.length, 1);
    const halfH = h / 2 - padY;

    // Background quartile grid (faint horizontal stripes)
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    [0.25, 0.5, 0.75, 1.0].forEach(frac => {
      const yUp = yZero - frac * halfH;
      const yDn = yZero + frac * halfH;
      ctx.beginPath(); ctx.moveTo(padX, yUp); ctx.lineTo(w - padX, yUp); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(padX, yDn); ctx.lineTo(w - padX, yDn); ctx.stroke();
    });

    // Zero line (brighter)
    ctx.strokeStyle = "rgba(255,255,255,0.18)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padX, yZero); ctx.lineTo(w - padX, yZero); ctx.stroke();

    // Bars: wins ABOVE zero (green) + losses BELOW zero (red), so each
    // month visibly shows the composition that produced its net.
    keys.forEach((k, i) => {
      const m = months[k];
      const x = padX + i * bw + 3;
      const innerW = Math.max(8, bw - 8);
      const lag = i / Math.max(keys.length, 1) * 0.35;
      const localT = Math.max(0, Math.min(1, (progress - lag) / (1 - lag || 1)));
      const eased = 1 - Math.pow(1 - localT, 3);

      // Wins (green, growing UP from zero)
      const winH = (m.winsTotal / maxStack) * halfH * eased;
      if (winH > 0.4) {
        const grad = ctx.createLinearGradient(0, yZero - winH, 0, yZero);
        grad.addColorStop(0, "rgba(61, 240, 194, 0.95)");
        grad.addColorStop(1, "rgba(34, 211, 154, 0.55)");
        ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 14;
        ctx.fillStyle = grad;
        _roundedBar(ctx, x, yZero - winH, innerW, winH, 3, "top");
        ctx.shadowBlur = 0;
        // Bright top highlight
        ctx.fillStyle = "rgba(255,255,255,0.55)";
        ctx.fillRect(x + 1, yZero - winH, innerW - 2, 1);
      }
      // Losses (red, growing DOWN from zero)
      const lossH = (-m.lossesTotal / maxStack) * halfH * eased;
      if (lossH > 0.4) {
        const grad = ctx.createLinearGradient(0, yZero, 0, yZero + lossH);
        grad.addColorStop(0, "rgba(255, 84, 112, 0.95)");
        grad.addColorStop(1, "rgba(248, 113, 113, 0.45)");
        ctx.shadowColor = "#ff5470"; ctx.shadowBlur = 14;
        ctx.fillStyle = grad;
        _roundedBar(ctx, x, yZero, innerW, lossH, 3, "bottom");
        ctx.shadowBlur = 0;
        // Bright bottom highlight
        ctx.fillStyle = "rgba(255,255,255,0.45)";
        ctx.fillRect(x + 1, yZero + lossH - 1, innerW - 2, 1);
      }
      // Net P&L label above the taller side (only after settling)
      if (eased > 0.85) {
        ctx.globalAlpha = (eased - 0.85) / 0.15;
        const net = m.winsTotal + m.lossesTotal;
        const netCol = net >= 0 ? "#3df0c2" : "#ff7691";
        ctx.fillStyle = netCol; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
        ctx.shadowColor = netCol; ctx.shadowBlur = 8;
        const labelY = Math.min(yZero - winH - 6, yZero - 4);
        ctx.fillText(fmtUsd(net), x + innerW / 2, labelY);
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 1;
      }
      if (progress >= 1) {
        const winRate = m.n ? m.nWins / m.n : 0;
        const net = m.winsTotal + m.lossesTotal;
        _hitRegions["chart-monthly"].push({
          x0: x, x1: x + innerW,
          y0: yZero - halfH, y1: yZero + halfH,
          html: `
            <div class="tt-row"><span class="tt-label">Month</span><span class="tt-value">${k}</span></div>
            <div class="tt-row"><span class="tt-label">Wins total</span><span class="tt-value pos">${fmtUsd(m.winsTotal)}</span></div>
            <div class="tt-row"><span class="tt-label">Losses total</span><span class="tt-value neg">${fmtUsd(m.lossesTotal)}</span></div>
            <div class="tt-row"><span class="tt-label">Net P&L</span><span class="tt-value ${net >= 0 ? 'pos' : 'neg'}">${fmtUsd(net)}</span></div>
            <div class="tt-row"><span class="tt-label">Trades</span><span class="tt-value">${m.n}</span></div>
            <div class="tt-row"><span class="tt-label">Win rate</span><span class="tt-value">${fmtPct(winRate)}</span></div>`,
        });
      }
    });
    // x-axis labels (only fully visible at end)
    if (progress > 0.9) {
      ctx.globalAlpha = (progress - 0.9) / 0.1;
      ctx.fillStyle = "#5d6b85"; ctx.font = "10px sans-serif"; ctx.textAlign = "center";
      const step = keys.length > 12 ? Math.ceil(keys.length / 12) : 1;
      keys.forEach((k, i) => {
        if (i % step === 0) ctx.fillText(k.slice(2), padX + i * bw + bw / 2, h - 4);
      });
      ctx.globalAlpha = 1;
    }
    if (progress >= 1) _attachTooltip("chart-monthly", "tt-monthly");
  });
}

// Rounded-corner bar: rounds the SIDE indicated ("top"/"bottom"/"left"/"right"/"all")
function _roundedBar(ctx, x, y, w, h, r, which) {
  if (w < 1 || h < 1) return;
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  if (which === "top") {
    ctx.moveTo(x, y + h);
    ctx.lineTo(x, y + rr);
    ctx.arcTo(x, y, x + rr, y, rr);
    ctx.lineTo(x + w - rr, y);
    ctx.arcTo(x + w, y, x + w, y + rr, rr);
    ctx.lineTo(x + w, y + h);
  } else if (which === "bottom") {
    ctx.moveTo(x, y);
    ctx.lineTo(x + w, y);
    ctx.lineTo(x + w, y + h - rr);
    ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
    ctx.lineTo(x + rr, y + h);
    ctx.arcTo(x, y + h, x, y + h - rr, rr);
  } else if (which === "left") {
    ctx.moveTo(x + w, y);
    ctx.lineTo(x + rr, y);
    ctx.arcTo(x, y, x, y + rr, rr);
    ctx.lineTo(x, y + h - rr);
    ctx.arcTo(x, y + h, x + rr, y + h, rr);
    ctx.lineTo(x + w, y + h);
  } else if (which === "right") {
    ctx.moveTo(x, y);
    ctx.lineTo(x + w - rr, y);
    ctx.arcTo(x + w, y, x + w, y + rr, rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
    ctx.lineTo(x, y + h);
  } else {
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + rr, rr);
    ctx.arcTo(x + w, y + h, x + w - rr, y + h, rr);
    ctx.arcTo(x, y + h, x, y + h - rr, rr);
    ctx.arcTo(x, y, x + rr, y, rr);
  }
  ctx.closePath();
  ctx.fill();
}

function drawHoldHistogram(trades) {
  _hitRegions["chart-holds"] = [];
  if (!trades.length) {
    const r = _setupCanvas("chart-holds"); if (!r) return;
    const { ctx, w, h } = r;
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

  _animateChart("chart-holds", (ctx, w, h, progress) => {
    const padX = 30, padTop = 28, padBot = 28;
    const bw = (w - 2 * padX) / buckets.length;
    const chartH = h - padTop - padBot;

    // Faint horizontal grid (quartile lines)
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    for (let i = 1; i <= 3; i++) {
      const y = padTop + (i / 4) * chartH;
      ctx.beginPath(); ctx.moveTo(padX, y); ctx.lineTo(w - padX, y); ctx.stroke();
    }

    buckets.forEach((b, i) => {
      const x = padX + i * bw + 4;
      const innerW = Math.max(8, bw - 10);
      const lag = i / buckets.length * 0.45;
      const localT = Math.max(0, Math.min(1, (progress - lag) / (1 - lag || 1)));
      const eased = 1 - Math.pow(1 - localT, 3);
      const fullBh = (b.c / maxC) * chartH;
      const bh = fullBh * eased;
      const yTop = h - padBot - bh;
      const isMicro = b.label === "≤10s";

      if (bh < 0.5) {
        // Empty bucket: just a faint baseline marker
        ctx.fillStyle = "rgba(255,255,255,0.04)";
        ctx.fillRect(x, h - padBot - 1, innerW, 1);
      } else {
        // ─── COMPOSITION SPLIT ───────────────────────────────────────
        // Stack win segment (green, on top) above loss segment (red).
        const total = b.c;
        const winFrac = b.wins / total;
        const lossFrac = b.losses / total;
        const winH = bh * winFrac;
        const lossH = bh * lossFrac;
        const neutralH = bh - winH - lossH;   // timeouts that broke even

        // Loss segment at the bottom of the bar
        if (lossH > 0.4) {
          const lg = ctx.createLinearGradient(0, h - padBot - lossH, 0, h - padBot);
          lg.addColorStop(0, "rgba(255, 84, 112, 0.90)");
          lg.addColorStop(1, "rgba(248, 113, 113, 0.55)");
          ctx.shadowColor = "#ff5470"; ctx.shadowBlur = 10;
          ctx.fillStyle = lg;
          _roundedBar(ctx, x, h - padBot - lossH, innerW, lossH, 3, "bottom");
          ctx.shadowBlur = 0;
        }
        // Win segment on top
        if (winH > 0.4) {
          const wg = ctx.createLinearGradient(0, yTop, 0, yTop + winH);
          wg.addColorStop(0, "rgba(61, 240, 194, 0.95)");
          wg.addColorStop(1, "rgba(34, 211, 154, 0.55)");
          ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 12;
          ctx.fillStyle = wg;
          _roundedBar(ctx, x, yTop, innerW, winH, 3, "top");
          ctx.shadowBlur = 0;
          // Bright top highlight
          ctx.fillStyle = "rgba(255,255,255,0.55)";
          ctx.fillRect(x + 1, yTop, innerW - 2, 1);
        }
        // Hairline split between win and loss segments
        if (winH > 0 && lossH > 0) {
          ctx.fillStyle = "rgba(255,255,255,0.20)";
          ctx.fillRect(x, h - padBot - lossH, innerW, 1);
        }
        // Microscalp warning border (orange) on ≤10s bucket
        if (isMicro) {
          ctx.strokeStyle = "rgba(251, 191, 36, 0.5)";
          ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
          ctx.strokeRect(x - 1, yTop - 1, innerW + 2, bh + 2);
          ctx.setLineDash([]);
        }
      }

      // Labels + count (only at near-complete)
      if (eased > 0.8) {
        ctx.globalAlpha = (eased - 0.8) / 0.2;
        if (b.c > 0) {
          ctx.fillStyle = "#e6ecf5"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
          ctx.fillText(b.c, x + innerW / 2, yTop - 6);
        }
        ctx.fillStyle = isMicro ? "rgba(251, 191, 36, 0.85)" : "#5d6b85";
        ctx.font = "10px sans-serif";
        ctx.fillText(b.label, x + innerW / 2, h - 8);
        ctx.globalAlpha = 1;
      }
      if (progress >= 1) {
        _hitRegions["chart-holds"].push({
          x0: x, x1: x + innerW,
          y0: yTop - 14, y1: h - padBot,
          html: `
            <div class="tt-row"><span class="tt-label">Bucket</span><span class="tt-value">${b.label}</span></div>
            <div class="tt-row"><span class="tt-label">Trades</span><span class="tt-value">${b.c}</span></div>
            <div class="tt-row"><span class="tt-label">Wins</span><span class="tt-value pos">${b.wins}</span></div>
            <div class="tt-row"><span class="tt-label">Losses</span><span class="tt-value neg">${b.losses}</span></div>
            <div class="tt-row"><span class="tt-label">Win rate</span><span class="tt-value">${b.c ? (b.wins/b.c*100).toFixed(0) : 0}%</span></div>
            <div class="tt-row"><span class="tt-label">Net P&L</span><span class="tt-value ${b.pnl >= 0 ? 'pos' : 'neg'}">${fmtUsd(b.pnl)}</span></div>
            ${isMicro ? '<div class="tt-row"><span class="tt-label">Lucid</span><span class="tt-value neg">microscalp range</span></div>' : ''}`,
        });
      }
    });
    if (progress >= 1) _attachTooltip("chart-holds", "tt-holds");
  });
}

function drawWinLossHistogram(trades) {
  _hitRegions["chart-wlhist"] = [];
  if (!trades.length) {
    const r = _setupCanvas("chart-wlhist"); if (!r) return;
    const { ctx, w, h } = r;
    ctx.fillStyle = "#5d6b85"; ctx.font = "13px sans-serif"; ctx.textAlign = "center";
    ctx.fillText("No trades yet", w / 2, h / 2);
    return;
  }
  const wins = trades.filter(t => (t.pnl_usd || 0) > 0);
  const losses = trades.filter(t => (t.pnl_usd || 0) < 0);
  const winTotal = wins.reduce((s, t) => s + t.pnl_usd, 0);
  const lossTotal = Math.abs(losses.reduce((s, t) => s + t.pnl_usd, 0));   // positive magnitude
  const net = winTotal - lossTotal;
  const totalMag = Math.max(winTotal + lossTotal, 1);
  const winFrac = winTotal / totalMag;
  const lossFrac = lossTotal / totalMag;
  const profitFactor = lossTotal > 0 ? winTotal / lossTotal : (winTotal > 0 ? Infinity : 0);
  const winRate = trades.length ? wins.length / trades.length : 0;

  _animateChart("chart-wlhist", (ctx, w, h, progress) => {
    const padX = 32;
    const barH = 38;
    const barY = h / 2 - barH / 2 + 6;     // shifted down to leave room for labels
    const barW = w - 2 * padX;
    const innerW = barW;

    // Headline stats (top)
    if (progress > 0.4) {
      ctx.globalAlpha = Math.min(1, (progress - 0.4) / 0.4);
      ctx.font = "bold 13px sans-serif"; ctx.textBaseline = "middle";
      // Win total (left side)
      ctx.fillStyle = "#3df0c2"; ctx.textAlign = "left";
      ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 10;
      ctx.fillText(`+${fmtUsdPlain(winTotal).replace('$','$')}`, padX, barY - 18);
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#9ab"; ctx.font = "10px sans-serif";
      ctx.fillText(`${wins.length} wins`, padX, barY - 4);

      // Loss total (right side)
      ctx.fillStyle = "#ff7691"; ctx.textAlign = "right";
      ctx.font = "bold 13px sans-serif";
      ctx.shadowColor = "#ff5470"; ctx.shadowBlur = 10;
      ctx.fillText(`-${fmtUsdPlain(lossTotal).replace('$','$')}`, w - padX, barY - 18);
      ctx.shadowBlur = 0;
      ctx.fillStyle = "#9ab"; ctx.font = "10px sans-serif";
      ctx.fillText(`${losses.length} losses`, w - padX, barY - 4);
      ctx.globalAlpha = 1;
    }

    // ─── BALANCE BAR ─────────────────────────────────────────────────
    // Rounded outer container
    const containerGrad = ctx.createLinearGradient(0, barY, 0, barY + barH);
    containerGrad.addColorStop(0, "rgba(255,255,255,0.04)");
    containerGrad.addColorStop(1, "rgba(255,255,255,0.01)");
    ctx.fillStyle = containerGrad;
    _roundedBar(ctx, padX, barY, innerW, barH, 10, "all");

    // Win fill (flows in from LEFT)
    const fillProgress = Math.max(0, Math.min(1, (progress - 0.15) / 0.85));
    const easedFill = 1 - Math.pow(1 - fillProgress, 3);
    const winW = winFrac * innerW * easedFill;
    if (winW > 0.5) {
      const winGrad = ctx.createLinearGradient(padX, 0, padX + winW, 0);
      winGrad.addColorStop(0, "rgba(34, 211, 154, 0.95)");
      winGrad.addColorStop(1, "rgba(61, 240, 194, 0.85)");
      ctx.shadowColor = "#22d39a"; ctx.shadowBlur = 18;
      ctx.fillStyle = winGrad;
      _roundedBar(ctx, padX, barY, winW, barH, 10,
                   winW >= innerW - 0.5 ? "all" : "left");
      ctx.shadowBlur = 0;
    }
    // Loss fill (flows in from RIGHT)
    const lossW = lossFrac * innerW * easedFill;
    if (lossW > 0.5) {
      const lossGrad = ctx.createLinearGradient(w - padX - lossW, 0, w - padX, 0);
      lossGrad.addColorStop(0, "rgba(255, 118, 145, 0.85)");
      lossGrad.addColorStop(1, "rgba(255, 84, 112, 0.95)");
      ctx.shadowColor = "#ff5470"; ctx.shadowBlur = 18;
      ctx.fillStyle = lossGrad;
      _roundedBar(ctx, w - padX - lossW, barY, lossW, barH, 10,
                   lossW >= innerW - 0.5 ? "all" : "right");
      ctx.shadowBlur = 0;
    }
    // Highlight strip across the top of the bar (the "shine")
    ctx.fillStyle = "rgba(255,255,255,0.18)";
    ctx.fillRect(padX + 10, barY + 2, innerW - 20, 1);

    // Centre fulcrum / divider — placed at the actual split point
    if (easedFill > 0.7) {
      ctx.globalAlpha = (easedFill - 0.7) / 0.3;
      const splitX = padX + winW;
      ctx.strokeStyle = "rgba(255,255,255,0.55)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(splitX, barY - 4);
      ctx.lineTo(splitX, barY + barH + 4);
      ctx.stroke();
      // Triangle pointer above the split
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.beginPath();
      ctx.moveTo(splitX - 5, barY - 5);
      ctx.lineTo(splitX + 5, barY - 5);
      ctx.lineTo(splitX, barY - 1);
      ctx.closePath(); ctx.fill();
      ctx.globalAlpha = 1;
    }

    // ─── BOTTOM SUMMARY: NET P&L + PROFIT FACTOR + WIN RATE ────────
    if (progress > 0.75) {
      ctx.globalAlpha = (progress - 0.75) / 0.25;
      ctx.font = "10px sans-serif"; ctx.textBaseline = "alphabetic";
      const yBot = barY + barH + 26;

      // Net (centre)
      const netColor = net >= 0 ? "#3df0c2" : "#ff7691";
      ctx.textAlign = "center";
      ctx.fillStyle = "#7a85a3"; ctx.font = "9px sans-serif";
      ctx.fillText("NET", w / 2, yBot - 14);
      ctx.fillStyle = netColor;
      ctx.font = "bold 16px sans-serif";
      ctx.shadowColor = netColor; ctx.shadowBlur = 12;
      ctx.fillText(`${net >= 0 ? '+' : ''}${fmtUsdPlain(Math.abs(net))}`, w / 2, yBot + 6);
      ctx.shadowBlur = 0;

      // Profit Factor (left)
      ctx.textAlign = "left";
      ctx.fillStyle = "#7a85a3"; ctx.font = "9px sans-serif";
      ctx.fillText("PROFIT FACTOR", padX, yBot - 14);
      ctx.fillStyle = profitFactor >= 1 ? "#3df0c2" : "#ff7691";
      ctx.font = "bold 14px sans-serif";
      const pfText = profitFactor === Infinity ? "∞" : profitFactor.toFixed(2);
      ctx.fillText(pfText, padX, yBot + 4);

      // Win Rate (right)
      ctx.textAlign = "right";
      ctx.fillStyle = "#7a85a3"; ctx.font = "9px sans-serif";
      ctx.fillText("WIN RATE", w - padX, yBot - 14);
      ctx.fillStyle = winRate >= 0.5 ? "#3df0c2" : "#c7d0e0";
      ctx.font = "bold 14px sans-serif";
      ctx.fillText(`${(winRate * 100).toFixed(1)}%`, w - padX, yBot + 4);
      ctx.globalAlpha = 1;
    }

    if (progress >= 1) {
      // Hit regions: wins half on left, losses half on right
      const splitX = padX + winFrac * innerW;
      _hitRegions["chart-wlhist"].push({
        x0: padX, x1: splitX, y0: barY - 25, y1: barY + barH + 30,
        html: `
          <div class="tt-row"><span class="tt-label">Category</span><span class="tt-value pos">Wins</span></div>
          <div class="tt-row"><span class="tt-label">Count</span><span class="tt-value">${wins.length}</span></div>
          <div class="tt-row"><span class="tt-label">Total</span><span class="tt-value pos">${fmtUsd(winTotal)}</span></div>
          <div class="tt-row"><span class="tt-label">Average</span><span class="tt-value pos">${fmtUsd(wins.length ? winTotal/wins.length : 0)}</span></div>
          <div class="tt-row"><span class="tt-label">Biggest</span><span class="tt-value pos">${fmtUsd(wins.length ? Math.max(...wins.map(t=>t.pnl_usd)) : 0)}</span></div>`,
      });
      _hitRegions["chart-wlhist"].push({
        x0: splitX, x1: w - padX, y0: barY - 25, y1: barY + barH + 30,
        html: `
          <div class="tt-row"><span class="tt-label">Category</span><span class="tt-value neg">Losses</span></div>
          <div class="tt-row"><span class="tt-label">Count</span><span class="tt-value">${losses.length}</span></div>
          <div class="tt-row"><span class="tt-label">Total</span><span class="tt-value neg">-${fmtUsdPlain(lossTotal)}</span></div>
          <div class="tt-row"><span class="tt-label">Average</span><span class="tt-value neg">${fmtUsd(losses.length ? -lossTotal/losses.length : 0)}</span></div>
          <div class="tt-row"><span class="tt-label">Biggest</span><span class="tt-value neg">${fmtUsd(losses.length ? Math.min(...losses.map(t=>t.pnl_usd)) : 0)}</span></div>`,
      });
      _attachTooltip("chart-wlhist", "tt-wlhist");
    }
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
  updateChartMarkers();
  updateSetupLines();
  updateTradeLineSegments();
}
