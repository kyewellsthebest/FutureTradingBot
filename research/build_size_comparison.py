"""Run ultra-real sim at 5 different fixed MNQ sizes and build a comparison
HTML report. Per-trade $ scales linearly with size, so the relative
return is just multiplied — but max DD also scales linearly, so the
Calmar ratio stays the same.

The interesting question: which size hits the spec (especially the 2% DD)
while delivering the most return?
"""
from __future__ import annotations
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, "/home/user/HFTBot")

from bot.pullback_strategy import (
    detect_pullback_setup, _setup_key,
    MIN_TARGET_HOLD_SECONDS, COOLDOWN_SECS,
    MAX_HOLD_SECS, MAX_WAIT_SECS,
    IMPULSE_PTS, IMPULSE_WINDOW_BARS, PULLBACK_PCT,
    STOP_PTS, TARGET_PTS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_HTML = Path("/home/user/HFTBot/reports/size_comparison.html")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 1.0
LATENCY_MS = 200
SIZES_TO_TEST = [1, 2, 3, 4, 5]


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_sim(price, ts_ns, bars_1m, size):
    """Run simulation at a fixed MNQ size. Returns list of trades."""
    bar_ts = bars_1m.index.astype("int64").to_numpy()
    cooldown_ns = COOLDOWN_SECS * 1_000_000_000
    latency_ns = LATENCY_MS * 1_000_000
    max_hold_ns = MAX_HOLD_SECS * 1_000_000_000
    max_wait_ns = MAX_WAIT_SECS * 1_000_000_000
    min_hold_ns = MIN_TARGET_HOLD_SECONDS * 1_000_000_000

    trades = []
    used_keys = set()
    last_exit_ts = -1

    for i in range(3, len(bars_1m) - 1):
        sig_ts = int(bar_ts[i + 1])
        bars_at_i = bars_1m.iloc[:i + 1]
        setup = detect_pullback_setup(bars_at_i,
            pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
        if setup is None: continue
        key = _setup_key(setup)
        if key in used_keys: continue
        if last_exit_ts > 0 and sig_ts - last_exit_ts < cooldown_ns: continue
        side = 1 if setup.side == "LONG" else -1
        entry_price = float(setup.pullback_entry)
        stop_px = float(setup.stop_px_val)
        target_px = float(setup.target_px_val)
        fill_start = int(np.searchsorted(ts_ns, sig_ts + latency_ns, side="left"))
        fill_end = int(np.searchsorted(ts_ns, sig_ts + max_wait_ns, side="left"))
        if fill_start >= fill_end: continue
        scan_fill = price[fill_start:fill_end]
        hits = scan_fill <= entry_price if side == 1 else scan_fill >= entry_price
        if not hits.any(): continue
        entry_idx = fill_start + int(np.argmax(hits))
        entry_ts = int(ts_ns[entry_idx])
        timeout_ts = entry_ts + max_hold_ns
        min_target_ts = entry_ts + min_hold_ns
        exit_end = min(int(np.searchsorted(ts_ns, timeout_ts, side="left")), len(price) - 1)
        if exit_end <= entry_idx: continue
        scan_p = price[entry_idx + 1:exit_end + 1]
        scan_t = ts_ns[entry_idx + 1:exit_end + 1]
        if side == 1:
            stop_mask = scan_p <= stop_px; tgt_mask = scan_p >= target_px
        else:
            stop_mask = scan_p >= stop_px; tgt_mask = scan_p <= target_px
        stop_idx = int(np.argmax(stop_mask)) if stop_mask.any() else len(scan_p)
        if tgt_mask.any():
            cand = np.where(tgt_mask & (scan_t >= min_target_ts))[0]
            tgt_idx = int(cand[0]) if len(cand) > 0 else len(scan_p)
        else:
            tgt_idx = len(scan_p)
        if stop_idx == len(scan_p) and tgt_idx == len(scan_p):
            exit_px = float(scan_p[-1]); exit_ts = int(scan_t[-1]); reason = "timeout"
        elif stop_idx <= tgt_idx:
            exit_px = stop_px; exit_ts = int(scan_t[stop_idx]); reason = "stop"
        else:
            exit_px = target_px; exit_ts = int(scan_t[tgt_idx]); reason = "target"
        pnl_pts = (exit_px - entry_price) if side == 1 else (entry_price - exit_px)
        pnl_usd = pnl_pts * size * MNQ_PER_PT - COMM_PER_CONTRACT_RT * size
        trades.append({
            "side": setup.side, "size": size,
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "entry_px": round(float(entry_price), 2),
            "exit_px": round(float(exit_px), 2),
            "hold_s": round((exit_ts - entry_ts) / 1e9, 2),
            "exit_reason": reason,
            "pnl_usd": round(float(pnl_usd), 2),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts
    return trades


def summarize(trades, period_days, starting_bal=STARTING_BALANCE):
    n = len(trades)
    if n == 0: return None
    pnls = np.array([t["pnl_usd"] for t in trades])
    wins = int((pnls > 0).sum())
    losses = int((pnls < 0).sum())
    gw = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    pf = gw / gl if gl > 0 else 999
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(pnls[pnls > 0].mean()) if wins else 0
    avg_l = float(pnls[pnls < 0].mean()) if losses else 0
    max_streak = streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44
    total = float(pnls.sum())
    annual = total / starting_bal * 100 * (12 / months)
    return {
        "n_trades": n, "wins": wins, "losses": losses,
        "wr_pct": round(wins/n*100, 2),
        "pf": round(pf, 3) if pf < 99 else None,
        "rr": round(abs(avg_w/avg_l) if avg_l else 0, 2),
        "avg_win": round(avg_w, 2),
        "avg_loss": round(avg_l, 2),
        "total_pnl": round(total, 2),
        "return_pct": round(total/starting_bal*100, 2),
        "return_pct_per_mo": round(total/starting_bal*100/months, 2),
        "annualized_pct": round(annual, 1),
        "max_dd_usd": round(maxdd, 2),
        "max_dd_pct": round(abs(maxdd/starting_bal*100), 2),
        "calmar": round(annual / abs(maxdd/starting_bal*100), 2) if maxdd != 0 else 0,
        "max_losing_streak": int(max_streak),
        "trades_per_day": round(n/period_days, 1),
        "trades_per_month": round(n/months, 1),
    }


def hits_spec(s):
    return (s["wr_pct"] >= 55 and s["rr"] >= 1.2 and s["trades_per_month"] >= 100
            and s["return_pct_per_mo"] >= 3.0 and s["max_dd_pct"] <= 2.0)


def main():
    t0 = time.time()
    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
    print(f"  {len(price):,} ticks, {len(bars_1m):,} bars ({time.time()-t0:.0f}s)")

    # The simulation logic is identical regardless of size — same trade
    # decisions, just different $ per trade. So we run ONCE at size=1
    # and scale the P&L for each tested size. Commissions also scale
    # linearly so the math is exact: pnl_usd(size=N) = N * pnl_usd(size=1).
    print("\nRunning sim once at size=1...")
    base_trades = run_sim(price, ts_ns, bars_1m, size=1)
    print(f"  {len(base_trades)} trades in {time.time()-t0:.0f}s")

    # Build per-size results
    results = {}
    daily_per_size = {}
    equity_per_size = {}
    weekly_per_size = {}
    for size in SIZES_TO_TEST:
        scaled = []
        for t in base_trades:
            t2 = dict(t)
            t2["size"] = size
            t2["pnl_usd"] = round(t["pnl_usd"] * size, 2)
            scaled.append(t2)
        s = summarize(scaled, period_days)
        results[size] = s
        # daily breakdown
        tdf = pd.DataFrame(scaled)
        tdf["entry_dt"] = pd.to_datetime(tdf["entry_ts"], utc=True)
        tdf["date"] = tdf["entry_dt"].dt.tz_convert("America/New_York").dt.date.astype(str)
        tdf["week"] = tdf["entry_dt"].dt.to_period("W-MON").astype(str)
        daily = tdf.groupby("date").agg(trades=("pnl_usd", "size"),
            wins=("pnl_usd", lambda x: int((x > 0).sum())),
            pnl=("pnl_usd", "sum")).reset_index()
        daily["cum_pnl"] = daily["pnl"].cumsum()
        daily_per_size[size] = daily.to_dict(orient="records")
        weekly = tdf.groupby("week").agg(trades=("pnl_usd", "size"),
            wins=("pnl_usd", lambda x: int((x > 0).sum())),
            pnl=("pnl_usd", "sum")).reset_index()
        weekly["wr"] = weekly["wins"] / weekly["trades"] * 100
        weekly_per_size[size] = weekly.to_dict(orient="records")
        bal = STARTING_BALANCE
        ec = []
        for t in scaled:
            bal += t["pnl_usd"]
            ec.append(round(bal, 2))
        equity_per_size[size] = ec

    print("\nResults:")
    for size in SIZES_TO_TEST:
        s = results[size]
        spec = " HITS SPEC" if hits_spec(s) else ""
        print(f"  {size} MNQ: ret={s['return_pct_per_mo']:+.2f}%/mo  "
              f"DD={s['max_dd_pct']:.2f}%  Calmar={s['calmar']:.2f}{spec}")

    # ========================================================================
    # Build HTML report
    # ========================================================================
    data = {
        "meta": {
            "period_start": str(pd.to_datetime(base_trades[0]["entry_ts"], utc=True)),
            "period_end": str(pd.to_datetime(base_trades[-1]["exit_ts"], utc=True)),
            "period_days": round(period_days, 1),
            "period_months": round(period_days / 30.44, 2),
            "starting_balance": STARTING_BALANCE,
            "n_trades": len(base_trades),
            "impulse_pts": IMPULSE_PTS, "impulse_window_bars": IMPULSE_WINDOW_BARS,
            "pullback_pct": PULLBACK_PCT, "stop_pts": STOP_PTS, "target_pts": TARGET_PTS,
            "max_hold_secs": MAX_HOLD_SECS, "min_target_hold_secs": MIN_TARGET_HOLD_SECONDS,
            "cooldown_secs": COOLDOWN_SECS,
            "latency_ms": LATENCY_MS, "comm_per_contract": COMM_PER_CONTRACT_RT,
        },
        "sizes": SIZES_TO_TEST,
        "results": {str(k): v for k, v in results.items()},
        "daily": {str(k): v for k, v in daily_per_size.items()},
        "weekly": {str(k): v for k, v in weekly_per_size.items()},
        "equity": {str(k): v for k, v in equity_per_size.items()},
    }
    html = HTML_TEMPLATE.replace("__DATA_JSON__", json.dumps(data, default=str))
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html)
    print(f"\nWrote {OUT_HTML} ({OUT_HTML.stat().st_size/1e6:.2f} MB)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Position Size Comparison · Pullback Impulse</title>
<style>
body{background:#0a0e17;color:#d4dae5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;}
main{max-width:1300px;margin:0 auto;padding:16px;}
h1{color:#22d39a;margin:0 0 8px 0;font-size:24px;}
h2{color:#d4dae5;margin:24px 0 10px 0;font-size:18px;border-bottom:1px solid #1f2733;padding-bottom:4px;}
p.sub{color:#8a93a6;margin:0 0 14px 0;font-size:13px;}
.pos{color:#22d39a;}.neg{color:#ff5470;}
.meta{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:12px 16px;font-size:12px;color:#b0b7c3;margin-bottom:16px;}
.meta div{padding:2px 0;}.meta b{color:#d4dae5;}
.size-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0;}
.size-card{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:14px;}
.size-card.best{border-color:#22d39a;box-shadow:0 0 0 2px rgba(34,211,154,0.2);}
.size-card.spec-fail{border-color:#ff5470;}
.size-title{font-size:18px;font-weight:700;margin-bottom:8px;}
.size-row{display:flex;justify-content:space-between;padding:3px 0;font-size:12px;}
.size-row b{font-weight:700;}
.spec-badge{font-size:11px;padding:2px 8px;border-radius:4px;display:inline-block;margin-top:6px;}
.spec-badge.pass{background:#22d39a;color:#0a0e17;}
.spec-badge.fail{background:#3a4452;color:#8a93a6;}
table.rep{width:100%;border-collapse:collapse;font-size:12px;background:#0f1422;}
table.rep th,table.rep td{padding:8px 10px;text-align:right;border-bottom:1px solid #1f2733;}
table.rep th{background:#161d2b;color:#8a93a6;text-transform:uppercase;letter-spacing:0.5px;font-size:11px;font-weight:600;position:sticky;top:0;}
table.rep td.left{text-align:left;}
.scroll{max-height:450px;overflow-y:auto;border-radius:8px;border:1px solid #1f2733;}
.chart-block{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:14px;margin-bottom:14px;}
.chart-title{color:#d4dae5;font-size:13px;font-weight:600;margin-bottom:10px;}
.svg-chart{width:100%;height:300px;display:block;}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:6px;font-size:12px;}
.legend-item{display:flex;align-items:center;gap:6px;color:#b0b7c3;}
.legend-swatch{width:14px;height:3px;border-radius:2px;}
.size-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;}
.size-tab{background:#1f2733;color:#d4dae5;border:1px solid #2a3441;padding:8px 14px;border-radius:6px;cursor:pointer;}
.size-tab.active{background:#22d39a;color:#0a0e17;border-color:#22d39a;font-weight:700;}
</style>
</head>
<body>
<main>
<h1>📐 Position Size Comparison</h1>
<p class="sub">Same Pullback Impulse strategy, varying fixed MNQ size from 1 to 5. The strategy makes identical trade decisions at every size — only the $ per trade and DD scale linearly. Question: which size delivers the best return without blowing the spec?</p>
<div class="meta" id="meta"></div>

<h2>📈 Side-by-Side</h2>
<div class="size-grid" id="size-grid"></div>

<h2>📊 Comparison Table</h2>
<div class="scroll"><table class="rep">
  <thead><tr><th class="left">Metric</th><th>1 MNQ</th><th>2 MNQ</th><th>3 MNQ</th><th>4 MNQ</th><th>5 MNQ</th></tr></thead>
  <tbody id="compare-tbody"></tbody>
</table></div>

<h2>🎯 Spec Pass/Fail by Size</h2>
<div class="scroll"><table class="rep">
  <thead><tr><th class="left">Spec</th><th>Target</th><th>1 MNQ</th><th>2 MNQ</th><th>3 MNQ</th><th>4 MNQ</th><th>5 MNQ</th></tr></thead>
  <tbody id="spec-tbody"></tbody>
</table></div>

<div class="chart-block">
  <div class="chart-title">All 5 Equity Curves Overlaid</div>
  <div id="chart-equity"></div>
  <div class="legend" id="eq-legend"></div>
</div>

<div class="chart-block">
  <div class="chart-title">Max Drawdown by Size</div>
  <div id="chart-dd"></div>
</div>

<div class="chart-block">
  <div class="chart-title">Return / DD (Calmar Ratio) by Size</div>
  <div id="chart-calmar"></div>
</div>

<h2>📅 Per-Week P&L (select size)</h2>
<div class="size-tabs" id="weekly-tabs"></div>
<div class="scroll"><table class="rep"><thead><tr><th class="left">Week</th><th>Trades</th><th>Wins</th><th>WR</th><th>P&L</th><th>Return %</th></tr></thead><tbody id="weekly-tbody"></tbody></table></div>

<h2>📆 Per-Day P&L (select size)</h2>
<div class="size-tabs" id="daily-tabs"></div>
<div class="scroll"><table class="rep"><thead><tr><th class="left">Date</th><th>Trades</th><th>Wins</th><th>WR</th><th>Day P&L</th><th>Running P&L</th></tr></thead><tbody id="daily-tbody"></tbody></table></div>

</main>

<script>
const DATA = __DATA_JSON__;
const STARTING_BAL = 50000;
const SIZE_COLORS = {1:"#22d39a", 2:"#4dd4ff", 3:"#ffd54d", 4:"#ff8c4a", 5:"#ff5470"};
const SIZES = DATA.sizes;

function fmtMoney(v, sign=true){const s=sign&&v>0?"+":(v<0?"-":"");return s+"$"+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});}
function fmtPct(v){return (v>0?"+":"")+v.toFixed(2)+"%";}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function hitsSpec(s){return s.wr_pct>=55 && s.rr>=1.2 && s.trades_per_month>=100 && s.return_pct_per_mo>=3 && s.max_dd_pct<=2;}

// META
const m = DATA.meta;
document.getElementById("meta").innerHTML = `
  <div><b>Period:</b> ${m.period_start.slice(0,10)} → ${m.period_end.slice(0,10)} (${m.period_days} days, ${m.period_months} months)</div>
  <div><b>Trades simulated:</b> ${m.n_trades.toLocaleString()} (same trade decisions at every size)</div>
  <div><b>Strategy:</b> impulse=${m.impulse_pts}pt over ${m.impulse_window_bars}b · pullback=${m.pullback_pct} · stop=${m.stop_pts}p · target=${m.target_pts}p</div>
  <div><b>Min target hold:</b> ${m.min_target_hold_secs}s · <b>Cooldown:</b> ${m.cooldown_secs}s · <b>Max hold:</b> ${m.max_hold_secs}s</div>
  <div><b>Execution:</b> ${m.latency_ms}ms latency, $${m.comm_per_contract}/contract round-trip</div>
`;

// Per-size summary cards
let bestSize = null, bestRet = -1e9;
SIZES.forEach(sz => {
  const r = DATA.results[sz];
  if (hitsSpec(r) && r.return_pct_per_mo > bestRet) { bestRet = r.return_pct_per_mo; bestSize = sz; }
});

const sgEl = document.getElementById("size-grid");
sgEl.innerHTML = SIZES.map(sz => {
  const r = DATA.results[sz];
  const isBest = sz === bestSize;
  const specPass = hitsSpec(r);
  const cls = isBest ? "best" : (specPass ? "" : "spec-fail");
  return `<div class="size-card ${cls}">
    <div class="size-title" style="color:${SIZE_COLORS[sz]};">${sz} MNQ${isBest ? " 🏆" : ""}</div>
    <div class="size-row"><span>Return/mo</span><b class="${r.return_pct_per_mo>=0?"pos":"neg"}">${fmtPct(r.return_pct_per_mo)}</b></div>
    <div class="size-row"><span>Total P&L</span><b class="${r.total_pnl>=0?"pos":"neg"}">${fmtMoney(r.total_pnl)}</b></div>
    <div class="size-row"><span>Max DD</span><b class="neg">${fmtMoney(r.max_dd_usd)}</b></div>
    <div class="size-row"><span>Max DD %</span><b class="${r.max_dd_pct<=2?"pos":"neg"}">${r.max_dd_pct}%</b></div>
    <div class="size-row"><span>Calmar</span><b>${r.calmar}</b></div>
    <div class="size-row"><span>Annualized</span><b class="${r.annualized_pct>=0?"pos":"neg"}">${fmtPct(r.annualized_pct)}</b></div>
    <div class="size-row"><span>Avg win / loss</span><b>+$${r.avg_win.toFixed(0)} / -$${Math.abs(r.avg_loss).toFixed(0)}</b></div>
    <div class="size-row"><span>WR / RR</span><b>${r.wr_pct}% / ${r.rr}</b></div>
    <div class="size-row"><span>Trades/mo</span><b>${r.trades_per_month}</b></div>
    <div class="size-row"><span>Max streak</span><b>${r.max_losing_streak}</b></div>
    <span class="spec-badge ${specPass?"pass":"fail"}">${specPass?"✓ Hits spec":"✗ Fails spec"}</span>
  </div>`;
}).join("");

// Comparison table
const metrics = [
  ["Return/mo (%)", "return_pct_per_mo", v=>fmtPct(v)],
  ["Total P&L ($)", "total_pnl", v=>fmtMoney(v)],
  ["Annualized (%)", "annualized_pct", v=>fmtPct(v)],
  ["Max DD ($)", "max_dd_usd", v=>fmtMoney(v)],
  ["Max DD (%)", "max_dd_pct", v=>v+"%"],
  ["Calmar ratio", "calmar", v=>v.toFixed(2)],
  ["Avg win ($)", "avg_win", v=>"+$"+v.toFixed(2)],
  ["Avg loss ($)", "avg_loss", v=>"-$"+Math.abs(v).toFixed(2)],
  ["Win rate (%)", "wr_pct", v=>v+"%"],
  ["Profit factor", "pf", v=>v?v.toFixed(2):"∞"],
  ["RR (actual)", "rr", v=>v.toFixed(2)],
  ["Trades/month", "trades_per_month", v=>v.toFixed(0)],
  ["Trades/day", "trades_per_day", v=>v.toFixed(1)],
  ["Max losing streak", "max_losing_streak", v=>v.toString()],
];
document.getElementById("compare-tbody").innerHTML = metrics.map(([label, key, fmt]) => {
  const cells = SIZES.map(sz => {
    const v = DATA.results[sz][key];
    const cls = (key === "return_pct_per_mo" || key === "total_pnl" || key === "annualized_pct")
      ? (v >= 0 ? "pos" : "neg") : (key === "max_dd_pct" ? (v <= 2 ? "pos" : "neg") : "");
    return `<td class="${cls}">${v !== null && v !== undefined ? fmt(v) : "—"}</td>`;
  }).join("");
  return `<tr><td class="left">${label}</td>${cells}</tr>`;
}).join("");

// Spec table
const specs = [
  ["WR ≥ 55%", "≥55%", s => s.wr_pct, v => v + "%", v => v >= 55],
  ["RR ≥ 1.2", "≥1.2", s => s.rr, v => v.toFixed(2), v => v >= 1.2],
  ["Trades/mo ≥ 100", "≥100", s => s.trades_per_month, v => v.toFixed(0), v => v >= 100],
  ["Return ≥ 3%/mo", "≥3%", s => s.return_pct_per_mo, v => fmtPct(v), v => v >= 3],
  ["Max DD ≤ 2%", "≤2%", s => s.max_dd_pct, v => v + "%", v => v <= 2],
];
document.getElementById("spec-tbody").innerHTML = specs.map(([n, t, getter, fmt, pass]) => {
  const cells = SIZES.map(sz => {
    const v = getter(DATA.results[sz]);
    const p = pass(v);
    return `<td class="${p?"pos":"neg"}">${fmt(v)} ${p?"✓":"✗"}</td>`;
  }).join("");
  return `<tr><td class="left">${n}</td><td>${t}</td>${cells}</tr>`;
}).join("");

// ============ SVG charts ============
function svgMultiLine(containerId, seriesMap, opts={}) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const W = el.clientWidth || 800;
  const H = opts.height || 300;
  const padL = 60, padR = 10, padT = 10, padB = 24;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  // global min/max across all series
  let minY = Infinity, maxY = -Infinity, maxLen = 0;
  Object.values(seriesMap).forEach(arr => {
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] < minY) minY = arr[i];
      if (arr[i] > maxY) maxY = arr[i];
    }
    if (arr.length > maxLen) maxLen = arr.length;
  });
  const rangeY = (maxY - minY) || 1;
  const stepX = maxLen > 1 ? innerW / (maxLen - 1) : 0;
  let paths = "";
  Object.entries(seriesMap).forEach(([name, arr]) => {
    let p = "";
    for (let i = 0; i < arr.length; i++) {
      const x = padL + i * stepX;
      const y = padT + innerH - ((arr[i] - minY) / rangeY) * innerH;
      p += (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1) + " ";
    }
    const color = SIZE_COLORS[parseInt(name)] || "#888";
    paths += `<path d="${p}" stroke="${color}" stroke-width="1.5" fill="none"/>`;
  });
  const yTicks = [];
  for (let k = 0; k <= 4; k++) {
    const val = minY + rangeY * k / 4;
    const y = padT + innerH - (k / 4) * innerH;
    yTicks.push({val, y});
  }
  let zeroLine = "";
  if (minY < 0 && maxY > 0) {
    const zY = padT + innerH - ((0 - minY) / rangeY) * innerH;
    zeroLine = `<line x1="${padL}" y1="${zY.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${zY.toFixed(1)}" stroke="#3a4452" stroke-dasharray="3,3" stroke-width="1"/>`;
  }
  const yLabels = yTicks.map(t => `
    <line x1="${padL}" y1="${t.y.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${t.y.toFixed(1)}" stroke="#1f2733" stroke-width="1"/>
    <text x="${(padL-4).toFixed(1)}" y="${(t.y+3).toFixed(1)}" fill="#8a93a6" font-size="10" text-anchor="end">${formatNumber(t.val)}</text>
  `).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="svg-chart" preserveAspectRatio="none">
    ${yLabels}${zeroLine}${paths}
  </svg>`;
}

function svgSizeBars(containerId, sizeVals, color="#22d39a", fmtFn=v=>v.toFixed(2)) {
  const el = document.getElementById(containerId);
  if (!el) return;
  const W = el.clientWidth || 800;
  const H = 240;
  const padL = 60, padR = 30, padT = 14, padB = 32;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const sizes = SIZES;
  const values = sizes.map(sz => sizeVals[sz]);
  const minV = Math.min(0, ...values);
  const maxV = Math.max(0, ...values);
  const rangeV = (maxV - minV) || 1;
  const barW = innerW / sizes.length;
  let bars = "";
  sizes.forEach((sz, i) => {
    const v = values[i];
    const yTop = padT + innerH - ((Math.max(0, v) - minV) / rangeV) * innerH;
    const yBot = padT + innerH - ((Math.min(0, v) - minV) / rangeV) * innerH;
    const x = padL + i * barW + barW * 0.15;
    const w = barW * 0.7;
    const h = Math.abs(yBot - yTop);
    const c = typeof color === "function" ? color(v) : color;
    bars += `<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${SIZE_COLORS[sz]}" opacity="0.9"/>
      <text x="${(x + w/2).toFixed(1)}" y="${(yTop - 4).toFixed(1)}" fill="${SIZE_COLORS[sz]}" font-size="11" font-weight="700" text-anchor="middle">${fmtFn(v)}</text>
      <text x="${(x + w/2).toFixed(1)}" y="${(H - 8).toFixed(1)}" fill="#8a93a6" font-size="11" text-anchor="middle">${sz} MNQ</text>`;
  });
  const yTicks = [];
  for (let k = 0; k <= 4; k++) {
    const val = minV + rangeV * k / 4;
    const y = padT + innerH - (k / 4) * innerH;
    yTicks.push({val, y});
  }
  const yLabels = yTicks.map(t => `
    <line x1="${padL}" y1="${t.y.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${t.y.toFixed(1)}" stroke="#1f2733" stroke-width="1"/>
    <text x="${(padL-4).toFixed(1)}" y="${(t.y+3).toFixed(1)}" fill="#8a93a6" font-size="10" text-anchor="end">${formatNumber(t.val)}</text>
  `).join("");
  el.style.height = H + "px";
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="svg-chart" preserveAspectRatio="none">
    ${yLabels}${bars}
  </svg>`;
}

function formatNumber(v) {
  const abs = Math.abs(v);
  if (abs >= 10000) return (v/1000).toFixed(0) + "k";
  if (abs >= 1000) return (v/1000).toFixed(1) + "k";
  if (abs >= 10) return v.toFixed(0);
  return v.toFixed(2);
}

function drawAllCharts() {
  // Equity overlay
  const seriesMap = {};
  SIZES.forEach(sz => { seriesMap[sz] = DATA.equity[sz]; });
  svgMultiLine("chart-equity", seriesMap);
  document.getElementById("eq-legend").innerHTML = SIZES.map(sz => `
    <span class="legend-item">
      <span class="legend-swatch" style="background:${SIZE_COLORS[sz]};"></span>
      ${sz} MNQ ${fmtPct(DATA.results[sz].return_pct)}
    </span>`).join("");
  // DD
  const ddVals = {};
  SIZES.forEach(sz => { ddVals[sz] = DATA.results[sz].max_dd_pct; });
  svgSizeBars("chart-dd", ddVals, "#ff5470", v => v.toFixed(2)+"%");
  // Calmar
  const calmar = {};
  SIZES.forEach(sz => { calmar[sz] = DATA.results[sz].calmar; });
  svgSizeBars("chart-calmar", calmar, "#22d39a", v => v.toFixed(1));
}
drawAllCharts();

// ============ Size-switchable weekly/daily tables ============
let selectedWeeklySize = bestSize || SIZES[0];
let selectedDailySize = bestSize || SIZES[0];

function renderTabs(containerId, selected, onChange) {
  document.getElementById(containerId).innerHTML = SIZES.map(sz => `
    <button class="size-tab${sz==selected?" active":""}" data-size="${sz}">${sz} MNQ</button>`).join("");
  document.querySelectorAll(`#${containerId} .size-tab`).forEach(b => {
    b.onclick = () => { onChange(parseInt(b.dataset.size)); };
  });
}
function renderWeekly() {
  renderTabs("weekly-tabs", selectedWeeklySize, sz => { selectedWeeklySize = sz; renderWeekly(); });
  const rows = DATA.weekly[selectedWeeklySize];
  document.getElementById("weekly-tbody").innerHTML = rows.map(w => `
    <tr><td class="left">${esc(w.week)}</td><td>${w.trades}</td><td>${w.wins}</td>
    <td>${w.wr.toFixed(1)}%</td>
    <td class="${w.pnl>=0?"pos":"neg"}">${fmtMoney(w.pnl)}</td>
    <td class="${w.pnl>=0?"pos":"neg"}">${fmtPct(w.pnl/STARTING_BAL*100)}</td></tr>`).join("");
}
function renderDaily() {
  renderTabs("daily-tabs", selectedDailySize, sz => { selectedDailySize = sz; renderDaily(); });
  const rows = DATA.daily[selectedDailySize];
  document.getElementById("daily-tbody").innerHTML = rows.map(d => `
    <tr><td class="left">${esc(d.date)}</td><td>${d.trades}</td><td>${d.wins}</td>
    <td>${(d.wins/d.trades*100).toFixed(1)}%</td>
    <td class="${d.pnl>=0?"pos":"neg"}">${fmtMoney(d.pnl)}</td>
    <td class="${d.cum_pnl>=0?"pos":"neg"}">${fmtMoney(d.cum_pnl)}</td></tr>`).join("");
}
renderWeekly();
renderDaily();

window.addEventListener("resize", drawAllCharts);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
