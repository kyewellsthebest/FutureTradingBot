"""Build a TRULY self-contained HTML report — no external CDN deps.
Charts are inline SVG so they render even with no internet."""
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
    DEFAULT_SIZE, MIN_TARGET_HOLD_SECONDS, COOLDOWN_SECS,
    MAX_HOLD_SECS, MAX_WAIT_SECS,
    IMPULSE_PTS, IMPULSE_WINDOW_BARS, PULLBACK_PCT,
    STOP_PTS, TARGET_PTS,
)

SRC = Path("/home/user/HFTBot/data/tick/NQ.03-26.Last.parquet")
OUT_HTML = Path("/home/user/HFTBot/reports/simulation_report.html")

STARTING_BALANCE = 50_000.0
MNQ_PER_PT = 2.0
COMM_PER_CONTRACT_RT = 1.0
LATENCY_MS = 200


def build_1m_bars(price, ts_ns, volume):
    df = pd.DataFrame({"price": price, "volume": volume,
                       "ts": pd.to_datetime(ts_ns, utc=True)})
    df = df.set_index("ts")
    ohlc = df["price"].resample("1min").agg(["first", "max", "min", "last"])
    ohlc.columns = ["open", "high", "low", "close"]
    vol = df["volume"].resample("1min").sum()
    return pd.concat([ohlc, vol.rename("volume")], axis=1).dropna()


def run_simulation():
    t0 = time.time()
    print("Loading...")
    df = pd.read_parquet(SRC)
    period_days = (df["ts"].iloc[-1] - df["ts"].iloc[0]).total_seconds() / 86400
    price = df["price"].to_numpy(dtype=np.float32)
    volume = df["volume"].to_numpy(dtype=np.int32)
    ts_ns = df["ts"].astype("int64").to_numpy()
    bars_1m = build_1m_bars(price, ts_ns, volume)
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
        setup = detect_pullback_setup(bars_at_i, pd.Timestamp(sig_ts, tz="UTC").to_pydatetime())
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
        pnl_usd = pnl_pts * DEFAULT_SIZE * MNQ_PER_PT - COMM_PER_CONTRACT_RT * DEFAULT_SIZE
        trades.append({
            "side": setup.side, "size": DEFAULT_SIZE,
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "entry_px": round(float(entry_price), 2),
            "exit_px": round(float(exit_px), 2),
            "stop_px": round(float(stop_px), 2),
            "target_px": round(float(target_px), 2),
            "hold_s": round((exit_ts - entry_ts) / 1e9, 2),
            "exit_reason": reason,
            "pnl_usd": round(float(pnl_usd), 2),
        })
        used_keys.add(key)
        last_exit_ts = exit_ts
    print(f"  {len(trades)} trades in {time.time()-t0:.0f}s")
    return trades, period_days


def build_data_dict(trades, period_days):
    tdf = pd.DataFrame(trades)
    tdf["entry_dt"] = pd.to_datetime(tdf["entry_ts"], utc=True)
    tdf["exit_dt"] = pd.to_datetime(tdf["exit_ts"], utc=True)
    tdf["date"] = tdf["entry_dt"].dt.tz_convert("America/New_York").dt.date
    tdf["week"] = tdf["entry_dt"].dt.to_period("W-MON").astype(str)
    n = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    losses = int((tdf["pnl_usd"] < 0).sum())
    pnls = tdf["pnl_usd"].to_numpy()
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else 999
    cum = pnls.cumsum()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    avg_w = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].mean()) if wins else 0
    avg_l = float(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].mean()) if losses else 0
    max_streak = streak = 0
    for p in pnls:
        if p < 0:
            streak += 1
            if streak > max_streak: max_streak = streak
        else: streak = 0
    months = period_days / 30.44

    daily = tdf.groupby("date").agg(trades=("pnl_usd", "size"),
        wins=("pnl_usd", lambda x: int((x > 0).sum())),
        pnl=("pnl_usd", "sum")).reset_index()
    daily["date_str"] = daily["date"].astype(str)
    daily["cum_pnl"] = daily["pnl"].cumsum()

    weekly = tdf.groupby("week").agg(trades=("pnl_usd", "size"),
        wins=("pnl_usd", lambda x: int((x > 0).sum())),
        pnl=("pnl_usd", "sum")).reset_index()
    weekly["wr"] = weekly["wins"] / weekly["trades"] * 100

    holds = tdf["hold_s"].to_numpy()
    hold_bins = [
        ("<10s", int((holds < 10).sum())),
        ("10-30s", int(((holds >= 10) & (holds < 30)).sum())),
        ("30-60s", int(((holds >= 30) & (holds < 60)).sum())),
        ("1-5m", int(((holds >= 60) & (holds < 300)).sum())),
        ("5-10m", int(((holds >= 300) & (holds < 600)).sum())),
        ("10m+", int((holds >= 600).sum())),
    ]
    wl_bins = []
    for label, lo, hi in [
        ("<=-15", -1e9, -15), ("-15--10", -15, -10), ("-10--5", -10, -5),
        ("-5-0", -5, 0), ("0-5", 0, 5), ("5-10", 5, 10),
        ("10-15", 10, 15), ("15-20", 15, 20), (">20", 20, 1e9),
    ]:
        wl_bins.append({"label": label, "count": int(((pnls >= lo) & (pnls < hi)).sum())})

    bal = STARTING_BALANCE
    equity_curve = []
    for r in trades:
        bal += r["pnl_usd"]
        equity_curve.append({"i": len(equity_curve), "balance": round(bal, 2)})

    by_exit = {}
    for reason in ["target", "stop", "timeout"]:
        g = tdf[tdf["exit_reason"] == reason]
        if len(g) == 0: continue
        by_exit[reason] = {
            "count": int(len(g)),
            "wr": float((g["pnl_usd"] > 0).mean() * 100),
            "avg": float(g["pnl_usd"].mean()),
            "total": float(g["pnl_usd"].sum()),
        }

    return {
        "meta": {
            "period_start": str(tdf["entry_dt"].min()),
            "period_end": str(tdf["exit_dt"].max()),
            "period_days": round(period_days, 1),
            "period_months": round(months, 2),
            "starting_balance": STARTING_BALANCE,
            "strategy": "Pullback Impulse",
            "default_size": DEFAULT_SIZE,
            "impulse_pts": IMPULSE_PTS, "impulse_window_bars": IMPULSE_WINDOW_BARS,
            "pullback_pct": PULLBACK_PCT, "stop_pts": STOP_PTS, "target_pts": TARGET_PTS,
            "max_hold_secs": MAX_HOLD_SECS,
            "min_target_hold_secs": MIN_TARGET_HOLD_SECONDS,
            "cooldown_secs": COOLDOWN_SECS,
            "comm_per_contract": COMM_PER_CONTRACT_RT, "latency_ms": LATENCY_MS,
        },
        "summary": {
            "n_trades": n, "wins": wins, "losses": losses,
            "wr_pct": round(wins/n*100, 2),
            "pf": round(pf, 3) if pf < 99 else None,
            "rr": round(abs(avg_w/avg_l) if avg_l else 0, 2),
            "avg_win": round(avg_w, 2), "avg_loss": round(avg_l, 2),
            "total_pnl": round(float(pnls.sum()), 2),
            "return_pct": round(float(pnls.sum()/STARTING_BALANCE*100), 2),
            "return_pct_per_mo": round(float(pnls.sum()/STARTING_BALANCE*100/months), 2),
            "max_dd_usd": round(maxdd, 2),
            "max_dd_pct": round(abs(maxdd/STARTING_BALANCE*100), 2),
            "max_losing_streak": int(max_streak),
            "trades_per_day": round(n/period_days, 1),
            "trades_per_week": round(n*5/period_days, 1),
            "trades_per_month": round(n/months, 1),
        },
        "by_exit": by_exit,
        "hold_distribution": [{"bin": l, "count": c} for l, c in hold_bins],
        "winloss_distribution": wl_bins,
        "daily": daily[["date_str", "trades", "wins", "pnl", "cum_pnl"]].to_dict(orient="records"),
        "weekly": weekly.to_dict(orient="records"),
        "equity_curve": equity_curve,
        "trades": trades,
    }


def main():
    trades, period_days = run_simulation()
    data = build_data_dict(trades, period_days)
    data_json = json.dumps(data, default=str)
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html)
    print(f"\nWrote {OUT_HTML}  ({OUT_HTML.stat().st_size / 1e6:.2f} MB)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Pullback Impulse · Ultra-Real Simulation</title>
<style>
body{background:#0a0e17;color:#d4dae5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;}
main{max-width:1300px;margin:0 auto;padding:16px;}
h1{color:#22d39a;margin:0 0 8px 0;font-size:24px;}
h2{color:#d4dae5;margin:24px 0 10px 0;font-size:18px;border-bottom:1px solid #1f2733;padding-bottom:4px;}
p.sub{color:#8a93a6;margin:0 0 14px 0;font-size:13px;}
code{background:#1f2733;padding:2px 6px;border-radius:3px;font-size:12px;}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0;}
.stat-card{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:10px 14px;}
.stat-label{color:#8a93a6;font-size:10px;text-transform:uppercase;letter-spacing:0.5px;}
.stat-value{font-size:22px;font-weight:700;margin-top:2px;}
.stat-sub{color:#8a93a6;font-size:10px;margin-top:2px;}
.pos{color:#22d39a;}.neg{color:#ff5470;}
.chart-block{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:14px;margin-bottom:14px;}
.chart-title{color:#d4dae5;font-size:13px;font-weight:600;margin-bottom:10px;}
.svg-chart{width:100%;height:260px;display:block;}
.play-block{background:linear-gradient(135deg,#1a2138,#0f1422);border:2px solid #22d39a;border-radius:12px;padding:16px;margin:20px 0;}
.play-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px;}
.play-btn{background:#22d39a;color:#0a0e17;border:none;padding:10px 22px;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;}
.play-btn.paused{background:#ff8c4a;}
.speed-btn{background:#1f2733;color:#d4dae5;border:1px solid #2a3441;padding:6px 12px;border-radius:6px;cursor:pointer;font-size:12px;}
.speed-btn.active{background:#22d39a;color:#0a0e17;border-color:#22d39a;}
.play-status{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;}
.play-stat{background:#0a0e17;padding:8px 14px;border-radius:8px;flex:1 1 120px;min-width:120px;max-width:180px;}
.play-stat-label{color:#8a93a6;font-size:10px;text-transform:uppercase;}
.play-stat-value{font-size:20px;font-weight:700;margin-top:2px;}
.play-progress{width:100%;height:6px;background:#1f2733;border-radius:3px;margin-top:12px;overflow:hidden;}
.play-progress-bar{height:100%;background:linear-gradient(90deg,#22d39a,#1ec48a);width:0%;}
table.rep{width:100%;border-collapse:collapse;font-size:11px;background:#0f1422;}
table.rep th,table.rep td{padding:7px 8px;text-align:right;border-bottom:1px solid #1f2733;}
table.rep th{background:#161d2b;color:#8a93a6;text-transform:uppercase;letter-spacing:0.5px;font-size:10px;font-weight:600;position:sticky;top:0;}
table.rep td.left{text-align:left;}
table.rep td.side-long{color:#22d39a;}table.rep td.side-short{color:#ff5470;}
.scroll{max-height:450px;overflow-y:auto;border-radius:8px;border:1px solid #1f2733;}
.pager{display:flex;gap:6px;margin-top:10px;align-items:center;flex-wrap:wrap;}
.pager button{background:#1f2733;color:#d4dae5;border:1px solid #2a3441;padding:6px 12px;border-radius:6px;cursor:pointer;}
.pager button:disabled{opacity:0.3;cursor:not-allowed;}
.filters{display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;}
.filters select,.filters input{background:#1f2733;color:#d4dae5;border:1px solid #2a3441;padding:6px 10px;border-radius:6px;font-size:12px;}
.spec-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin:12px 0;}
.spec-row{display:flex;justify-content:space-between;align-items:center;background:#0f1422;padding:10px 14px;border-radius:8px;border:1px solid #1f2733;}
.spec-row.pass{border-color:#22d39a;}.spec-row.fail{border-color:#ff5470;}
.meta{background:#0f1422;border:1px solid #1f2733;border-radius:10px;padding:12px 16px;font-size:12px;color:#b0b7c3;}
.meta div{padding:2px 0;}.meta b{color:#d4dae5;}
</style>
</head>
<body>
<main>
<h1>📊 Ultra-Real Simulation</h1>
<p class="sub">Pullback Impulse · NQ futures · Dec 10 2025 → Feb 27 2026 · 1 MNQ fixed · 200ms latency</p>
<div class="meta" id="meta"></div>

<h2>📈 Headline Stats</h2>
<div class="stat-grid" id="stat-grid"></div>

<div class="play-block">
  <div class="chart-title">🎬 Day-by-Day P&L Replay (trading days only)</div>
  <div class="play-controls">
    <button class="play-btn" id="play-btn">▶ Play</button>
    <button class="play-btn" id="reset-btn" style="background:#3a4452;">⟲ Reset</button>
    <span style="color:#8a93a6;font-size:12px;">Speed:</span>
    <button class="speed-btn" data-speed="2000">0.5×</button>
    <button class="speed-btn active" data-speed="1000">1×</button>
    <button class="speed-btn" data-speed="500">2×</button>
    <button class="speed-btn" data-speed="200">5×</button>
    <button class="speed-btn" data-speed="50">20×</button>
  </div>
  <div class="play-status">
    <div class="play-stat"><div class="play-stat-label">Date</div><div class="play-stat-value" id="p-date">—</div></div>
    <div class="play-stat"><div class="play-stat-label">Today P&L</div><div class="play-stat-value" id="p-pnl">$0</div></div>
    <div class="play-stat"><div class="play-stat-label">Today Trades</div><div class="play-stat-value" id="p-trades">0</div></div>
    <div class="play-stat"><div class="play-stat-label">Today Wins</div><div class="play-stat-value" id="p-wins">0</div></div>
    <div class="play-stat"><div class="play-stat-label">Balance</div><div class="play-stat-value" id="p-bal">$50,000</div></div>
    <div class="play-stat"><div class="play-stat-label">Return</div><div class="play-stat-value" id="p-ret">+0.00%</div></div>
  </div>
  <div class="play-progress"><div class="play-progress-bar" id="p-bar"></div></div>
</div>

<h2>🎯 Spec Check</h2>
<div class="spec-grid" id="spec-grid"></div>

<div class="chart-block"><div class="chart-title">Equity Curve (per-trade resolution)</div><div id="chart-equity"></div></div>
<div class="chart-block"><div class="chart-title">Daily P&L (all trading days)</div><div id="chart-daily"></div></div>
<div class="chart-block"><div class="chart-title">Drawdown Over Time</div><div id="chart-dd"></div></div>
<div class="chart-block"><div class="chart-title">Hold-Time Distribution</div><div id="chart-hold"></div></div>
<div class="chart-block"><div class="chart-title">P&L per Trade Distribution</div><div id="chart-wl"></div></div>

<h2>🎟 By Exit Reason</h2>
<div class="scroll"><table class="rep"><thead><tr><th class="left">Reason</th><th>Count</th><th>WR</th><th>Avg P&L</th><th>Total P&L</th></tr></thead><tbody id="exit-tbody"></tbody></table></div>

<h2>📅 Per-Week Performance</h2>
<div class="scroll"><table class="rep"><thead><tr><th class="left">Week</th><th>Trades</th><th>Wins</th><th>WR</th><th>P&L</th><th>Return %</th></tr></thead><tbody id="weekly-tbody"></tbody></table></div>

<h2>📆 Per-Day Performance</h2>
<div class="scroll"><table class="rep"><thead><tr><th class="left">Date</th><th>Trades</th><th>Wins</th><th>WR</th><th>Day P&L</th><th>Running P&L</th></tr></thead><tbody id="daily-tbody"></tbody></table></div>

<h2>📋 Every Trade Taken</h2>
<div class="filters">
  <select id="f-side"><option value="">All sides</option><option value="LONG">LONG</option><option value="SHORT">SHORT</option></select>
  <select id="f-reason"><option value="">All reasons</option><option value="target">target</option><option value="stop">stop</option><option value="timeout">timeout</option></select>
  <select id="f-pnl"><option value="">All P&L</option><option value="win">Wins</option><option value="loss">Losses</option></select>
  <input type="text" id="f-date" placeholder="Date YYYY-MM-DD" />
  <span style="color:#8a93a6;font-size:11px;align-self:center;"><span id="t-count">—</span> trades</span>
</div>
<div class="scroll"><table class="rep"><thead><tr>
  <th class="left">#</th><th class="left">Entry NY</th><th>Side</th><th>Entry</th><th>Exit</th><th>Stop</th><th>Tgt</th><th>Hold</th><th>Reason</th><th>P&L</th>
</tr></thead><tbody id="trades-tbody"></tbody></table></div>
<div class="pager">
  <button id="pg-prev">‹ Prev</button>
  <span id="pg-info" style="color:#8a93a6;font-size:11px;padding:0 8px;align-self:center;"></span>
  <button id="pg-next">Next ›</button>
</div>

</main>

<script>
const DATA = __DATA_JSON__;
const STARTING_BAL = 50000;

function fmtMoney(v, sign=true){const s=sign&&v>0?"+":(v<0?"-":"");return s+"$"+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});}
function fmtPct(v){return (v>0?"+":"")+v.toFixed(2)+"%";}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

// ============================================================================
// SVG chart helpers (no external deps)
// ============================================================================
function svgLine(containerId, data, opts={}) {
  const el = document.getElementById(containerId);
  if (!el || !data || data.length === 0) { if (el) el.innerHTML = "<div style='color:#8a93a6;padding:10px'>(no data)</div>"; return; }
  const W = el.clientWidth || 800;
  const H = opts.height || 260;
  const padL = 50, padR = 10, padT = 10, padB = 24;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const minY = Math.min(...data);
  const maxY = Math.max(...data);
  const rangeY = (maxY - minY) || 1;
  const stepX = data.length > 1 ? innerW / (data.length - 1) : 0;
  let path = "";
  let fillPath = "";
  for (let i = 0; i < data.length; i++) {
    const x = padL + i * stepX;
    const y = padT + innerH - ((data[i] - minY) / rangeY) * innerH;
    path += (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1) + " ";
  }
  // Y-axis ticks (5 of them)
  const yTicks = [];
  for (let k = 0; k <= 4; k++) {
    const val = minY + rangeY * k / 4;
    const y = padT + innerH - (k / 4) * innerH;
    yTicks.push({val, y});
  }
  // baseline (zero) line if zero is in range
  let zeroLine = "";
  if (opts.showZero !== false && minY < 0 && maxY > 0) {
    const zY = padT + innerH - ((0 - minY) / rangeY) * innerH;
    zeroLine = `<line x1="${padL}" y1="${zY.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${zY.toFixed(1)}" stroke="#3a4452" stroke-dasharray="3,3" stroke-width="1"/>`;
  }
  const color = opts.color || "#22d39a";
  const fillColor = opts.fillColor || (color === "#22d39a" ? "rgba(34,211,154,0.15)" : "rgba(255,84,112,0.15)");
  // Fill area under the line
  if (opts.fill !== false && data.length > 1) {
    const lastX = padL + (data.length - 1) * stepX;
    fillPath = `<path d="${path} L${lastX.toFixed(1)},${(padT+innerH).toFixed(1)} L${padL.toFixed(1)},${(padT+innerH).toFixed(1)} Z" fill="${fillColor}"/>`;
  }
  const yLabels = yTicks.map(t => `
    <line x1="${padL}" y1="${t.y.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${t.y.toFixed(1)}" stroke="#1f2733" stroke-width="1"/>
    <text x="${(padL-4).toFixed(1)}" y="${(t.y+3).toFixed(1)}" fill="#8a93a6" font-size="10" text-anchor="end">${formatNumber(t.val)}</text>
  `).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="svg-chart" preserveAspectRatio="none">
    ${yLabels}
    ${zeroLine}
    ${fillPath}
    <path d="${path}" stroke="${color}" stroke-width="1.5" fill="none"/>
  </svg>`;
}

function svgBars(containerId, labels, values, opts={}) {
  const el = document.getElementById(containerId);
  if (!el || !values || values.length === 0) { if (el) el.innerHTML = "<div style='color:#8a93a6;padding:10px'>(no data)</div>"; return; }
  const W = el.clientWidth || 800;
  const H = opts.height || 260;
  const padL = 50, padR = 10, padT = 10, padB = 36;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const minV = Math.min(0, ...values);
  const maxV = Math.max(0, ...values);
  const rangeV = (maxV - minV) || 1;
  const barW = innerW / values.length;
  const zeroY = padT + innerH - ((0 - minV) / rangeV) * innerH;
  let bars = "";
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    const yTop = padT + innerH - ((Math.max(0, v) - minV) / rangeV) * innerH;
    const yBot = padT + innerH - ((Math.min(0, v) - minV) / rangeV) * innerH;
    const x = padL + i * barW + 1;
    const w = Math.max(1, barW - 2);
    const h = Math.abs(yBot - yTop);
    const color = opts.colorFn ? opts.colorFn(v, i, labels[i]) : (v >= 0 ? "#22d39a" : "#ff5470");
    bars += `<rect x="${x.toFixed(1)}" y="${yTop.toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" fill="${color}" opacity="0.85"/>`;
  }
  // Y ticks
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
  // X labels — show at most 12
  let xLabels = "";
  const labelStep = Math.max(1, Math.ceil(labels.length / 12));
  for (let i = 0; i < labels.length; i += labelStep) {
    const x = padL + i * barW + barW / 2;
    xLabels += `<text x="${x.toFixed(1)}" y="${(H - 8)}" fill="#8a93a6" font-size="9" text-anchor="middle">${esc(labels[i])}</text>`;
  }
  // zero baseline
  const zeroLine = `<line x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${(padL+innerW).toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="#3a4452" stroke-width="1"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="svg-chart" preserveAspectRatio="none">
    ${yLabels}${zeroLine}${bars}${xLabels}
  </svg>`;
}

function formatNumber(v) {
  const abs = Math.abs(v);
  if (abs >= 10000) return (v/1000).toFixed(0) + "k";
  if (abs >= 1000) return (v/1000).toFixed(1) + "k";
  if (abs >= 10) return v.toFixed(0);
  return v.toFixed(1);
}

// ============================================================================
// Render content
// ============================================================================
function renderAll() {
  try {
    const m = DATA.meta, s = DATA.summary;
    document.getElementById("meta").innerHTML = `
      <div><b>Period:</b> ${m.period_start.slice(0,10)} → ${m.period_end.slice(0,10)} (${m.period_days} days, ${m.period_months} months)</div>
      <div><b>Strategy:</b> ${m.strategy} · <b>Size:</b> ${m.default_size} MNQ fixed</div>
      <div><b>Signal:</b> ≥${m.impulse_pts}-pt net move over ${m.impulse_window_bars} bars → LIMIT at ${m.pullback_pct} retrace</div>
      <div><b>Stop:</b> ${m.stop_pts}pt · <b>Target:</b> ${m.target_pts}pt (planned RR ${(m.target_pts/m.stop_pts).toFixed(2)})</div>
      <div><b>Holds:</b> max ${m.max_hold_secs}s · target min ${m.min_target_hold_secs}s · stops fire fast</div>
      <div><b>Cooldown:</b> ${m.cooldown_secs}s · <b>Execution:</b> ${m.latency_ms}ms latency, $${m.comm_per_contract}/contract`;

    // Stat cards
    const cards = [
      ["Total Return", fmtPct(s.return_pct), s.return_pct>=0?"pos":"neg", `${s.return_pct_per_mo>0?"+":""}${s.return_pct_per_mo}%/mo`],
      ["Total P&L", fmtMoney(s.total_pnl), s.total_pnl>=0?"pos":"neg", `over ${m.period_months} mo`],
      ["Trades", s.n_trades.toLocaleString(), "", `${s.trades_per_day}/day · ${s.trades_per_month}/mo`],
      ["Win Rate", s.wr_pct + "%", s.wr_pct>=55?"pos":"neg", `${s.wins} W / ${s.losses} L`],
      ["Profit Factor", s.pf?s.pf.toFixed(2):"∞", s.pf>=1?"pos":"neg", "wins/losses"],
      ["RR (actual)", s.rr.toFixed(2), s.rr>=1.2?"pos":"neg", `+${s.avg_win.toFixed(2)} / -${Math.abs(s.avg_loss).toFixed(2)}`],
      ["Max Drawdown", fmtMoney(s.max_dd_usd), "neg", `${s.max_dd_pct}% of $50k`],
      ["Max Losing Streak", s.max_losing_streak, "", "consecutive losses"],
    ];
    document.getElementById("stat-grid").innerHTML = cards.map(c => `
      <div class="stat-card"><div class="stat-label">${c[0]}</div>
      <div class="stat-value ${c[2]}">${c[1]}</div>
      <div class="stat-sub">${c[3]}</div></div>`).join("");

    // Specs
    const specs = [
      ["WR ≥ 55%", s.wr_pct, 55, "%", s.wr_pct>=55],
      ["RR ≥ 1.2", s.rr, 1.2, "", s.rr>=1.2],
      ["Trades/mo ≥ 100", s.trades_per_month, 100, "", s.trades_per_month>=100],
      ["Return ≥ 3%/mo", s.return_pct_per_mo, 3, "%", s.return_pct_per_mo>=3],
      ["Max DD ≤ 2%", s.max_dd_pct, 2, "%", s.max_dd_pct<=2],
    ];
    document.getElementById("spec-grid").innerHTML = specs.map(([n,a,t,u,p]) => `
      <div class="spec-row ${p?"pass":"fail"}">
        <div><b>${n}</b><br><span style="font-size:10px;color:#8a93a6;">target: ${t}${u}</span></div>
        <div style="text-align:right;">
          <div class="${p?"pos":"neg"}" style="font-size:16px;font-weight:700;">${a.toFixed(2)}${u}</div>
          <div style="font-size:16px;">${p?"✅":"❌"}</div>
        </div></div>`).join("");

    // Tables
    document.getElementById("exit-tbody").innerHTML = Object.entries(DATA.by_exit).map(([r,d]) => `
      <tr><td class="left">${esc(r)}</td><td>${d.count}</td><td>${d.wr.toFixed(1)}%</td>
      <td class="${d.avg>=0?"pos":"neg"}">${fmtMoney(d.avg)}</td>
      <td class="${d.total>=0?"pos":"neg"}">${fmtMoney(d.total)}</td></tr>`).join("");

    document.getElementById("weekly-tbody").innerHTML = DATA.weekly.map(w => `
      <tr><td class="left">${esc(w.week)}</td><td>${w.trades}</td><td>${w.wins}</td>
      <td>${w.wr.toFixed(1)}%</td>
      <td class="${w.pnl>=0?"pos":"neg"}">${fmtMoney(w.pnl)}</td>
      <td class="${w.pnl>=0?"pos":"neg"}">${fmtPct(w.pnl/STARTING_BAL*100)}</td></tr>`).join("");

    document.getElementById("daily-tbody").innerHTML = DATA.daily.map(d => `
      <tr><td class="left">${esc(d.date_str)}</td><td>${d.trades}</td><td>${d.wins}</td>
      <td>${(d.wins/d.trades*100).toFixed(1)}%</td>
      <td class="${d.pnl>=0?"pos":"neg"}">${fmtMoney(d.pnl)}</td>
      <td class="${d.cum_pnl>=0?"pos":"neg"}">${fmtMoney(d.cum_pnl)}</td></tr>`).join("");

    // Charts
    drawCharts();

    // Trades table
    renderTrades();
  } catch (e) {
    console.error(e);
    document.body.insertAdjacentHTML("afterbegin",
      `<div style="background:#ff5470;color:white;padding:14px;font-family:monospace;">Error: ${esc(String(e))}</div>`);
  }
}

function drawCharts() {
  try {
    svgLine("chart-equity", DATA.equity_curve.map(p=>p.balance), {color:"#22d39a"});
  } catch(e){ console.error("eq", e); }
  try {
    svgBars("chart-daily",
      DATA.daily.map(d=>d.date_str.slice(5)),
      DATA.daily.map(d=>d.pnl));
  } catch(e){ console.error("daily", e); }
  try {
    let cum=0, peak=0;
    const dd = DATA.equity_curve.map(p=>{ cum=p.balance-STARTING_BAL; if(cum>peak)peak=cum; return cum-peak; });
    svgLine("chart-dd", dd, {color:"#ff5470", fillColor:"rgba(255,84,112,0.18)"});
  } catch(e){ console.error("dd", e); }
  try {
    svgBars("chart-hold",
      DATA.hold_distribution.map(h=>h.bin),
      DATA.hold_distribution.map(h=>h.count),
      {colorFn:()=>"#22d39a"});
  } catch(e){ console.error("hold", e); }
  try {
    svgBars("chart-wl",
      DATA.winloss_distribution.map(b=>b.label),
      DATA.winloss_distribution.map(b=>b.count),
      {colorFn:(v,i,lbl)=> lbl.startsWith("-")||lbl.startsWith("<=") ? "#ff5470":"#22d39a"});
  } catch(e){ console.error("wl", e); }
}

// ============================================================================
// Playback
// ============================================================================
let playing=false, playTimer=null, curIdx=0, speedMs=1000;
function startPlay(){
  if (curIdx>=DATA.daily.length) curIdx=0;
  playing=true;
  document.getElementById("play-btn").textContent="⏸ Pause";
  document.getElementById("play-btn").classList.add("paused");
  playTimer = setInterval(()=>{
    if (curIdx>=DATA.daily.length){ stopPlay(); return; }
    curIdx++;
    updatePlay();
  }, speedMs);
}
function stopPlay(){
  playing=false;
  if (playTimer) clearInterval(playTimer);
  document.getElementById("play-btn").textContent="▶ Play";
  document.getElementById("play-btn").classList.remove("paused");
}
function updatePlay(){
  if (!DATA.daily || DATA.daily.length===0) return;
  const init = curIdx===0;
  const idx = Math.max(0, Math.min(curIdx-1, DATA.daily.length-1));
  const d = DATA.daily[idx] || {date_str:"—",pnl:0,trades:0,wins:0,cum_pnl:0};
  document.getElementById("p-date").textContent = init?"Day 0":d.date_str;
  const pnl = init?0:d.pnl;
  const pEl = document.getElementById("p-pnl");
  pEl.textContent = fmtMoney(pnl);
  pEl.className = "play-stat-value " + (pnl>=0?"pos":"neg");
  document.getElementById("p-trades").textContent = init?0:d.trades;
  document.getElementById("p-wins").textContent = init?0:d.wins;
  const bal = STARTING_BAL + (init?0:d.cum_pnl);
  document.getElementById("p-bal").textContent = "$" + bal.toLocaleString(undefined,{maximumFractionDigits:0});
  const ret = (bal - STARTING_BAL)/STARTING_BAL*100;
  const rEl = document.getElementById("p-ret");
  rEl.textContent = fmtPct(ret);
  rEl.className = "play-stat-value " + (ret>=0?"pos":"neg");
  document.getElementById("p-bar").style.width = (curIdx/DATA.daily.length*100) + "%";
}
document.getElementById("play-btn").onclick = ()=>{ if (playing) stopPlay(); else startPlay(); };
document.getElementById("reset-btn").onclick = ()=>{ stopPlay(); curIdx=0; updatePlay(); };
document.querySelectorAll(".speed-btn").forEach(b=>{
  b.onclick = ()=>{
    document.querySelectorAll(".speed-btn").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    speedMs = parseInt(b.dataset.speed);
    if (playing){ stopPlay(); startPlay(); }
  };
});

// ============================================================================
// Trades table
// ============================================================================
let filtered = DATA.trades.slice();
let pageIdx = 0;
const PAGE_SIZE = 100;
function applyFilters(){
  const side = document.getElementById("f-side").value;
  const reason = document.getElementById("f-reason").value;
  const pnl = document.getElementById("f-pnl").value;
  const date = document.getElementById("f-date").value.trim();
  filtered = DATA.trades.filter(t=>{
    if (side && t.side !== side) return false;
    if (reason && t.exit_reason !== reason) return false;
    if (pnl === "win" && t.pnl_usd <= 0) return false;
    if (pnl === "loss" && t.pnl_usd >= 0) return false;
    if (date){
      const dStr = new Date(t.entry_ts/1e6).toISOString().slice(0,10);
      if (!dStr.includes(date)) return false;
    }
    return true;
  });
  pageIdx = 0;
  renderTrades();
}
function renderTrades(){
  const start = pageIdx * PAGE_SIZE;
  const slice = filtered.slice(start, start + PAGE_SIZE);
  document.getElementById("trades-tbody").innerHTML = slice.map((t,i)=>{
    const dt = new Date(t.entry_ts/1e6);
    const dtStr = dt.toLocaleString("en-US",{timeZone:"America/New_York",
      year:"numeric",month:"2-digit",day:"2-digit",
      hour:"2-digit",minute:"2-digit",hour12:false});
    return `<tr><td class="left">${start+i+1}</td>
      <td class="left">${esc(dtStr)}</td>
      <td class="side-${t.side.toLowerCase()}">${t.side}</td>
      <td>${t.entry_px}</td><td>${t.exit_px}</td>
      <td>${t.stop_px}</td><td>${t.target_px}</td>
      <td>${t.hold_s<60?t.hold_s.toFixed(0)+"s":(t.hold_s/60).toFixed(1)+"m"}</td>
      <td>${esc(t.exit_reason)}</td>
      <td class="${t.pnl_usd>=0?"pos":"neg"}">${fmtMoney(t.pnl_usd)}</td></tr>`;
  }).join("");
  document.getElementById("t-count").textContent = filtered.length;
  document.getElementById("pg-info").textContent =
    `${start+1}–${Math.min(start+PAGE_SIZE, filtered.length)} of ${filtered.length}`;
  document.getElementById("pg-prev").disabled = pageIdx === 0;
  document.getElementById("pg-next").disabled = (pageIdx+1)*PAGE_SIZE >= filtered.length;
}
document.getElementById("f-side").onchange = applyFilters;
document.getElementById("f-reason").onchange = applyFilters;
document.getElementById("f-pnl").onchange = applyFilters;
document.getElementById("f-date").oninput = applyFilters;
document.getElementById("pg-prev").onclick = ()=>{ if (pageIdx>0){pageIdx--; renderTrades();} };
document.getElementById("pg-next").onclick = ()=>{ if ((pageIdx+1)*PAGE_SIZE<filtered.length){pageIdx++; renderTrades();} };

// Initial render
renderAll();
updatePlay();
// Re-draw charts on window resize so SVG re-scales correctly
let resizeT = null;
window.addEventListener("resize", ()=>{
  if (resizeT) clearTimeout(resizeT);
  resizeT = setTimeout(drawCharts, 200);
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
