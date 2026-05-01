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
    // The chart needs a relayout when its container becomes visible
    if (name === "chart" && window.Plotly && document.getElementById("live-chart").data) {
      try { Plotly.Plots.resize("live-chart"); } catch (e) {}
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

  // ---- /api/freshness — chart staleness pill -----------------------
  async function refreshFreshness() {
    try {
      const r = await fetch("/api/freshness");
      const f = await r.json();
      const pill = $("freshness-pill");
      if (f.age_seconds == null) { pill.textContent = "no data"; pill.className = "pill bad"; return; }
      const min = Math.round(f.age_seconds / 60);
      let label, cls;
      if (min <= 6)     { label = `live (${min} min ago)`;    cls = "pill pos"; }
      else if (min <= 20) { label = `delayed ${min} min`;     cls = "pill"; }
      else              { label = `stale ${min} min`;          cls = "pill bad"; }
      label += ` • ${f.source || ""}`;
      pill.textContent = label;
      pill.className = cls;
    } catch (e) { /* ignore */ }
  }

  // ---- /api/live_chart — Plotly figure ------------------------------
  async function refreshLiveChart() {
    const el = $("live-chart");
    if (!window.Plotly) {
      el.innerHTML = `<div style="color:#ef5350">Plotly failed to load — check network</div>`;
      return;
    }
    try {
      const r = await fetch("/api/live_chart");
      const fig = await r.json();
      if (fig.error) {
        el.innerHTML = `<div style="text-align:center;padding:30px">
          <div style="color:#ef5350;font-weight:600;margin-bottom:6px">${fig.error}</div>
          <div style="color:#787b86;font-size:11px">${fig.detail || ""}</div>
          <div style="color:#787b86;font-size:11px;margin-top:8px">
            (yfinance / CNBC are blocked or returning empty — chart will populate
            once a feed comes back online)
          </div></div>`;
        return;
      }
      // Reset the placeholder styles before Plotly takes over
      el.style.display = "block"; el.style.alignItems = ""; el.style.justifyContent = "";
      el.style.color = ""; el.style.fontSize = "";
      Plotly.react("live-chart", fig.data, fig.layout, {
        responsive: true, scrollZoom: true,
        modeBarButtonsToRemove: ["select2d", "lasso2d"],
        displaylogo: false,
      });
    } catch (e) {
      el.innerHTML = `<div style="color:#ef5350;padding:30px">chart fetch failed: ${e}</div>`;
    }
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
    refreshFreshness();
    refreshLiveChart();
    refreshBrain();
    refreshLast100();
    setInterval(refreshData,         15_000);
    setInterval(refreshLivePosition,  3_000);
    setInterval(refreshFreshness,    30_000);
    setInterval(refreshLiveChart,    60_000);
    setInterval(refreshBrain,        15_000);
    setInterval(refreshLast100,      30_000);
    setInterval(tickAge,              1_000);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else { start(); }
})();
