/* Dashboard front-end (per spec).
   Polls /api/data every 30s and /api/price every 500ms.
   "Updated Xs ago" is computed from a local Date.now() delta — not from
   the absolute server timestamp — so it ticks correctly on any device. */
(function () {
  const $ = (id) => document.getElementById(id);
  const fmtMoney = (n) => (n == null) ? "—"
    : n.toLocaleString("en-US", { style: "currency", currency: "USD",
                                  minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const fmtNum = (n, d = 2) => (n == null || isNaN(n)) ? "—" : Number(n).toFixed(d);

  let lastDataReceivedAt = 0;
  let lastDataServerTs = null;
  let chart = null, candleSeries = null;

  // ---- chart (lightweight-charts) -----------------------------------
  function ensureChart() {
    if (chart || !window.LightweightCharts) return;
    chart = LightweightCharts.createChart($("chart"), {
      layout: { background: { color: "#131722" }, textColor: "#d8def0" },
      grid: { horzLines: { color: "#232a3b" }, vertLines: { color: "#232a3b" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#232a3b" },
    });
    candleSeries = chart.addCandlestickSeries({
      upColor: "#2ecc71", downColor: "#e74c3c",
      borderUpColor: "#2ecc71", borderDownColor: "#e74c3c",
      wickUpColor: "#2ecc71", wickDownColor: "#e74c3c",
    });
    new ResizeObserver(() => chart.applyOptions({
      width: $("chart").clientWidth, height: 360,
    })).observe($("chart"));
  }

  async function refreshCandles() {
    try {
      const r = await fetch("/api/candles");
      const arr = await r.json();
      if (!candleSeries) return;
      candleSeries.setData(arr);
    } catch (e) { /* ignore */ }
  }

  // ---- main data poll (30s) -----------------------------------------
  async function refreshData() {
    try {
      const r = await fetch("/api/data");
      const d = await r.json();
      lastDataReceivedAt = Date.now();
      lastDataServerTs = d.as_of || null;
      paint(d);
    } catch (e) {
      $("health-dot").className = "dot bad";
    }
  }

  function paint(d) {
    $("health-dot").className = "dot ok";
    $("cycle-label").textContent = d.cycle != null ? `cycle ${d.cycle}` : "cycle —";
    $("kill-zone-label").textContent = d.kill_zone && d.kill_zone.active
      ? `▶ ${d.kill_zone.name}`
      : (d.kill_zone ? `next: ${d.kill_zone.next}` : "—");
    $("price").textContent = fmtNum(d.price, 2);
    $("price-ts").textContent = d.price_ts || "—";

    // Account
    const a = d.account || {};
    $("balance").textContent = fmtMoney(a.balance);
    $("starting").textContent = fmtMoney(a.starting_balance);
    $("pnl").textContent = fmtMoney(a.realized_pnl);
    $("trades-today").textContent = a.trades_today ?? "—";

    // Readiness
    const tr = d.trade_readiness || { pct: 0, passing: [], blocking: [], total_checks: 0 };
    const pct = Math.round((tr.pct || 0) * 100);
    $("readiness-pct").textContent = `${pct}%`;
    $("readiness-fill").style.width = `${pct}%`;
    $("passing").innerHTML = (tr.passing || []).map((p) => `<span class="pass-pill">${p}</span>`).join(", ") || "—";
    $("blocking").innerHTML = (tr.blocking || []).map((p) => `<span class="block-pill">${p}</span>`).join(", ") || "—";
    const card = $("readiness-card");
    card.classList.remove("green", "yellow", "red");
    if (pct >= 90) card.classList.add("green");
    else if (pct >= 60) card.classList.add("yellow");
    else card.classList.add("red");

    // Microstructure
    const ms = d.microstructure || {};
    if (ms.vpin) $("vpin").textContent = `${ms.vpin.regime} (${fmtNum(ms.vpin.value, 3)})${ms.vpin.crash_warning ? " ⚠" : ""}`;
    if (ms.adverse_selection) $("adverse").textContent = `${ms.adverse_selection.regime} (${fmtNum(ms.adverse_selection.score, 3)})`;
    if (ms.regime) $("regime").textContent = `${ms.regime.state} conf ${fmtNum(ms.regime.confidence, 2)}`;
    if (ms.gex) $("gex").textContent = `${ms.gex.regime} $${fmtNum(ms.gex.total_gex_billion, 1)}B`;
    if (ms.macro) $("macro").textContent = `${ms.macro.bias} ${fmtNum(ms.macro.score, 2)}`;

    // (whitelist now lives in the Strategies card, populated by refreshStrategies)

    // Stat arb
    const sa = d.stat_arb || {};
    $("sa-signal").textContent = sa.signal || "—";
    $("sa-z").textContent = fmtNum(sa.zscore, 2);
    $("sa-beta").textContent = fmtNum(sa.beta, 2);
    $("sa-p").textContent = fmtNum(sa.coint_pvalue, 3);

    // Trades
    const rows = (d.recent_trades || []).slice().reverse();
    $("trades-body").innerHTML = rows.map((t) => {
      const pnl = t.pnl ?? 0;
      const cls = pnl > 0 ? "pos" : (pnl < 0 ? "neg" : "");
      return `<tr>
        <td>${(t.entry_time || "").slice(0, 19).replace("T", " ")}</td>
        <td>${t.signal_name || ""}</td>
        <td>${t.side || ""}</td>
        <td>${fmtNum(t.entry_px, 2)}</td>
        <td>${fmtNum(t.exit_px, 2)}</td>
        <td>${t.exit_reason || "—"}</td>
        <td class="${cls}">${pnl ? fmtMoney(pnl) : "—"}</td>
      </tr>`;
    }).join("");

    // ---- Lucid account panel ----
    paintLucid(d.lucid_account || {});
    paintFundedAccounts(d.funded_accounts || {});
  }

  function paintLucid(L) {
    if (!L || !Object.keys(L).length) return;
    $("lucid-account-id").textContent = `account #${L.account_id ?? "—"}`;
    $("lucid-blown-pill").style.display = L.blown ? "inline-block" : "none";
    $("lucid-balance").textContent = fmtMoney(L.balance);
    $("lucid-trail").textContent = fmtMoney(L.trail_floor);
    $("lucid-trail-locked").textContent = L.trail_locked ? "locked at break-even" : "trailing $2K below peak";
    $("lucid-buffer").textContent = fmtMoney(L.buffer_to_trail);
    const tp = L.today_pnl ?? 0;
    const tpEl = $("lucid-today-pnl");
    tpEl.textContent = (tp >= 0 ? "+" : "") + fmtMoney(tp);
    tpEl.className = "big-number " + (tp > 0 ? "pos" : tp < 0 ? "neg" : "");
    $("lucid-dll-remaining").textContent = L.dll_hit ? "DLL HIT — no new entries" : `DLL room ${fmtMoney(L.dll_remaining)}`;
    const cp = L.cum_pnl ?? 0;
    const cpEl = $("lucid-cum-pnl");
    cpEl.textContent = (cp >= 0 ? "+" : "") + fmtMoney(cp);
    cpEl.className = "big-number " + (cp > 0 ? "pos" : cp < 0 ? "neg" : "");
    $("lucid-trading-days").textContent = `${L.n_trading_days ?? 0} trading days`;
    const share = L.today_share_of_total ?? 0;
    const shareEl = $("lucid-consistency");
    shareEl.textContent = `${Math.round(share * 100)}%`;
    shareEl.className = "big-number " + (L.consistency_ok ? "pos" : "neg");
    $("lucid-takehome").textContent = fmtMoney(L.take_home_at_split);
    const peEl = $("lucid-payout");
    peEl.textContent = L.payout_eligible ? "READY" : "—";
    peEl.className = "big-number " + (L.payout_eligible ? "pos" : "");
    $("lucid-payout-reason").textContent = L.payout_reason || "—";
  }

  function paintFundedAccounts(F) {
    if (!F) return;
    $("funded-passed-pill").textContent = `${F.n_passed ?? 0} passed`;
    $("funded-failed-pill").textContent = `${F.n_failed ?? 0} failed`;
    $("funded-active-pill").textContent = `active #${F.active_account_id ?? "—"}`;
    const hist = (F.history || []).slice().reverse();
    $("funded-body").innerHTML = hist.map((h) => {
      const cls = h.outcome === "PASSED" ? "pos" : "neg";
      const pnl = h.cum_pnl ?? 0;
      return `<tr>
        <td>#${h.account_id ?? "—"}</td>
        <td>${(h.started_at || "").slice(0,10)}</td>
        <td>${(h.ended_at || "").slice(0,10)}</td>
        <td class="${cls}">${h.outcome || "—"}</td>
        <td>${h.n_trading_days ?? "—"}</td>
        <td>${h.n_trades ?? "—"}</td>
        <td>${h.wins ?? "—"}</td>
        <td>${h.losses ?? "—"}</td>
        <td class="${pnl >= 0 ? 'pos':'neg'}">${fmtMoney(pnl)}</td>
        <td>${fmtMoney(h.ending_balance)}</td>
        <td class="muted small">${h.blow_reason || "—"}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="11" class="muted">no archived accounts yet — current account is the first run</td></tr>`;
  }

  // ---- Last 100 trades table ----
  async function refreshLast100() {
    try {
      const r = await fetch("/api/last_trades");
      const arr = await r.json();
      $("last100-body").innerHTML = arr.map((t) => {
        const pnl = t.pnl ?? 0;
        const cls = pnl > 0 ? "pos" : (pnl < 0 ? "neg" : "");
        return `<tr>
          <td>${(t.entry_time || "").slice(0, 19).replace("T", " ")}</td>
          <td>${t.signal_name || ""}</td>
          <td>${t.side || ""}</td>
          <td>${t.qty ?? "—"}</td>
          <td>${fmtNum(t.entry_px, 2)}</td>
          <td>${fmtNum(t.stop_px, 2)}</td>
          <td>${fmtNum(t.target_px, 2)}</td>
          <td>${fmtNum(t.exit_px, 2)}</td>
          <td>${t.exit_reason || "—"}</td>
          <td class="${cls}">${pnl ? fmtMoney(pnl) : "—"}</td>
        </tr>`;
      }).join("");
    } catch (e) { /* ignore */ }
  }

  // ---- Live trade chart (Plotly) ----
  async function refreshLiveChart() {
    if (!window.Plotly) return;
    try {
      const r = await fetch("/api/live_chart");
      const fig = await r.json();
      if (fig.error) return;
      Plotly.react("live-chart", fig.data, fig.layout, {
        responsive: true, scrollZoom: true,
        modeBarButtonsToRemove: ["select2d", "lasso2d"],
        displaylogo: false,
      });
    } catch (e) { /* ignore */ }
  }

  // ---- filter mode + ablation findings ------------------------------
  async function refreshFilterConfig() {
    try {
      const r = await fetch("/api/filter_config");
      const d = await r.json();
      const mode = (d.mode || "—").toUpperCase();
      const pill = $("filter-mode-pill");
      pill.textContent = mode;
      pill.className = "pill mode-" + mode.toLowerCase();
      $("filter-summary").textContent = d.summary || "";
      const f = (d.status || {}).filters || {};
      function setRow(id, info) {
        const el = $(id);
        if (!el || !info) return;
        const ok = info.enabled === true || info.as_veto === true;
        el.innerHTML = (ok ? "<span class='pass-pill'>ON</span>" : "<span class='block-pill'>OFF</span>")
          + ` <span class="muted small">${info.ablation || ""}</span>`;
      }
      setRow("f-proximity", f.proximity);
      setRow("f-minrr",     f.min_rr ? { enabled: true, ablation: f.min_rr.ablation } : null);
      setRow("f-killzone",  f.killzone);
      setRow("f-bias",      f.daily_bias);
      setRow("f-cooldown",  f.cooldown);
      setRow("f-volregime", f.vol_regime);
    } catch (e) { /* ignore */ }
  }

  async function refreshStrategies() {
    try {
      const r = await fetch("/api/strategies");
      const d = await r.json();
      const list = d.strategies || [];
      const nA = list.filter(s => s.tier === "A").length;
      const nB = list.filter(s => s.tier === "B").length;
      const nOther = list.length - nA - nB;
      $("strategies-count").textContent = `${list.length} live  (A:${nA} · B:${nB} · core:${nOther})`;
      const fmtPct = (x) => x == null ? "—" : (Math.round(x * 100) + "%");
      const fmtRR = (s) => (s.stop_pts && s.target_pts) ? `${s.stop_pts}/${s.target_pts}` : "—";
      $("strategies-body").innerHTML = list.map(s => {
        const family = `<span class="pill family-${s.family}">${s.family}</span>`;
        const sideCls = s.side === "LONG" ? "pos" : "neg";
        const tierCls = s.tier === "A" ? "pass-pill" :
                        s.tier === "B" ? "block-pill" : "muted";
        const tierLabel = s.tier === "A" ? "A · 60%+ WR" :
                          s.tier === "B" ? "B · pos EV" : "live";
        const rowCls = s.is_live ? "" : "muted-row";
        return `<tr class="${rowCls}">
          <td>${s.name}</td>
          <td>${family}</td>
          <td class="${sideCls}">${s.side || "—"}</td>
          <td>${fmtPct(s.win_rate)}</td>
          <td>${s.profit_factor ? Number(s.profit_factor).toFixed(2) : "—"}</td>
          <td>${s.trades || "—"}</td>
          <td>${fmtRR(s)}</td>
          <td><span class="${tierCls}">${tierLabel}</span></td>
        </tr>`;
      }).join("");
    } catch (e) { /* ignore */ }
  }

  // ---- price poll (500ms) -------------------------------------------
  async function refreshPrice() {
    try {
      const r = await fetch("/api/price");
      const d = await r.json();
      if (d.price != null) $("price").textContent = fmtNum(d.price, 2);
      if (d.ts) $("price-ts").textContent = d.ts;
    } catch (e) { /* ignore */ }
  }

  // ---- "updated Xs ago" using LOCAL delta ---------------------------
  function tickAge() {
    if (!lastDataReceivedAt) {
      $("age-label").textContent = "updated —";
      return;
    }
    const sec = Math.floor((Date.now() - lastDataReceivedAt) / 1000);
    $("age-label").textContent = `updated ${sec}s ago`;
  }

  // ---- bootstrap ----------------------------------------------------
  function start() {
    ensureChart();
    refreshData();
    refreshCandles();
    refreshFilterConfig();
    refreshStrategies();
    refreshLast100();
    refreshLiveChart();
    setInterval(refreshData, 30_000);
    setInterval(refreshCandles, 60_000);
    setInterval(refreshPrice, 500);
    setInterval(refreshFilterConfig, 60_000);
    setInterval(refreshStrategies, 120_000);
    setInterval(refreshLast100, 30_000);
    setInterval(refreshLiveChart, 60_000);
    setInterval(tickAge, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else { start(); }
})();
