/* HFT Bot v11 dashboard — tabbed layout.
   Polling cadence:
     /api/data            every 15s  (whole snapshot — drives ribbon + Lucid + Funded)
     /api/live_position   every 3s   (live unrealized P&L when in trade)
     /api/freshness       every 30s  (chart-staleness pill)
     /api/v11/brain       every 10s  (Brain tab — Z scores update fast)
     /api/v11/strategies  every 5min (mining stats, rarely change)
     /api/last_trades     every 30s  (Trades tab)
     /api/candles         every 30s  (chart redraw)
     /api/trade_markers   every 30s  (trade arrows on chart)
*/
(function () {
  const $ = (id) => document.getElementById(id);
  const fmtMoney = (n) =>
    n == null ? "—"
              : n.toLocaleString("en-US", { style: "currency", currency: "USD",
                                             minimumFractionDigits: 0, maximumFractionDigits: 2 });
  const fmtNum = (n, d = 2) => (n == null || isNaN(n)) ? "—" : Number(n).toFixed(d);
  const fmtSigned = (n) => n == null ? "—" : (n >= 0 ? "+" : "") + fmtMoney(n);
  const fmtPct = (x) => x == null ? "—" : (Math.round(x * 100) + "%");

  let lastDataReceivedAt = 0;
  // Strategies state for sortable table
  let _strategiesData = [];
  let _strategiesSort = { col: "sharpe", dir: "desc" };

  // ---- Tab routing -------------------------------------------------
  function activateTab(name) {
    document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".tabpane").forEach(p =>
      p.classList.toggle("active", p.id === "pane-" + name));
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

  // =====================================================================
  // /api/data — drives ribbon + Lucid + Funded
  // =====================================================================
  async function refreshData() {
    try {
      const r = await fetch("/api/data");
      const d = await r.json();
      lastDataReceivedAt = Date.now();
      paintRibbon(d);
      paintLucid(d.lucid_account || {});
      paintFunded(d.funded_accounts || {});
    } catch (e) {
      $("health-dot").className = "dot bad";
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
      $("r-pos").textContent = `${op.side} x${op.qty}`;
      $("r-pos-stat").classList.add("pos-open");
    } else {
      $("r-pos").textContent = "FLAT";
      $("r-pos-stat").classList.remove("pos-open");
    }
    // NY time bucket from v11 block
    const v11 = d.v11 || {};
    if (v11.ny_bucket) $("ny-bucket-label").textContent = v11.ny_bucket;
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
    // Adaptive size — derived from buffer (matches monte_carlo_v11.adaptive_qty_factor)
    const bal = L.balance ?? 50000;
    const trail = L.trail_floor ?? 48000;
    const buffer = bal - trail;
    const baseSize = (window._v11BaseSize || 25);
    const scale = (L.starting_balance || 50000) / 50000;
    const bn = buffer / scale;
    let factor = 1.0;
    if (bn < 200)       factor = 0;
    else if (bn < 500)  factor = 0.20;
    else if (bn < 1000) factor = 0.40;
    else if (bn < 2000) factor = 0.60;
    else if (bn < 4000) factor = 0.85;
    const adaptiveQty = factor === 0 ? 0 : Math.max(1, Math.floor(baseSize * factor));
    const sizeEl = $("lucid-size");
    if (sizeEl) {
      sizeEl.textContent = adaptiveQty + " MNQ";
      sizeEl.className = "big-number " + (adaptiveQty === 0 ? "neg" : adaptiveQty < baseSize ? "" : "pos");
    }
    if ($("lucid-size-meta")) $("lucid-size-meta").textContent = `base ${baseSize} MNQ × ${(factor*100).toFixed(0)}%`;
    $("lucid-takehome").textContent = fmtMoney(L.take_home_at_split);
    const peEl = $("lucid-payout");
    if (peEl) {
      peEl.textContent = L.payout_eligible ? "READY" : "—";
      peEl.className = "big-number " + (L.payout_eligible ? "pos" : "");
    }
    if ($("lucid-payout-reason")) $("lucid-payout-reason").textContent = L.payout_reason || "—";
  }

  function paintFunded(F) {
    if (!F) return;
    $("funded-active-pill").textContent = `active #${F.active_account_id ?? "—"}`;
    $("funded-failed-pill").textContent = `${F.n_failed ?? 0} failed`;
    if ($("funded-passed-pill")) $("funded-passed-pill").textContent = `${F.n_passed ?? 0} passed`;
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

  // =====================================================================
  // /api/price — fast tick (3s) for ribbon price (independent of bot health)
  // =====================================================================
  async function refreshPrice() {
    try {
      const r = await fetch("/api/price");
      const p = await r.json();
      if (p.price != null) {
        $("r-price").textContent = fmtNum(p.price, 2);
      }
    } catch (e) { /* ignore */ }
  }

  // =====================================================================
  // /api/live_position — fast tick (3s) when in a trade
  // =====================================================================
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
      body.innerHTML = `<p class="muted">No open position. Bot is watching <span id="live-watch-count">${(window._brainStrategyCount ?? "—")}</span> v11 strategies on NQ-ES divergence.</p>`;
      return;
    }
    pill.textContent = "IN TRADE"; pill.className = "pill pill-pos";
    const pnl = p.unrealized_pnl ?? 0;
    const pnlCls = pnl > 0 ? "pos" : pnl < 0 ? "neg" : "";
    const sideCls = p.side === "LONG" ? "pos" : "neg";
    const progress = (p.progress_to_target ?? 0.5) * 100;
    body.innerHTML = `
      <div class="live-pos-grid">
        <div><span class="muted small">Strategy</span><div class="big-number" style="font-size:14px;font-family:monospace">${p.signal || "—"}</div>
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

  // =====================================================================
  // /api/v11/brain — Brain tab (Z-scores, closest to trigger, recent fires)
  // =====================================================================
  async function refreshV11Brain() {
    try {
      const r = await fetch("/api/v11/brain");
      const b = await r.json();
      paintBrainStatus(b);
      paintZScores(b.z_scores || {}, b.closest_to_trigger || []);
      paintClosestToTrigger(b.closest_to_trigger || []);
      paintRecentFires(b.recent_fires || []);
    } catch (e) { /* ignore */ }
  }

  function paintBrainStatus(b) {
    const summary = b.summary || {};
    window._brainStrategyCount = summary.count || 0;
    window._v11BaseSize = b.base_size || 25;
    if ($("brain-strategy-count")) $("brain-strategy-count").textContent = summary.count ?? "—";
    if ($("brain-strategy-breakdown")) $("brain-strategy-breakdown").textContent =
      `${summary.long_count || 0} LONG / ${summary.short_count || 0} SHORT`;
    if ($("brain-last-bar") && b.last_bar_ts) {
      $("brain-last-bar").textContent = b.last_bar_ts.slice(11, 16) + " UTC";
    }
    if ($("brain-ny-bucket")) $("brain-ny-bucket").textContent = b.ny_bucket || "—";
    if ($("brain-atr")) $("brain-atr").textContent = b.atr != null ? Number(b.atr).toFixed(2) : "—";
    if ($("brain-bars")) $("brain-bars").textContent = b.bars_processed ?? 0;
    if ($("brain-fired")) $("brain-fired").textContent = b.signals_fired ?? 0;
    if ($("brain-blocked")) $("brain-blocked").textContent = `${b.signals_blocked ?? 0} blocked`;
    const stateText = b.in_trade ? "IN TRADE"
      : ((b.lucid && b.lucid.dll_hit) ? "DLL HIT — paused"
      : "FLAT — evaluating");
    if ($("brain-state-text")) {
      $("brain-state-text").textContent = stateText;
      $("brain-state-text").className = "big-number " + (b.in_trade ? "pos" : "");
    }
  }

  function paintZScores(zScores, closest) {
    // Build small cards for each Z-window: 15, 20, 30, 45, 60, 90, 120
    const wantedWindows = [15, 20, 30, 45, 60, 90, 120];
    const grid = $("zscore-grid");
    if (!grid) return;
    // Find which windows are CURRENTLY firing
    const firedLong = new Set();
    const firedShort = new Set();
    for (const c of closest) {
      if (c.fired) {
        if (c.side === "LONG") firedLong.add(c.z_window);
        else firedShort.add(c.z_window);
      }
    }
    grid.innerHTML = wantedWindows.map(w => {
      const v = zScores[String(w)];
      const vTxt = v == null ? "—" : (v >= 0 ? "+" : "") + Number(v).toFixed(2);
      const cls = v == null ? "" : (v > 0 ? "pos" : "neg");
      let cardCls = "zscore-card";
      if (firedLong.has(w)) cardCls += " fired";
      if (firedShort.has(w)) cardCls += " fired-short";
      // Bar visualization: scale Z-value [-3, +3] to [0%, 100%], pivot at 50
      const bar = v == null ? 0 : Math.max(-3, Math.min(3, v));
      let leftPct, widthPct;
      if (bar >= 0) { leftPct = 50; widthPct = (bar / 3) * 50; }
      else          { leftPct = 50 + (bar / 3) * 50; widthPct = -bar / 3 * 50; }
      return `<div class="${cardCls}">
        <div class="zw">${w}-bar Z</div>
        <div class="zv ${cls}">${vTxt}</div>
        <div class="zbar">
          <div class="zbar-mid"></div>
          <div class="zbar-fill" style="left:${leftPct}%;width:${widthPct}%;
            background:${v == null ? "#888" : (v > 0 ? "#e74c3c" : "#2ecc71")}"></div>
        </div>
      </div>`;
    }).join("");
  }

  function paintClosestToTrigger(closest) {
    const tbody = $("closest-body");
    if (!tbody) return;
    if (!closest.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="muted">Waiting for first bar update…</td></tr>`;
      return;
    }
    tbody.innerHTML = closest.map(c => {
      const fired = c.fired;
      let statusCls, statusTxt;
      if (fired) {
        statusCls = c.side === "LONG" ? "fire-status fired-long" : "fire-status fired-short";
        statusTxt = "FIRED";
      } else if (c.distance != null && c.distance < 0.3) {
        statusCls = "fire-status near"; statusTxt = "NEAR";
      } else {
        statusCls = "fire-status idle"; statusTxt = "idle";
      }
      const sideCls = "side-" + c.side;
      const dist = c.distance == null ? "—"
        : (c.distance >= 0 ? "+" : "") + Number(c.distance).toFixed(2);
      const z = c.z_current == null ? "—"
        : (c.z_current >= 0 ? "+" : "") + Number(c.z_current).toFixed(2);
      const trigText = c.side === "LONG" ? `<−${c.z_threshold}` : `>+${c.z_threshold}`;
      return `<tr>
        <td><span class="${statusCls}">${statusTxt}</span></td>
        <td><code style="font-size:11px">${c.name.slice(0,55)}</code></td>
        <td class="${sideCls}">${c.side}</td>
        <td>${c.time_ctx || "—"}</td>
        <td>Z[${c.z_window}] ${trigText}</td>
        <td>${z}</td>
        <td class="${fired ? 'pos' : ''}">${dist}</td>
      </tr>`;
    }).join("");
  }

  function paintRecentFires(fires) {
    const tbody = $("recent-fires-body");
    if (!tbody) return;
    if (!fires.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted">No fires yet — waiting for first trigger.</td></tr>`;
      return;
    }
    const recent = fires.slice().reverse();
    tbody.innerHTML = recent.map(f => {
      const sideCls = "side-" + f.side;
      const t = (f.ts || "").slice(11, 19);
      const z = f.z_value == null ? "—"
        : (f.z_value >= 0 ? "+" : "") + Number(f.z_value).toFixed(2);
      return `<tr>
        <td>${t}</td>
        <td><code style="font-size:11px">${(f.strategy || "").slice(0, 55)}</code></td>
        <td class="${sideCls}">${f.side || "—"}</td>
        <td>${f.qty || "—"}</td>
        <td>${z}</td>
        <td>${fmtNum(f.entry, 2)}</td>
        <td>${fmtNum(f.stop, 2)}</td>
        <td>${fmtNum(f.target, 2)}</td>
      </tr>`;
    }).join("");
  }

  // =====================================================================
  // TradingView Lightweight Charts (NQ=F, yfinance feed)
  // =====================================================================
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
    const _resize = () => {
      const w = Math.max(280, el.clientWidth);
      const h = Math.min(560, Math.max(320, window.innerHeight * 0.55));
      _chart.applyOptions({ width: w, height: h });
      el.style.height = h + "px";
    };
    _resize();
    new ResizeObserver(_resize).observe(el);
    window.addEventListener("resize", _resize);
  }

  async function refreshCandles() {
    ensureChart();
    if (!_candleSeries) return;
    try {
      const r = await fetch("/api/candles");
      const arr = await r.json();
      if (!Array.isArray(arr) || !arr.length) return;
      _candleSeries.setData(arr);
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

  // =====================================================================
  // /api/v11/strategies — Strategies tab (sortable)
  // =====================================================================
  async function refreshStrategies() {
    try {
      const r = await fetch("/api/v11/strategies");
      const list = await r.json();
      _strategiesData = Array.isArray(list) ? list : [];
      renderStrategiesTable();
    } catch (e) { /* ignore */ }
  }

  function renderStrategiesTable() {
    const list = _strategiesData;
    if (!list.length) {
      $("strategies-body").innerHTML = `<tr><td colspan="8" class="muted">No v11 strategies loaded yet. If this persists after deploy, the Railway volume may be hiding mined_v11_patterns.json — restart the service to trigger the bundled-config bootstrap.</td></tr>`;
      $("strategies-count").textContent = "0 total";
      return;
    }
    $("strategies-count").textContent = `top 10 of ${list.length}`;

    // Sort
    const { col, dir } = _strategiesSort;
    const mult = dir === "asc" ? 1 : -1;
    const sorted = [...list].sort((a, b) => {
      const av = a[col]; const bv = b[col];
      if (av == null) return 1; if (bv == null) return -1;
      if (typeof av === "string") return mult * av.localeCompare(bv);
      return mult * (av - bv);
    });

    // Update header indicators
    document.querySelectorAll("#strategies-table th[data-sort]").forEach(th => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === col) th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
    });

    // Plain-English time-bucket labels
    const ctxLabel = {
      "t_1300_1330": "1:00–1:30 PM ET",
      "t_1330_1400": "1:30–2:00 PM ET",
      "t_1400_1430": "2:00–2:30 PM ET",
      "t_1430_1500": "2:30–3:00 PM ET",
      "t_1500_1530": "3:00–3:30 PM ET",
      "t_1530_1600": "3:30–4:00 PM ET",
      "pm_full":     "2:00–4:00 PM ET",
      "t_1330_1530": "1:30–3:30 PM ET",
    };
    // Compute trades/month (28 months of OOS data: Jan 2024 – Apr 2026)
    const TEST_MONTHS = 28;
    sorted.forEach((s, i) => {
      s._tpm = (s.n_test || 0) / TEST_MONTHS;
      s._idx = i + 1;
    });
    // Show only the top 10 of the current sort
    const top10 = sorted.slice(0, 10);
    $("strategies-body").innerHTML = top10.map(s => {
      const sCls = "side-" + s.side;
      const pnl = s.yearly_at_25mnq ?? 0;
      const pnlCls = pnl > 0 ? "pos" : "neg";
      const wrCls = s.wr >= 0.55 ? "pos" : (s.wr >= 0.50 ? "" : "muted");
      const pfCls = s.pf >= 1.5 ? "pos" : (s.pf >= 1.0 ? "" : "muted");
      return `<tr data-strat="${s.name}">
        <td>#${s._idx}</td>
        <td class="${sCls}">${s.side}</td>
        <td>${ctxLabel[s.time_ctx] || s.time_ctx || "—"}</td>
        <td class="${wrCls}">${fmtPct(s.wr)}</td>
        <td>${s._tpm.toFixed(1)}</td>
        <td>1:${s.rr}</td>
        <td class="${pfCls}">${Number(s.pf).toFixed(2)}</td>
        <td class="${pnlCls}">${fmtMoney(pnl)}</td>
      </tr>`;
    }).join("");

    // Re-wire row clicks → strategy detail modal
    document.querySelectorAll("#strategies-body tr[data-strat]").forEach(tr => {
      tr.addEventListener("click", () => openStrategyModal(tr.dataset.strat));
    });
  }

  // Wire up sort handlers
  function wireStrategySort() {
    document.querySelectorAll("#strategies-table th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const col = th.dataset.sort;
        if (_strategiesSort.col === col) {
          _strategiesSort.dir = _strategiesSort.dir === "asc" ? "desc" : "asc";
        } else {
          _strategiesSort.col = col;
          _strategiesSort.dir = "desc";
        }
        renderStrategiesTable();
      });
    });
  }

  // =====================================================================
  // Strategy detail modal
  // =====================================================================
  function openStrategyModal(name) {
    const modal = $("strat-modal");
    const content = $("strat-modal-content");
    modal.style.display = "flex";
    const s = _strategiesData.find(x => x.name === name);
    if (!s) {
      content.innerHTML = `<p class="muted">strategy not found: ${name}</p>`;
      return;
    }
    const sCls = "side-" + s.side;
    const ctxLabel = {
      "t_1300_1330": "1:00–1:30 PM ET",
      "t_1330_1400": "1:30–2:00 PM ET",
      "t_1400_1430": "2:00–2:30 PM ET",
      "t_1430_1500": "2:30–3:00 PM ET",
      "t_1500_1530": "3:00–3:30 PM ET",
      "t_1530_1600": "3:30–4:00 PM ET",
      "pm_full":     "2:00–4:00 PM ET (the full afternoon session)",
      "t_1330_1530": "1:30–3:30 PM ET",
    }[s.time_ctx] || s.time_ctx;
    const minutes = s.z_window * 5;
    const sideWord = s.side === "LONG" ? "BUY (go long)" : "SELL (go short)";
    const directionWord = s.side === "LONG" ? "rallies" : "falls";
    const trades_per_mo = ((s.n_test || 0) / 28).toFixed(1);

    // Plain-English explanation of WHY this works
    const ideaPara = s.side === "LONG"
      ? `NQ (Nasdaq-100 futures) and ES (S&P 500 futures) are tightly correlated — they almost always move together. When NQ has dropped MORE than ES over the last ${minutes} minutes, that's a temporary dislocation: NQ has temporarily underperformed its sister index. Historically this gap closes — NQ catches back up. So the bot BUYS NQ expecting it to rally.`
      : `NQ (Nasdaq-100 futures) and ES (S&P 500 futures) are tightly correlated — they almost always move together. When NQ has rallied MORE than ES over the last ${minutes} minutes, that's a temporary dislocation: NQ has temporarily overperformed its sister index. Historically this gap closes — NQ pulls back. So the bot SHORTS NQ expecting it to fall.`;

    // What does "Z-score" mean in plain English
    const zPara = `The bot watches a "Z-score" — a number that measures how unusual the current NQ-vs-ES gap is, compared to its normal noise. Z = 0 is normal. Z = ±1 happens often. Z = ±${s.z_threshold} is RARE — only the top few % of historical situations. That rarity is the edge.`;

    // Why this time bucket?
    const timePara = `This strategy ONLY runs during ${ctxLabel}. Outside this window the same trigger doesn't have an edge — most likely because liquidity, volatility regime, or the index-rebalance flows that drive the dislocation are concentrated in this part of the day.`;

    content.innerHTML = `
      <div class="modal-head">
        <div>
          <div style="font-size:11px;letter-spacing:.06em;color:#8a93a8;text-transform:uppercase">
            v11 NQ-ES stat-arb · strategy #${s._idx ?? "—"}
          </div>
          <h2 style="margin:4px 0 2px 0">
            <span class="${sCls}">${sideWord}</span> NQ when it ${directionWord} too far from ES
          </h2>
          <div class="muted small" style="font-family:monospace">${s.name}</div>
        </div>
      </div>

      <h4>1. The idea (in plain English)</h4>
      <p>${ideaPara}</p>

      <h4>2. The Z-score trigger</h4>
      <p>${zPara}</p>
      <p>This particular strategy fires when:</p>
      <ul class="trig-list">
        <li>The <strong>${s.z_window}-bar (${minutes} min)</strong> Z-score crosses
          <strong>${s.side === "LONG" ? "below −" + s.z_threshold : "above +" + s.z_threshold}</strong></li>
        <li>The current bar's clock falls inside <strong>${ctxLabel}</strong></li>
      </ul>

      <h4>3. Why this time window?</h4>
      <p>${timePara}</p>

      <h4>4. Entry, stop, target</h4>
      <table class="kv">
        <tr><th>Entry</th><td>The OPEN of the next 5-min bar after the trigger fires (with 2 NQ-pt slippage built in to be realistic).</td></tr>
        <tr><th>Stop loss</th><td><span class="neg">${s.stop_atr} × ATR(14)</span> away from entry.<br>
          ATR ≈ NQ's average 5-min range — if today's ATR is 28pt and stop = 1.5 ATR, stop = 42 pts away.<br>
          Translates to ≈ <strong>$${(s.stop_atr * 28 * 2).toFixed(0)} per MNQ</strong> at typical ATR.</td></tr>
        <tr><th>Profit target</th><td><span class="pos">${s.target_atr} × ATR(14)</span> away from entry.<br>
          So if stop = 42 pts, target ≈ <strong>${(s.target_atr * 28).toFixed(0)} pts</strong>.<br>
          Translates to ≈ <strong>$${(s.target_atr * 28 * 2).toFixed(0)} per MNQ</strong> at typical ATR.</td></tr>
        <tr><th>Risk / Reward</th><td><strong>1 : ${s.rr}</strong></td></tr>
        <tr><th>Max hold</th><td>${s.max_hold_min} minutes — if neither stop nor target hits in this time, the bot exits at market regardless.</td></tr>
      </table>

      <h4>5. Backtest performance <span class="muted small">(out-of-sample, Jan 2024 → Apr 2026)</span></h4>
      <table class="kv">
        <tr><th>Total trades</th><td>${s.n_test}</td></tr>
        <tr><th>Trades per month</th><td>${trades_per_mo}</td></tr>
        <tr><th>Win rate</th><td><strong>${fmtPct(s.wr)}</strong></td></tr>
        <tr><th>Profit factor</th><td><strong>${Number(s.pf).toFixed(2)}</strong> — every $1 lost was offset by $${Number(s.pf).toFixed(2)} won</td></tr>
        <tr><th>Sharpe ratio</th><td>${Number(s.sharpe).toFixed(2)}</td></tr>
        <tr><th>CPCV out-of-sample folds positive</th><td>${s.cpcv}/5 ${s.cpcv >= 3 ? "<span class='pos'>passes</span>" : ""}</td></tr>
        <tr><th>Net P&amp;L @ 1 MNQ over 28 months</th><td>${fmtMoney(s.net_1mnq)}</td></tr>
        <tr><th>Annualized P&amp;L @ 25 MNQ</th><td class="pos"><strong>${fmtMoney(s.yearly_at_25mnq)}</strong></td></tr>
      </table>

      <p class="muted small" style="margin-top:14px">
        Click outside this box or press Escape to close.
      </p>
    `;
  }
  function closeStrategyModal() { $("strat-modal").style.display = "none"; }

  // =====================================================================
  // /api/last_trades — Trades tab (with v11 strategy + Z value)
  // =====================================================================
  async function refreshLast100() {
    try {
      const r = await fetch("/api/last_trades");
      const arr = await r.json();
      paintTradesSummary(arr);
      const ny = (ts) => {
        if (!ts) return "—";
        try {
          const d = new Date(ts);
          return d.toLocaleString("en-US", { timeZone: "America/New_York",
            month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
            hour12: false }).replace(",", " ");
        } catch (e) { return ts.slice(0, 19).replace("T", " "); }
      };
      $("last100-body").innerHTML = arr.map((t) => {
        const pnl = t.pnl ?? 0;
        const cls = pnl > 0 ? "pos" : (pnl < 0 ? "neg" : "");
        const sideCls = "side-" + (t.side || "");
        // ml_confidence was set to historical WR; surface it as "Z value" placeholder
        // (real Z value at fire is in the signal_event log, not the trade row)
        const z = t.ml_confidence ? `WR ${(t.ml_confidence * 100).toFixed(0)}%` : "—";
        return `<tr>
          <td>${ny(t.entry_time)}</td>
          <td><code style="font-size:11px">${(t.signal_name || "").slice(0,55)}</code></td>
          <td class="${sideCls}">${t.side || ""}</td>
          <td>${t.qty ?? "—"}</td>
          <td class="muted small">${z}</td>
          <td>${fmtNum(t.entry_px, 2)}</td>
          <td>${fmtNum(t.stop_px, 2)}</td>
          <td>${fmtNum(t.target_px, 2)}</td>
          <td>${fmtNum(t.exit_px, 2)}</td>
          <td>${t.exit_reason || "—"}</td>
          <td class="${cls}">${pnl ? fmtMoney(pnl) : "—"}</td>
        </tr>`;
      }).join("") || `<tr><td colspan="11" class="muted">No trades yet.</td></tr>`;
    } catch (e) { /* ignore */ }
  }

  function paintTradesSummary(arr) {
    if (!Array.isArray(arr)) arr = [];
    const closed = arr.filter(t => t.exit_time);
    const n = closed.length;
    const wins = closed.filter(t => (t.pnl || 0) > 0).length;
    const losses = closed.filter(t => (t.pnl || 0) < 0).length;
    const totalPnl = closed.reduce((acc, t) => acc + (t.pnl || 0), 0);
    const grossWin = closed.filter(t => (t.pnl||0) > 0).reduce((a, t) => a + t.pnl, 0);
    const grossLoss = -closed.filter(t => (t.pnl||0) < 0).reduce((a, t) => a + t.pnl, 0);
    const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? 999 : 0);
    const wr = n ? wins / n : 0;
    const avgWin = wins ? grossWin / wins : 0;
    const avgLoss = losses ? -grossLoss / losses : 0;
    if ($("trades-count")) $("trades-count").textContent = `${n} total`;
    if ($("trades-stats-pill")) $("trades-stats-pill").textContent = `${wins} wins / ${losses} losses`;
    if ($("ts-total")) $("ts-total").textContent = n;
    if ($("ts-wr")) $("ts-wr").textContent = fmtPct(wr);
    if ($("ts-pf")) $("ts-pf").textContent = pf > 100 ? "—" : Number(pf).toFixed(2);
    if ($("ts-pnl")) {
      const el = $("ts-pnl");
      el.textContent = fmtSigned(totalPnl);
      el.className = "big-number " + (totalPnl > 0 ? "pos" : totalPnl < 0 ? "neg" : "");
    }
    if ($("ts-avg-win")) $("ts-avg-win").textContent = fmtMoney(avgWin);
    if ($("ts-avg-loss")) $("ts-avg-loss").textContent = fmtMoney(-avgLoss);
  }

  // =====================================================================
  // "updated Xs ago"
  // =====================================================================
  function tickAge() {
    if (!lastDataReceivedAt) {
      $("age-label").textContent = "updated —";
      return;
    }
    const sec = Math.floor((Date.now() - lastDataReceivedAt) / 1000);
    $("age-label").textContent = `updated ${sec}s ago`;
  }

  // =====================================================================
  // bootstrap
  // =====================================================================
  function start() {
    refreshData();
    refreshPrice();
    refreshLivePosition();
    refreshV11Brain();
    refreshLast100();
    refreshStrategies();
    refreshCandles();
    refreshTradeMarkers();
    setInterval(refreshData,         15_000);
    setInterval(refreshPrice,         3_000);
    setInterval(refreshLivePosition,  3_000);
    setInterval(refreshV11Brain,     10_000);
    setInterval(refreshLast100,      30_000);
    setInterval(refreshStrategies,  300_000);
    setInterval(refreshCandles,      30_000);
    setInterval(refreshTradeMarkers, 30_000);
    setInterval(tickAge,              1_000);
  }
  function wireModal() {
    const close = $("strat-modal-close");
    const bg = $("strat-modal-bg");
    if (close) close.addEventListener("click", closeStrategyModal);
    if (bg) bg.addEventListener("click", closeStrategyModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeStrategyModal();
    });
    // Brain help collapse toggle (persisted to localStorage)
    const helpCard = document.querySelector(".brain-help");
    if (helpCard) {
      const header = helpCard.querySelector(".card-header");
      if (localStorage.getItem("brainHelpCollapsed") === "1") {
        helpCard.classList.add("collapsed");
      }
      if (header) header.addEventListener("click", () => {
        helpCard.classList.toggle("collapsed");
        localStorage.setItem("brainHelpCollapsed",
          helpCard.classList.contains("collapsed") ? "1" : "0");
      });
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { start(); wireModal(); wireStrategySort(); });
  } else { start(); wireModal(); wireStrategySort(); }
})();
