/* HFT Bot dashboard — tabbed layout.
   Polling cadence:
     /api/data           every 15s  (whole snapshot — drives ribbon + Lucid)
     /api/live_position  every 3s   (live unrealized P&L when in trade)
     /api/freshness      every 30s  (chart-staleness pill)
     /api/live_chart     every 60s  (Plotly chart redraw)
     /api/brain          every 15s  (Brain tab)
     /api/last_trades    every 30s  (Trades tab + Funded counts pull from /api/data)
*/
(function () {
  const $ = (id) => document.getElementById(id);
  const fmtMoney = (n) =>
    n == null ? "—"
              : n.toLocaleString("en-US", { style: "currency", currency: "USD",
                                             minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const fmtNum = (n, d = 2) => (n == null || isNaN(n)) ? "—" : Number(n).toFixed(d);
  const fmtSigned = (n) => n == null ? "—" : (n >= 0 ? "+" : "") + fmtMoney(n);

  let lastDataReceivedAt = 0;

  // ---- Tab routing -------------------------------------------------
  function activateTab(name) {
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".tabpane").forEach(p =>
      p.classList.toggle("active", p.id === "pane-" + name));
    // Chart needs to be (re)sized once visible
    if (name === "chart") {
      ensureChart();
      if (_chart) {
        try { _chart.timeScale().fitContent(); } catch (e) {}
      }
    }
  }
  document.querySelectorAll(".tab").forEach(t => {
    t.addEventListener("click", () => activateTab(t.dataset.tab));
  });

  // ---- /api/data — drives ribbon + Lucid panel + funded ledger -----
  async function refreshData() {
    try {
      const r = await fetch("/api/data");
      const d = await r.json();
      lastDataReceivedAt = Date.now();
      paintRibbon(d);
      paintLucid(d.lucid_account || {});
      paintFunded(d.funded_accounts || {});
      paintReadiness(d.trade_readiness || {});
      paintFilterValues(d);
    } catch (e) {
      $("health-dot").className = "dot bad";
    }
  }

  // ---- Live filter values (Brain tab) ------------------------------
  function paintFilterValues(d) {
    const ms = d.microstructure || {};
    const kz = d.kill_zone || {};
    const blk = (el) => { if ($(el)) $(el).className = "big-number neg"; };
    const ok  = (el) => { if ($(el)) $(el).className = "big-number pos"; };
    const yel = (el) => { if ($(el)) $(el).className = "big-number"; };

    // VPIN: blocking when regime in HIGH/EXTREME or crash_warning
    const vp = ms.vpin;
    if (vp) {
      $("filt-vpin-val").textContent = (vp.value ?? 0).toFixed(3);
      const reg = vp.regime || "—";
      const crash = vp.crash_warning ? " ⚠ crash" : "";
      $("filt-vpin-meta").textContent = `${reg}${crash}  •  blocks at HIGH or EXTREME`;
      if (reg === "EXTREME" || vp.crash_warning) blk("filt-vpin-val");
      else if (reg === "HIGH" || reg === "ELEVATED") yel("filt-vpin-val");
      else ok("filt-vpin-val");
    }
    // Adverse Selection
    const ad = ms.adverse_selection;
    if (ad) {
      $("filt-adverse-val").textContent = (ad.score ?? 0).toFixed(3);
      const reg = ad.regime || "—";
      $("filt-adverse-meta").textContent = `${reg}  •  blocks at HIGH or EXTREME`;
      if (reg === "EXTREME" || reg === "HIGH") blk("filt-adverse-val");
      else if (reg === "ELEVATED") yel("filt-adverse-val");
      else ok("filt-adverse-val");
    }
    // Regime (multiplier only, never a hard block)
    const rg = ms.regime;
    if (rg) {
      $("filt-regime-val").textContent = rg.state || "—";
      $("filt-regime-meta").textContent = `confidence ${(rg.confidence ?? 0).toFixed(2)}  •  scales position size`;
      yel("filt-regime-val");
    }
    // GEX (sizing only)
    const gx = ms.gex;
    if (gx) {
      const b = (gx.total_gex_billion ?? 0).toFixed(1);
      $("filt-gex-val").textContent = `$${b}B`;
      $("filt-gex-meta").textContent = `${gx.regime || "—"}  •  scales position size`;
      yel("filt-gex-val");
    }
    // Macro (sizing only)
    const mc = ms.macro;
    if (mc) {
      const sc = mc.score ?? 0;
      $("filt-macro-val").textContent = sc.toFixed(2);
      $("filt-macro-meta").textContent = `${mc.bias || "—"}  •  scales position size`;
      yel("filt-macro-val");
    }
    // Kill zone — actual hard block
    if (kz) {
      $("filt-kz-val").textContent = kz.active ? (kz.name || "ACTIVE") : "OFF";
      $("filt-kz-meta").textContent = kz.active ? "trades allowed" : `next: ${kz.next || "—"}`;
      if (kz.active) ok("filt-kz-val"); else blk("filt-kz-val");
    }
  }

  function paintRibbon(d) {
    $("health-dot").className = "dot ok";
    $("cycle-label").textContent = d.cycle != null ? `cycle ${d.cycle}` : "cycle —";
    const L = d.lucid_account || {};
    $("acct-pill").textContent = `account #${L.account_id ?? "—"}`;
    $("r-price").textContent = fmtNum(d.price, 2);
    $("r-balance").textContent = fmtMoney(L.balance);
    const tp = L.today_pnl ?? 0;
    $("r-today").textContent = fmtSigned(tp);
    $("r-today").className = tp > 0 ? "pos" : tp < 0 ? "neg" : "";
    const cp = L.cum_pnl ?? 0;
    $("r-cum").textContent = fmtSigned(cp);
    $("r-cum").className = cp > 0 ? "pos" : cp < 0 ? "neg" : "";
    const a = d.account || {};
    if (a.open_position) {
      const op = a.open_position;
      $("r-pos").textContent = `${op.side} ${op.signal_name || ""} x${op.qty}`;
      $("r-pos-stat").classList.add("pos-open");
    } else {
      $("r-pos").textContent = "FLAT";
      $("r-pos-stat").classList.remove("pos-open");
    }
    const kz = d.kill_zone || {};
    $("kz-label").textContent = kz.active ? `▶ ${kz.name}` : (kz.next ? `next: ${kz.next}` : "—");
  }

  function paintLucid(L) {
    if (!L || !Object.keys(L).length) return;
    $("lucid-balance").textContent = fmtMoney(L.balance);
    $("lucid-trail").textContent = fmtMoney(L.trail_floor);
    $("lucid-trail-locked").textContent = L.trail_locked ? "locked at break-even" : "trailing $2K below peak";
    $("lucid-buffer").textContent = fmtMoney(L.buffer_to_trail);
    const tp = L.today_pnl ?? 0;
    const tpEl = $("lucid-today-pnl");
    tpEl.textContent = fmtSigned(tp);
    tpEl.className = "big-number " + (tp > 0 ? "pos" : tp < 0 ? "neg" : "");
    $("lucid-dll-remaining").textContent = L.dll_hit ? "DLL HIT — no new entries" : `DLL room ${fmtMoney(L.dll_remaining)}`;
    const cp = L.cum_pnl ?? 0;
    const cpEl = $("lucid-cum-pnl");
    cpEl.textContent = fmtSigned(cp);
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

  function paintFunded(F) {
    if (!F) return;
    $("funded-active-pill").textContent = `active #${F.active_account_id ?? "—"}`;
    $("funded-failed-pill").textContent = `${F.n_failed ?? 0} failed`;
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
    }).join("") || `<tr><td colspan="11" class="muted">No archived accounts yet — current account is the first run.</td></tr>`;
  }

  function paintReadiness(tr) {
    const pct = Math.round((tr.pct || 0) * 100);
    $("readiness-pct").textContent = `${pct}%`;
    $("readiness-fill").style.width = `${pct}%`;
    $("passing").innerHTML = (tr.passing || []).map(p => `<span class="pass-pill">${p}</span>`).join(" ") || "—";
    $("blocking").innerHTML = (tr.blocking || []).map(p => `<span class="block-pill">${p}</span>`).join(" ") || "—";
  }

  // ---- /api/live_position — fast tick (3s) when in a trade ---------
  async function refreshLivePosition() {
    try {
      const r = await fetch("/api/live_position");
      const p = await r.json();
      paintLivePosition(p);
    } catch (e) { /* ignore */ }
  }

  function paintLivePosition(p) {
    const body = $("live-position-body");
    const pill = $("live-state-pill");
    if (!p.in_trade) {
      pill.textContent = "FLAT"; pill.className = "pill";
      body.innerHTML = `<p class="muted">No open position. The bot is watching <span id="live-watch-count">${(window._brainWatchedN ?? "—")}</span> strategies on the whitelist.</p>`;
      return;
    }
    pill.textContent = "IN TRADE"; pill.className = "pill pill-pos";
    const pnl = p.unrealized_pnl ?? 0;
    const pnlCls = pnl > 0 ? "pos" : pnl < 0 ? "neg" : "";
    const sideCls = p.side === "LONG" ? "pos" : "neg";
    const progress = (p.progress_to_target ?? 0.5) * 100;
    body.innerHTML = `
      <div class="live-pos-grid">
        <div><span class="muted small">Signal</span><div class="big-number">${p.signal || "—"}</div>
             <span class="muted small ${sideCls}">${p.side} • x${p.qty} MNQ</span></div>
        <div><span class="muted small">Unrealized P&amp;L</span>
             <div class="big-number ${pnlCls}">${fmtSigned(pnl)}</div>
             <span class="muted small">${fmtNum(p.pts_pnl, 1)} pts</span></div>
        <div><span class="muted small">Entry</span><div class="big-number">${fmtNum(p.entry_px, 2)}</div></div>
        <div><span class="muted small">Now</span><div class="big-number">${fmtNum(p.current_px, 2)}</div></div>
        <div><span class="muted small">Stop</span><div class="big-number neg">${fmtNum(p.stop_px, 2)}</div>
             <span class="muted small">${fmtNum(p.pts_to_stop, 1)} pts away</span><br>
             <span class="muted small">risk ${fmtMoney(p.risk_at_stop)}</span></div>
        <div><span class="muted small">Target</span><div class="big-number pos">${fmtNum(p.target_px, 2)}</div>
             <span class="muted small">${fmtNum(p.pts_to_target, 1)} pts away</span><br>
             <span class="muted small">reward ${fmtMoney(p.reward_at_target)}</span></div>
      </div>
      <div class="trade-progress">
        <div class="trade-progress-track">
          <div class="trade-progress-fill" style="width:${progress}%"></div>
          <div class="trade-progress-marker" style="left:${progress}%"></div>
        </div>
        <div class="trade-progress-labels">
          <span class="neg">STOP</span>
          <span>${Math.round(progress)}% to target</span>
          <span class="pos">TARGET</span>
        </div>
      </div>`;
  }

  // ---- TradingView Lightweight Charts (NQ=F, yfinance feed) --------
  // Uses the open-source library bundled in /static/lightweightcharts.js.
  // Same chart engine as TradingView's web app, just rendered with our own
  // data so it actually shows real NQ futures (CME_MINI:NQ1! is restricted
  // in the free Advanced Chart widget).
  let _chart = null, _candleSeries = null;

  function ensureChart() {
    if (_chart) return;
    if (!window.LightweightCharts) return;
    const el = document.getElementById("lwchart");
    if (!el) return;
    _chart = LightweightCharts.createChart(el, {
      layout: { background: { color: "#131722" }, textColor: "#d8def0" },
      grid:   { horzLines: { color: "#1e222d" }, vertLines: { color: "#1e222d" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#363a45" },
      rightPriceScale: { borderColor: "#363a45" },
      crosshair: { mode: 1 },
    });
    _candleSeries = _chart.addCandlestickSeries({
      upColor: "#26a69a", downColor: "#ef5350",
      borderUpColor: "#26a69a", borderDownColor: "#ef5350",
      wickUpColor: "#26a69a", wickDownColor: "#ef5350",
    });
    new ResizeObserver(() => _chart.applyOptions({
      width: el.clientWidth, height: 560,
    })).observe(el);
  }

  async function refreshCandles() {
    ensureChart();
    if (!_candleSeries) return;
    try {
      const r = await fetch("/api/candles");
      const arr = await r.json();
      if (!Array.isArray(arr) || !arr.length) return;
      _candleSeries.setData(arr);
      // Freshness pill
      const lastSec = arr[arr.length - 1].time;
      const ageMin = Math.round((Date.now() / 1000 - lastSec) / 60);
      const pill = document.getElementById("freshness-pill");
      if (pill) {
        let label, cls;
        if (ageMin <= 6)       { label = `live (${ageMin} min)`;     cls = "pill pos"; }
        else if (ageMin <= 20) { label = `delayed ${ageMin} min`;    cls = "pill"; }
        else                    { label = `stale ${ageMin} min`;       cls = "pill bad"; }
        pill.textContent = label; pill.className = cls;
      }
    } catch (e) { /* ignore */ }
  }

  async function refreshTradeMarkers() {
    if (!_candleSeries) return;
    try {
      const r = await fetch("/api/trade_markers");
      const m = await r.json();
      if (Array.isArray(m)) _candleSeries.setMarkers(m);
    } catch (e) { /* ignore */ }
  }

  // ---- /api/brain — Brain tab ---------------------------------------
  async function refreshBrain() {
    try {
      const r = await fetch("/api/brain");
      const b = await r.json();
      window._brainWatchedN = b.n_strategies_watched;
      $("brain-doing").innerHTML = b.in_trade
        ? `<span class="pos">IN TRADE</span> — managing an open position`
        : `<span class="muted">FLAT</span> — no open trade, evaluating new signals each tick`;
      const ago = b.as_of ? Math.round((Date.now() - new Date(b.as_of).getTime()) / 1000) : null;
      $("brain-last-tick").textContent = ago != null ? `${ago}s ago (cycle ${b.cycle})` : "—";
      $("brain-kz").textContent = b.kill_zone?.active ? `ACTIVE — ${b.kill_zone.name}` : (`outside trade window — next: ${b.kill_zone?.next || "—"}`);
      $("brain-watched").textContent = `${b.n_strategies_watched} strategies (entry triggers being checked every tick)`;
      $("brain-counts").innerHTML = `<span class="pos">${b.n_recent_entries} entries taken</span> · `
        + `<span class="neg">${b.n_recent_blocked} signals blocked by Lucid guard</span> · `
        + `<span class="muted">${b.n_recent_exits} exits</span>`;
      // Events
      const evs = (b.events || []).slice().reverse();
      $("brain-events").innerHTML = evs.map(e => {
        const t = (e.ts || "").slice(11, 19);
        let typeCls = "";
        if (e.type === "ENTRY")   typeCls = "pos";
        else if (e.type === "EXIT") typeCls = "muted";
        else if (e.type === "BLOCKED") typeCls = "neg";
        const detail = e.reason || e.rule || (e.entry_px ? `@ ${fmtNum(e.entry_px,2)}` : "");
        return `<tr>
          <td>${t}</td>
          <td class="${typeCls}">${e.type || "—"}</td>
          <td>${e.signal || "—"}</td>
          <td>${e.side || ""}</td>
          <td class="muted small">${detail}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="5" class="muted">No recent events.</td></tr>`;
      // Whitelist
      $("brain-whitelist").innerHTML = (b.whitelist || []).map(s => {
        const sCls = s.side === "LONG" ? "pos" : "neg";
        const wr = s.win_rate ? Math.round(s.win_rate * 100) + "%" : "—";
        const sr = (s.stop_pts && s.target_pts) ? `${s.stop_pts} / ${s.target_pts}` : "—";
        return `<tr>
          <td>${s.name}</td>
          <td class="${sCls}">${s.side}</td>
          <td>${sr}</td>
          <td>${wr}</td>
        </tr>`;
      }).join("");
    } catch (e) { /* ignore */ }
  }

  // ---- /api/strategies — Strategies tab -----------------------------
  async function refreshStrategies() {
    try {
      const r = await fetch("/api/strategies");
      const d = await r.json();
      const list = d.strategies || [];
      $("strategies-count").textContent = `${list.length} total · ${d.n_live ?? 0} live · ${d.n_watch ?? 0} watch`;
      const fmtPct = (x) => x == null ? "—" : (Math.round(x * 100) + "%");
      const fmtPF  = (x) => x == null ? "—" : Number(x).toFixed(2);
      const fmtRR  = (s) => (s.stop_pts && s.target_pts)
        ? `${s.stop_pts} / ${s.target_pts}` : "—";
      const fmtRRRatio = (s) => (s.stop_pts && s.target_pts)
        ? (s.target_pts / s.stop_pts).toFixed(2) : "—";
      $("strategies-body").innerHTML = list.map(s => {
        const family = `<span class="pill family-${s.family}">${s.family}</span>`;
        const sCls = s.side === "LONG" ? "pos" : "neg";
        const tierCls = s.tier === "A" ? "pass-pill" : (s.tier === "B" ? "block-pill" : "muted");
        const tierLabel = s.tier === "A" ? "A · live" : (s.tier === "B" ? "B · watch" : "live");
        const pnl = s.net_pnl ?? 0;
        const pnlCls = pnl > 0 ? "pos" : pnl < 0 ? "neg" : "";
        return `<tr data-strat="${s.name}" class="${s.is_live ? '' : 'muted-row'}">
          <td>${s.name}</td>
          <td>${family}</td>
          <td class="${sCls}">${s.side || "—"}</td>
          <td>${fmtRR(s)}</td>
          <td>${fmtRRRatio(s)}</td>
          <td>${s.trades ?? "—"}</td>
          <td>${fmtPct(s.win_rate)}</td>
          <td>${fmtPF(s.profit_factor)}</td>
          <td class="${pnlCls}">${pnl ? fmtMoney(pnl) : "—"}</td>
          <td><span class="${tierCls}">${tierLabel}</span></td>
        </tr>`;
      }).join("") || `<tr><td colspan="10" class="muted">No strategies loaded.</td></tr>`;
      // Wire click-to-open-modal on every row
      document.querySelectorAll("#strategies-body tr[data-strat]").forEach(tr => {
        tr.addEventListener("click", () => openStrategyModal(tr.dataset.strat));
      });
    } catch (e) { /* ignore */ }
  }

  // ---- Strategy detail modal ----------------------------------------
  async function openStrategyModal(name) {
    const modal = $("strat-modal");
    const content = $("strat-modal-content");
    modal.style.display = "flex";
    content.innerHTML = `<p class="muted">loading ${name}…</p>`;
    try {
      const r = await fetch(`/api/strategy/${encodeURIComponent(name)}`);
      const d = await r.json();
      const stats = d.stats || {};
      const fmtPct = (x) => x == null ? "—" : (Math.round(x * 100) + "%");
      const fmtPF  = (x) => x == null ? "—" : Number(x).toFixed(2);
      const sCls = d.side === "LONG" ? "pos" : d.side === "SHORT" ? "neg" : "";
      const triggersHtml = (d.triggers || []).length
        ? `<h4>Triggers</h4><ol class="trig-list">${d.triggers.map(t => `<li>${t}</li>`).join("")}</ol>`
        : "";
      const ideaHtml = d.idea ? `<p>${d.idea}</p>` : "";
      const descHtml = d.description ? `<p>${d.description}</p>` : "";
      const notesHtml = d.notes ? `<p class="muted small"><b>Notes:</b> ${d.notes}</p>` : "";
      const statsHtml = Object.keys(stats).length ? `
        <h4>Backtest Stats <span class="muted small">(out-of-sample 2024-2026)</span></h4>
        <table class="kv">
          <tr><th>Side</th><td class="${sCls}">${d.side || "—"}</td></tr>
          <tr><th>Stop / Target</th><td>${stats.stop_pts ?? "—"} / ${stats.target_pts ?? "—"} pts</td></tr>
          <tr><th>Trades (sample)</th><td>${stats.trades ?? "—"}</td></tr>
          <tr><th>Win rate</th><td>${fmtPct(stats.win_rate)}</td></tr>
          <tr><th>Profit factor</th><td>${fmtPF(stats.profit_factor)}</td></tr>
          <tr><th>Net P&amp;L</th><td>${stats.net_pnl != null ? fmtMoney(stats.net_pnl) : "—"}</td></tr>
          <tr><th>Tier</th><td>${stats.tier || "—"} ${stats.is_live ? "<span class='pass-pill'>LIVE</span>" : ""}</td></tr>
          <tr><th>Rigor</th><td>${stats.rigor_level || "—"}</td></tr>
        </table>` : "";
      content.innerHTML = `
        <div class="modal-head">
          <div>
            <div style="font-size:11px;letter-spacing:.06em;color:#8a93a8;text-transform:uppercase">${d.family || ""} • ${d.side || ""}</div>
            <h2 style="margin:4px 0 2px 0">${d.title || name}</h2>
            <div class="muted small" style="font-family:monospace">${name}</div>
          </div>
        </div>
        ${ideaHtml}
        ${triggersHtml}
        ${descHtml}
        ${statsHtml}
        ${notesHtml}`;
    } catch (e) {
      content.innerHTML = `<p class="neg">failed to load: ${e}</p>`;
    }
  }
  function closeStrategyModal() { $("strat-modal").style.display = "none"; }

  // ---- /api/last_trades — Trades tab --------------------------------
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
      }).join("") || `<tr><td colspan="10" class="muted">No trades yet.</td></tr>`;
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
    refreshData();
    refreshLivePosition();
    refreshBrain();
    refreshLast100();
    refreshStrategies();
    refreshCandles();
    refreshTradeMarkers();
    setInterval(refreshData,         15_000);
    setInterval(refreshLivePosition,  3_000);
    setInterval(refreshBrain,        15_000);
    setInterval(refreshLast100,      30_000);
    setInterval(refreshStrategies,  120_000);   // backtest stats rarely change
    setInterval(refreshCandles,      30_000);
    setInterval(refreshTradeMarkers, 30_000);
    setInterval(tickAge,              1_000);
  }
  // Wire modal close handlers once DOM is ready
  function wireModal() {
    const close = $("strat-modal-close");
    const bg = $("strat-modal-bg");
    if (close) close.addEventListener("click", closeStrategyModal);
    if (bg) bg.addEventListener("click", closeStrategyModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeStrategyModal();
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { start(); wireModal(); });
  } else { start(); wireModal(); }
})();
