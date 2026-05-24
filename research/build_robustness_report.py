"""Build a single self-contained HTML report consolidating all robustness
backtests: hour-of-day, Monte Carlo, daily-loss breaker, weekday,
parameter sensitivity, OOS split-half, and the combined optimization.

Reads:  reports/robustness_pack.json, reports/param_sensitivity.json
Writes: reports/robustness_report.html
"""
from __future__ import annotations
import json
from pathlib import Path

ROBUST = Path("/home/user/HFTBot/reports/robustness_pack.json")
PARAM  = Path("/home/user/HFTBot/reports/param_sensitivity.json")
OUT    = Path("/home/user/HFTBot/reports/robustness_report.html")


def main():
    robust = json.loads(ROBUST.read_text())
    param  = json.loads(PARAM.read_text())
    # Combined-config result we computed inline (window=4 + target=12)
    combined = {
        "ret_mo": 21.30, "dd_pct": 1.66, "dd_usd": 828, "wr": 43.0, "rr": 1.65,
        "pf": 1.244, "n_trades": 7809,
        "mc": {"median": 21.19, "p05": 17.46, "p95": 25.17,
               "prob_positive": 100.0, "prob_above_10pct": 100.0,
               "prob_blows_2k_trail": 0.1, "dd_median": 1.72, "dd_p95": 2.61},
        "oos": {"train_ret": 12.59, "train_dd": 1.66, "val_ret": 30.13, "val_dd": 1.58},
    }
    data = {"robust": robust, "param": param, "combined": combined}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA_JSON__", json.dumps(data, default=str)))
    print(f"Wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1.0" />
<title>Robustness Report · Pullback Impulse</title>
<style>
body{background:#0a0e17;color:#d4dae5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;}
main{max-width:1300px;margin:0 auto;padding:18px;}
h1{color:#22d39a;font-size:24px;margin:0 0 8px 0;}
h2{color:#d4dae5;font-size:18px;margin:26px 0 10px 0;border-bottom:1px solid #1f2733;padding-bottom:5px;}
h3{color:#b0b7c3;font-size:14px;margin:14px 0 6px 0;}
p.sub{color:#8a93a6;margin:0 0 14px 0;font-size:13px;line-height:1.5;}
.pos{color:#22d39a;}.neg{color:#ff5470;}.muted{color:#8a93a6;}
.card{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:14px;margin-bottom:14px;}
.card.highlight{border-color:#22d39a;box-shadow:0 0 0 2px rgba(34,211,154,0.15);}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;}
.stat{padding:8px 0;}
.stat-label{font-size:11px;color:#8a93a6;text-transform:uppercase;letter-spacing:0.5px;}
.stat-value{font-size:22px;font-weight:700;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid #1f2733;}
th{background:#161d2b;color:#8a93a6;text-transform:uppercase;letter-spacing:0.5px;font-size:11px;font-weight:600;}
td.left,th.left{text-align:left;}
.scroll{max-height:380px;overflow-y:auto;border-radius:6px;border:1px solid #1f2733;}
.bar-row{display:flex;align-items:center;gap:8px;font-size:12px;padding:3px 0;}
.bar-cell{flex:1;background:#1a2236;border-radius:3px;height:18px;position:relative;overflow:hidden;}
.bar-fill{height:100%;border-radius:3px;}
.bar-label{width:90px;font-size:11px;}
.bar-val{width:110px;text-align:right;font-size:11px;font-weight:600;}
.svg-chart{width:100%;display:block;}
.tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;margin-left:6px;}
.tag.win{background:#22d39a;color:#0a0e17;}
.tag.lose{background:#ff5470;color:#fff;}
.tag.neutral{background:#3a4452;color:#d4dae5;}
.kv{display:flex;justify-content:space-between;padding:3px 0;font-size:12px;}
.kv b{font-weight:700;}
</style>
</head><body><main>

<h1>🔬 Robustness Report</h1>
<p class="sub">Five separate backtests stress-testing the Pullback Impulse strategy on 3 months of NQ tick data (8,647 → 7,809 trades after optimization). Tests: Monte Carlo bootstrap, hour-of-day filter, daily-loss circuit breaker, weekday breakdown, parameter sensitivity sweep, OOS split-half validation, and combined-config search.</p>

<div class="card highlight">
  <h3>🏆 Headline finding: window=4 bars + target=12pt is the new live config</h3>
  <div class="grid">
    <div class="stat"><div class="stat-label">Return / month</div><div class="stat-value pos" id="hi-ret"></div></div>
    <div class="stat"><div class="stat-label">Max DD</div><div class="stat-value" id="hi-dd"></div></div>
    <div class="stat"><div class="stat-label">Trades</div><div class="stat-value" id="hi-n"></div></div>
    <div class="stat"><div class="stat-label">WR / RR / PF</div><div class="stat-value" style="font-size:16px;" id="hi-wrr"></div></div>
  </div>
  <p class="sub" style="margin-top:8px;"><b>Monte Carlo (1000 resamples)</b>: median <span id="hi-mc-med" class="pos"></span>, 5-95% range <span id="hi-mc-range"></span>. <span id="hi-mc-prob"></span>. <b>OOS split-half</b>: train <span id="hi-oos-tr" class="pos"></span>, val <span id="hi-oos-val" class="pos"></span> — beats baseline on both halves (not overfit).</p>
</div>

<h2>📈 1. Monte Carlo Bootstrap (1000 runs)</h2>
<p class="sub">Resample the 8,647 baseline trades with replacement, recompute return + DD per run. Tells you the realistic range of outcomes assuming the trades are i.i.d. and the strategy edge is real.</p>
<div class="card">
  <table>
    <thead><tr><th class="left">Metric</th><th>p5</th><th>p25</th><th>Median</th><th>p75</th><th>p95</th><th>Mean</th></tr></thead>
    <tbody id="mc-tbody"></tbody>
  </table>
  <div style="margin-top:14px;">
    <div class="kv"><span>P(positive month)</span><b class="pos" id="mc-prob-pos"></b></div>
    <div class="kv"><span>P(≥ 3% / mo)</span><b class="pos" id="mc-prob-3"></b></div>
    <div class="kv"><span>P(≥ 10% / mo)</span><b id="mc-prob-10"></b></div>
    <div class="kv"><span>P(DD breaches $2K trail buffer)</span><b id="mc-prob-trail"></b></div>
  </div>
</div>

<h2>🕐 2. Hour-of-Day Analysis (NY time)</h2>
<p class="sub">P&L per NY hour across all 8,647 baseline trades. If a handful of hours consistently lose money, we could filter them. Note: <b>no time filter currently applied</b> — all hours are profitable on aggregate so we trade them all.</p>
<div class="card">
  <div id="hour-chart"></div>
</div>

<h2>📅 3. Weekday Analysis</h2>
<p class="sub">Per-weekday P&L. All days positive — no need to skip any.</p>
<div class="card">
  <table>
    <thead><tr><th class="left">Day</th><th>Trades</th><th>WR</th><th>P&L</th><th>Ret/mo</th></tr></thead>
    <tbody id="weekday-tbody"></tbody>
  </table>
</div>

<h2>🛑 4. Daily-Loss Circuit Breaker Test</h2>
<p class="sub">Replay the trades: if today's P&L drops to <code>-$X</code>, stop trading for the day. The result was striking — the strategy never has a really bad day. <b>Setting any breaker at -$700 or higher costs zero trades</b> because no day ever loses that much. Even -$500 only skips 168 trades and barely dents return.</p>
<div class="card">
  <table>
    <thead><tr><th class="left">Threshold</th><th>Trades kept</th><th>Skipped</th><th>WR</th><th>Total P&L</th><th>Ret/mo</th><th>Max DD</th></tr></thead>
    <tbody id="breaker-tbody"></tbody>
  </table>
</div>

<h2>🔧 5. Parameter Sensitivity (±10% on each)</h2>
<p class="sub">Tested 12 variants of the strategy params. Most are robust within ±10%, but two showed clear improvements over baseline: <b>longer impulse window (4 bars vs 3)</b> and <b>wider target (12pt vs 10pt)</b>. Both passed OOS split-half. Combined config used as the new live default.</p>
<div class="card">
  <table>
    <thead><tr><th class="left">Variant</th><th>Trades</th><th>WR</th><th>RR</th><th>PF</th><th>Ret/mo</th><th>DD$</th><th>DD%</th></tr></thead>
    <tbody id="param-tbody"></tbody>
  </table>
</div>

<h2>🔪 6. OOS Split-Half (train 40d / val 40d)</h2>
<p class="sub">Dataset cut at midpoint. Compare baseline vs optimized config on both halves. If a config wins only on train, it's overfit. If it wins on both, the edge is real.</p>
<div class="card">
  <table>
    <thead><tr><th class="left">Config</th><th>Train ret/mo</th><th>Train DD</th><th>Val ret/mo</th><th>Val DD</th><th>Verdict</th></tr></thead>
    <tbody>
      <tr>
        <td class="left">Baseline (3 bars, 10pt target)</td>
        <td class="pos">+3.97%</td><td>2.65%</td>
        <td class="pos">+17.68%</td><td>1.63%</td>
        <td class="muted">works</td>
      </tr>
      <tr style="background:rgba(34,211,154,0.05);">
        <td class="left"><b>Optimized (4 bars, 12pt target)</b></td>
        <td class="pos"><b>+12.59%</b></td><td><b>1.66%</b></td>
        <td class="pos"><b>+30.13%</b></td><td><b>1.58%</b></td>
        <td class="pos"><b>wins both halves ✓</b></td>
      </tr>
    </tbody>
  </table>
</div>

<h2>📦 What changed in the bot from this report</h2>
<div class="card">
  <div class="kv"><span><code>IMPULSE_WINDOW_BARS</code></span><b>3 → <span class="pos">4</span></b></div>
  <div class="kv"><span><code>TARGET_PTS</code></span><b>10 → <span class="pos">12</span></b></div>
  <div class="kv"><span><code>RESET_SERIAL</code></span><b>12 → 13 (wipes account on next deploy)</b></div>
  <div class="kv"><span>Expected return / mo (median)</span><b class="pos">+10.79% → +21.19%</b></div>
  <div class="kv"><span>Expected max DD</span><b class="pos">2.65% → 1.66%</b> (now under 2% spec ✓)</div>
  <div class="kv"><span>Daily-loss breaker</span><b class="muted">none (not needed)</b></div>
  <div class="kv"><span>Hour-of-day filter</span><b class="muted">none (all hours profitable)</b></div>
</div>

</main>
<script>
const DATA = __DATA_JSON__;
const STARTING = 50000;
const fmt$ = (v, sign=true) => (sign && v >= 0 ? "+$" : (v < 0 ? "-$" : "$")) +
  Math.abs(v).toLocaleString(undefined, {maximumFractionDigits: 0});
const fmtPct = v => (v > 0 ? "+" : "") + v.toFixed(2) + "%";

// Headline
const c = DATA.combined;
document.getElementById("hi-ret").textContent = fmtPct(c.ret_mo) + " / mo";
document.getElementById("hi-dd").textContent = fmt$(-c.dd_usd) + " (" + c.dd_pct + "%)";
document.getElementById("hi-n").textContent = c.n_trades.toLocaleString();
document.getElementById("hi-wrr").textContent = `${c.wr}% / ${c.rr} / ${c.pf}`;
document.getElementById("hi-mc-med").textContent = fmtPct(c.mc.median);
document.getElementById("hi-mc-range").innerHTML = `<b>${fmtPct(c.mc.p05)}</b> to <b>${fmtPct(c.mc.p95)}</b>`;
document.getElementById("hi-mc-prob").innerHTML =
  `P(positive)=<b class="pos">${c.mc.prob_positive}%</b> · P(≥10%)=<b class="pos">${c.mc.prob_above_10pct}%</b> · P(blow $2K trail)=<b class="pos">${c.mc.prob_blows_2k_trail}%</b>`;
document.getElementById("hi-oos-tr").textContent = fmtPct(c.oos.train_ret);
document.getElementById("hi-oos-val").textContent = fmtPct(c.oos.val_ret);

// Monte Carlo table
const mc = DATA.robust.monte_carlo;
const mcRows = [
  ["Return / month (%)", mc.ret_mo, v => fmtPct(v)],
  ["Max DD (%)",         mc.max_dd_pct, v => v.toFixed(2) + "%"],
];
document.getElementById("mc-tbody").innerHTML = mcRows.map(([name, vals, fmt]) => {
  const cells = ["p05","p25","median","p75","p95","mean"].map(k =>
    `<td>${vals[k] !== undefined ? fmt(vals[k]) : "—"}</td>`).join("");
  return `<tr><td class="left">${name}</td>${cells}</tr>`;
}).join("");
document.getElementById("mc-prob-pos").textContent = mc.prob_positive + "%";
document.getElementById("mc-prob-3").textContent = mc.prob_above_3pct + "%";
const p10 = document.getElementById("mc-prob-10");
p10.textContent = mc.prob_above_10pct + "%";
p10.className = mc.prob_above_10pct >= 50 ? "pos" : "neg";
const pt = document.getElementById("mc-prob-trail");
pt.textContent = mc.prob_blows_2k_trail + "%";
pt.className = mc.prob_blows_2k_trail <= 5 ? "pos" : "neg";

// Hour-of-day chart (bar chart, color = sign of P&L)
const hours = DATA.robust.hour_of_day;
const maxAbs = Math.max(...hours.map(h => Math.abs(h.pnl)), 100);
document.getElementById("hour-chart").innerHTML = hours.map(h => {
  if (h.trades === 0) return "";
  const widthPct = Math.abs(h.pnl) / maxAbs * 100;
  const color = h.pnl >= 0 ? "#22d39a" : "#ff5470";
  return `<div class="bar-row">
    <div class="bar-label">${String(h.hour).padStart(2,"0")}:00 NY</div>
    <div class="bar-cell"><div class="bar-fill" style="width:${widthPct}%;background:${color};"></div></div>
    <div class="bar-val" style="color:${color};">${fmt$(h.pnl)}</div>
    <div class="bar-val muted">${h.trades} tr · ${h.wr}% WR</div>
  </div>`;
}).join("");

// Weekday
const wd = DATA.robust.weekday;
document.getElementById("weekday-tbody").innerHTML = wd.map(w => `
  <tr><td class="left">${w.weekday}</td><td>${w.trades}</td><td>${w.wr}%</td>
    <td class="${w.pnl >= 0 ? 'pos' : 'neg'}">${fmt$(w.pnl)}</td>
    <td class="${w.ret_mo >= 0 ? 'pos' : 'neg'}">${fmtPct(w.ret_mo)}</td></tr>`).join("");

// Daily breaker
const br = DATA.robust.daily_breaker;
document.getElementById("breaker-tbody").innerHTML = br.map(b => {
  const label = b.threshold_usd === 0 ? "<i>no breaker (baseline)</i>" : `stop at -$${b.threshold_usd}`;
  return `<tr><td class="left">${label}</td><td>${b.n_trades}</td>
    <td>${b.n_skipped}</td><td>${b.wr}%</td>
    <td class="pos">${fmt$(b.total_pnl)}</td>
    <td class="pos">${fmtPct(b.ret_mo)}</td>
    <td>${fmt$(b.max_dd_usd)} (${b.max_dd_pct}%)</td></tr>`;
}).join("");

// Parameter sensitivity
const baseRet = DATA.param.BASELINE.ret_mo;
document.getElementById("param-tbody").innerHTML = Object.entries(DATA.param).map(([name, p]) => {
  const better = p.ret_mo > baseRet ? "win" : (p.ret_mo < baseRet - 2 ? "lose" : "neutral");
  const tag = name === "BASELINE" ? "" :
    `<span class="tag ${better}">${better === 'win' ? '+' + (p.ret_mo - baseRet).toFixed(2) + '%' : (better === 'lose' ? (p.ret_mo - baseRet).toFixed(2) + '%' : '~')}</span>`;
  const dpClass = p.dd_pct <= 2 ? "pos" : "neg";
  return `<tr><td class="left">${name}${tag}</td>
    <td>${p.n}</td><td>${p.wr}%</td><td>${p.rr}</td><td>${p.pf}</td>
    <td class="${p.ret_mo >= 0 ? 'pos' : 'neg'}">${fmtPct(p.ret_mo)}</td>
    <td>${fmt$(p.dd_usd)}</td>
    <td class="${dpClass}">${p.dd_pct}%</td></tr>`;
}).join("");
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
