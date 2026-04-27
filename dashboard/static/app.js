/* Dashboard front-end. Polls /api/state every 5s and refreshes the chart every 30s. */
(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (n, d = 2) => (n == null || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmtUSD = (n) => (n == null) ? "—" : (n >= 0 ? "+" : "") + "$" + fmt(n, 0);

  let chart, candleSeries;

  function initChart() {
    if (!window.LightweightCharts) return;
    chart = LightweightCharts.createChart($("chart"), {
      layout: { background: { color: "#131a30" }, textColor: "#e6e9f4" },
      grid: { vertLines: { color: "#1f2849" }, horzLines: { color: "#1f2849" } },
      timeScale: { borderColor: "#2a3358", timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#2a3358" },
      crosshair: { mode: 0 },
    });
    candleSeries = chart.addCandlestickSeries({
      upColor: "#2dd884", downColor: "#f25c63",
      wickUpColor: "#2dd884", wickDownColor: "#f25c63",
      borderVisible: false,
    });
    window.addEventListener("resize", () => chart.applyOptions({ width: $("chart").clientWidth }));
  }

  async function refreshCandles() {
    if (!candleSeries) return;
    try {
      const r = await fetch("/api/candles");
      const data = await r.json();
      candleSeries.setData(data);
    } catch (e) { /* keep last data */ }
  }

  function renderReadiness(state) {
    const r = state.trade_readiness || { pct: 0, passing: [], blocking: [], total_checks: 7 };
    const pct = Math.round((r.pct || 0) * 100);
    const html = `
      <div class="bar"><span style="width:${pct}%"></span></div>
      <div class="row"><span class="label">Readiness</span><span><b>${pct}%</b> (${(r.passing||[]).length}/${r.total_checks||7})</span></div>
      <div class="row"><span class="pass">Passing</span><span>${(r.passing || []).join(", ") || "—"}</span></div>
      <div class="row"><span class="block">Blocking</span><span>${(r.blocking || []).join(", ") || "—"}</span></div>
      <div class="row"><span class="label">In trade</span><span>${r.in_trade ? "yes" : "no"}</span></div>
    `;
    $("readiness").innerHTML = html;
  }

  function renderMicro(state) {
    const ms = state.microstructure || {};
    const rows = [];
    if (ms.vpin) rows.push(["VPIN", `${ms.vpin.regime} ${fmt(ms.vpin.value, 3)} (${ms.vpin.trend})`]);
    if (ms.adverse_selection) rows.push(["Adverse", `${ms.adverse_selection.regime} ${fmt(ms.adverse_selection.score, 3)}`]);
    if (ms.regime) rows.push(["Regime", `${ms.regime.state} (${fmt(ms.regime.confidence, 2)})`]);
    if (ms.gex) rows.push(["GEX", `${ms.gex.regime} $${fmt(ms.gex.total_gex_billion, 1)}B (${fmt(ms.gex.intensity_pct, 0)}%)`]);
    if (ms.macro) rows.push(["Macro", `${ms.macro.bias} ${fmt(ms.macro.score, 2)}`]);
    $("microstructure").innerHTML = rows.map(([k, v]) =>
      `<div class="row"><span class="label">${k}</span><span>${v}</span></div>`).join("");
  }

  function renderOpen(state) {
    const op = state.account && state.account.open_position;
    if (!op) { $("open").innerHTML = `<div class="row"><span class="label">flat</span></div>`; return; }
    $("open").innerHTML = `
      <div class="row"><span class="label">Signal</span><b>${op.signal_name}</b></div>
      <div class="row"><span class="label">Side</span><b class="${op.side === 'LONG' ? 'pass' : 'block'}">${op.side}</b></div>
      <div class="row"><span class="label">Entry</span>${fmt(op.entry_px)}</div>
      <div class="row"><span class="label">Stop</span>${fmt(op.stop_px)}</div>
      <div class="row"><span class="label">Target</span>${fmt(op.target_px)}</div>
      <div class="row"><span class="label">Contracts</span>${op.contracts}</div>
      <div class="row"><span class="label">ML</span>${op.ml_decision} R:R ${fmt(op.rr,2)}</div>
    `;
  }

  function renderTrades(state) {
    const tbody = $("trades").querySelector("tbody");
    const rows = (state.recent_trades || []).slice().reverse().map(t => {
      const cls = t.win ? "green" : "red";
      return `<tr>
        <td>${t.signal_name}</td>
        <td>${t.side}</td>
        <td>${fmt(t.entry_px)}</td>
        <td>${fmt(t.exit_px)}</td>
        <td class="${cls}">${fmt(t.pnl_points, 1)}</td>
        <td class="${cls}">${fmtUSD(t.pnl_dollars)}</td>
        <td>${t.exit_reason || ""}</td>
      </tr>`;
    });
    tbody.innerHTML = rows.join("") || `<tr><td colspan="7">no trades yet</td></tr>`;
  }

  function renderEvents(state) {
    const ev = state.recent_signal_events || [];
    $("events").innerHTML = ev.slice().reverse().map(e =>
      `<li>[${(e.ts||'').replace('T',' ').slice(0,19)}] ${e.type} ${e.signal||''} ${e.side||''} ${e.entry_px ? '@'+fmt(e.entry_px,2):''}</li>`
    ).join("") || "<li>—</li>";
  }

  async function refreshState() {
    try {
      const r = await fetch("/api/state");
      const s = await r.json();
      $("cycle").textContent = s.cycle ?? "—";
      $("price").textContent = s.price != null ? fmt(s.price, 2) : "—";
      $("balance").textContent = s.account ? "$" + fmt(s.account.balance, 0) : "—";
      $("pnl").textContent = s.account ? fmtUSD(s.account.realized_pnl) : "—";
      $("error").textContent = s.monitor_error || "";
      $("kz").textContent = s.kill_zone && s.kill_zone.active ? `· ${s.kill_zone.name}` : (s.kill_zone ? `· next: ${s.kill_zone.next}` : "");
      $("whitelist").innerHTML = (s.whitelist || []).map(x => `<span>${x}</span>`).join("");
      renderReadiness(s);
      renderMicro(s);
      renderOpen(s);
      renderTrades(s);
      renderEvents(s);
    } catch (e) {
      $("error").textContent = "state fetch failed";
    }
  }

  function start() {
    initChart();
    refreshCandles();
    refreshState();
    setInterval(refreshState, 5000);
    setInterval(refreshCandles, 30000);
  }
  document.addEventListener("DOMContentLoaded", start);
})();
