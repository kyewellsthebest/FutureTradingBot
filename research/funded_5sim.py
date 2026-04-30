"""
12-month TopStep Funded Account simulation × 5 staggered start dates.

Specs:
  Window:        2025-03-26 → 2026-03-25 (12 months)
  Account type:  $50K Live Funded
                  - Start balance: $50,000
                  - MLL: $48,000 (trails EOD high, never moves down)
                  - Locks at $50,000 once balance reaches $52,000
                  - Position cap: 50 MNQ
                  - All flat by 3:10 PM CT
                  - DLL: $1,000 (auto-flatten for the day)

  Sizing:        Half-Kelly with uncertainty haircut + 25% buffer cap
  Whitelist:     40 OOS-validated patterns (current bot)
  Macro stack:   v2 — Sharpe-preserving boosts only (cap 1.5x):
                  v1:
                   - SHORT when NAAIM > 90
                   - LONG when AAII bull-bear z52w < -1.5 (capitulation)
                   - SHORT when HY 5d change > +3%
                   - LONG/SHORT when CFTC AM-LM > |0.30|
                  v2 (new from cross-dataset pattern miner):
                   - SHORT when WTI 5d change > +5%
                   - SHORT when yield-curve 20d change < -0.10
                   - SHORT when AAII bear > 0.45 AND TGA-z < -0.5

  5 sims:        Same window, staggered start dates 7 days apart
                 (sims 1-5 = Mar 26, Apr 2, Apr 9, Apr 16, Apr 23)

Output:
  data/funded_5sim_results.json
  data/funded_5sim_report.html  — full visual report with charts + tables
"""
from __future__ import annotations

import base64
import io
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Use Agg backend for headless plot generation
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
OUT_JSON = DATA / "funded_5sim_results.json"
OUT_HTML = DATA / "funded_5sim_report.html"

# TopStep $50K Live Funded
START_BAL = 50_000.0
INITIAL_MLL = 48_000.0
MLL_LOCK_BAL = 52_000.0
LOCKED_MLL = 50_000.0
DLL = 1_000.0
MAX_MNQ = 50
DPP = 2.0
COMM = 0.40

WIN_DAYS = 365


def half_kelly(wr: float, rr: float, n_obs: int, frac: float = 0.5) -> float:
    if rr <= 0 or wr <= 0: return 0.0
    f = (wr * rr - (1 - wr)) / rr
    if f <= 0: return 0.0
    f = float(min(f * frac, 0.10))
    if n_obs < 100:
        f *= float(np.sqrt(n_obs / 100))
    return f


def gather_trades(start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    """Gate trades from cache + filter to whitelist + window."""
    val = json.loads((DATA/"validation_results.json").read_text())
    active = {n for n, s in val["signals"].items() if s.get("recommended")}
    cache = json.loads((DATA/"scenarios_trades_cache.json").read_text())
    raw = []
    for t in cache["trades"]:
        if t["name"] in active:
            t["ts"] = pd.Timestamp(t["ts"])
            if start <= t["ts"] <= end:
                raw.append(t)
    raw.sort(key=lambda t: t["ts"])
    open_until = pd.Timestamp.min.tz_localize("UTC")
    today = None; n_today = 0; taken = []
    for t in raw:
        if today != t["ts"].date():
            today = t["ts"].date(); n_today = 0
        if n_today >= 8 or t["ts"] < open_until:
            continue
        taken.append(t)
        lock = t["max_hold"] * (5 if t["tf"] == "5m" else 1)
        open_until = t["ts"] + pd.Timedelta(minutes=lock)
        n_today += 1
    return taken


def merge_macro(trades: list[dict]) -> pd.DataFrame:
    """Add macro features to each trade row."""
    if not trades:
        return pd.DataFrame()
    tdf = pd.DataFrame(trades)
    tdf["ts"] = pd.to_datetime(tdf["ts"]).dt.tz_localize(None)
    tdf["date_only"] = tdf["ts"].dt.normalize()
    tdf = tdf.sort_values("ts")

    cftc = pd.read_csv(DATA/"cftc_nq_features.csv.gz", parse_dates=["date"])
    cftc = cftc[cftc["contract"].str.contains("Consolidated", case=False, na=False)].set_index("date").sort_index()
    macro = pd.read_csv(DATA/"macro_features.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
    tga   = pd.read_csv(DATA/"tga_features.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
    naaim = pd.read_csv(DATA/"naaim_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
    naaim["date"] = pd.to_datetime(naaim["date"]); naaim = naaim.set_index("date").sort_index()
    aaii = pd.read_csv(DATA/"aaii_features.csv.gz").rename(columns={"Unnamed: 0":"date"})
    aaii["date"] = pd.to_datetime(aaii["date"]); aaii = aaii.set_index("date").sort_index()
    for d in [cftc, macro, tga, naaim, aaii]:
        d.index = d.index.tz_localize(None) if d.index.tz else d.index

    m = pd.merge_asof(tdf, cftc, left_on="date_only", right_index=True, direction="backward")
    m = pd.merge_asof(m, macro, left_on="date_only", right_index=True, direction="backward")
    m = pd.merge_asof(m, tga,   left_on="date_only", right_index=True, direction="backward")
    m = pd.merge_asof(m, naaim, left_on="date_only", right_index=True, direction="backward")
    m = pd.merge_asof(m, aaii,  left_on="date_only", right_index=True, direction="backward", suffixes=("","_a"))
    return m


def get_size_mult(row: pd.Series) -> float:
    """v2 macro boost stack — v1 + 3 new filters from cross-dataset pattern miner.
    Each new filter passed risk-adjusted screening (P&L ↑ ≥1%, Sharpe degradation ≤5%).
    Capped at 1.5x."""
    mult = 1.0
    side = row["side"]
    # v1 (validated)
    if side == "SHORT" and row.get("naaim", 50) > 90:                   mult = 1.5
    if side == "LONG"  and row.get("bull_bear_z52w", 0) < -1.5:         mult = 1.5
    if side == "SHORT" and row.get("hy_5d_change", 0) > 0.03:           mult = 1.5
    if side == "LONG"  and row.get("am_minus_lm", 0) >  0.30:           mult = 1.5
    if side == "SHORT" and row.get("am_minus_lm", 0) < -0.30:           mult = 1.5
    # v2 (Sharpe-preserving additions from macro_v2_test.py)
    if side == "SHORT" and row.get("wti_5d_change", 0) >  0.05:         mult = 1.5
    if side == "SHORT" and row.get("yc_change_20d",  0) < -0.10:        mult = 1.5
    if side == "SHORT" and row.get("bear", 0) > 0.45 and row.get("tga_z_1y", 0) < -0.5:
        mult = 1.5
    return mult


def simulate_one(taken_with_macro: pd.DataFrame, sim_label: str,
                  per_strat_wr: dict, per_strat_n: dict) -> dict:
    """Run one funded-account simulation."""
    bal = START_BAL
    mll = INITIAL_MLL
    mll_locked = False
    eod_high = START_BAL
    blown = False
    blow_reason = None
    realized_today = 0.0
    current_day = None
    consec_losers = 0

    daily_pnl: dict[str, float] = defaultdict(float)
    daily_trades: dict[str, int] = defaultdict(int)
    trade_log = []
    skipped = 0

    for _, t in taken_with_macro.iterrows():
        if blown:
            break
        ts = t["ts"]
        day = ts.date().isoformat()
        if current_day is None:
            current_day = day
        if day != current_day:
            # End-of-day MLL update
            eod_high = max(eod_high, bal)
            if not mll_locked:
                mll = max(mll, eod_high - 2_000.0)
                if eod_high >= MLL_LOCK_BAL:
                    mll = LOCKED_MLL
                    mll_locked = True
            current_day = day
            realized_today = 0.0
            consec_losers = 0  # reset session-level counter

        # Skip if DLL hit
        if realized_today <= -DLL:
            skipped += 1; continue

        # Sizing
        wr = per_strat_wr.get(t["name"], 0.5)
        n_obs = per_strat_n.get(t["name"], 100)
        rr = t["target_pts"] / t["stop_pts"] if t["stop_pts"] > 0 else 2.0
        kf = half_kelly(wr, rr, n_obs)
        target_risk = bal * kf
        risk_per_mnq = t["stop_pts"] * DPP + COMM
        n_contracts = int(target_risk // risk_per_mnq) if risk_per_mnq > 0 else 0

        # 25% buffer cap
        buffer = bal - mll
        max_n_buffer = int((buffer * 0.25) // risk_per_mnq)
        n_contracts = min(n_contracts, max_n_buffer)
        # Topstep cap
        n_contracts = min(n_contracts, MAX_MNQ)
        # Macro boost
        size_mult = get_size_mult(t)
        n_contracts = int(n_contracts * size_mult)
        n_contracts = min(n_contracts, MAX_MNQ)
        # Allow 1 contract if a single stop wouldn't fully blow buffer
        # (real traders take this risk; previous "buffer/5" rule was too strict)
        if n_contracts < 1 and risk_per_mnq < buffer * 0.6:
            n_contracts = 1
        if n_contracts < 1:
            skipped += 1; continue

        pnl = t["pts"] * DPP * n_contracts - COMM * n_contracts
        new_bal = bal + pnl

        # Real-time MLL check on losers
        if pnl < 0 and new_bal <= mll:
            bal = new_bal
            blown = True
            blow_reason = f"MLL_breach_{day}"
            trade_log.append({"ts": ts.isoformat(), "name": t["name"], "side": t["side"],
                              "n": n_contracts, "pnl": pnl, "bal": new_bal, "blew_up": True})
            break

        bal = new_bal
        realized_today += pnl
        daily_pnl[day] += pnl
        daily_trades[day] += 1
        if pnl < 0: consec_losers += 1
        else: consec_losers = 0
        trade_log.append({"ts": ts.isoformat(), "name": t["name"], "side": t["side"],
                          "n": n_contracts, "pnl": pnl, "bal": new_bal})

    # Final EOD update
    if not blown:
        eod_high = max(eod_high, bal)

    # Compute monthly grouping
    monthly_pnl = defaultdict(float)
    monthly_trades = defaultdict(int)
    weekly_pnl = defaultdict(float)
    for log in trade_log:
        if log.get("blew_up"): continue
        d = pd.Timestamp(log["ts"]).date()
        key = f"{d.year}-{d.month:02d}"
        monthly_pnl[key] += log["pnl"]
        monthly_trades[key] += 1
        wk = pd.Timestamp(d).strftime("%Y-W%V")
        weekly_pnl[wk] += log["pnl"]

    n_wins = sum(1 for l in trade_log if not l.get("blew_up") and l["pnl"] > 0)
    n_losses = sum(1 for l in trade_log if not l.get("blew_up") and l["pnl"] <= 0)

    return {
        "sim_label": sim_label,
        "starting_balance": START_BAL,
        "ending_balance": bal,
        "blown": blown,
        "blow_reason": blow_reason,
        "n_trades": len(trade_log),
        "n_wins": n_wins,
        "n_losses": n_losses,
        "win_rate": n_wins / max(1, n_wins + n_losses),
        "skipped": skipped,
        "daily_pnl": dict(daily_pnl),
        "daily_trades": dict(daily_trades),
        "monthly_pnl": dict(monthly_pnl),
        "monthly_trades": dict(monthly_trades),
        "weekly_pnl": dict(weekly_pnl),
        "trade_log": trade_log,
    }


def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_html(sims: list[dict], strat_summary: pd.DataFrame, window: tuple) -> str:
    """Build the HTML report with embedded charts + tables."""
    # ---- Chart 1: Equity curves for all 5 sims ----
    fig, ax = plt.subplots(figsize=(12, 6))
    for sim in sims:
        if not sim["trade_log"]:
            continue
        eq = [START_BAL]
        ts = [pd.Timestamp(sim["trade_log"][0]["ts"])]
        for log in sim["trade_log"]:
            if log.get("blew_up"): break
            eq.append(log["bal"])
            ts.append(pd.Timestamp(log["ts"]))
        ax.plot(ts, eq, label=f"{sim['sim_label']}: ${sim['ending_balance']:,.0f}",
                linewidth=1.6, alpha=0.85)
    ax.axhline(START_BAL, color="gray", linestyle="--", alpha=0.5, label=f"Start: ${START_BAL:,.0f}")
    ax.axhline(INITIAL_MLL, color="red", linestyle="--", alpha=0.4, label=f"Initial MLL: ${INITIAL_MLL:,.0f}")
    ax.axhline(LOCKED_MLL, color="orange", linestyle="--", alpha=0.4, label=f"Locked MLL: ${LOCKED_MLL:,.0f}")
    ax.set_title(f"5 Funded Account Simulations — {window[0]} to {window[1]}", fontsize=14)
    ax.set_ylabel("Account Balance ($)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    chart1 = fig_to_b64(fig)

    # ---- Chart 2: Monthly P&L by sim ----
    all_months = sorted({m for s in sims for m in s["monthly_pnl"]})
    fig, ax = plt.subplots(figsize=(12, 6))
    width = 0.15
    x = np.arange(len(all_months))
    for i, sim in enumerate(sims):
        pnls = [sim["monthly_pnl"].get(m, 0) for m in all_months]
        ax.bar(x + i * width, pnls, width, label=sim["sim_label"], alpha=0.85)
    ax.set_title("Monthly P&L by Simulation", fontsize=14)
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels(all_months, rotation=45)
    ax.set_ylabel("Monthly P&L ($)")
    ax.axhline(0, color="black", linewidth=0.7)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3, axis="y")
    chart2 = fig_to_b64(fig)

    # ---- Chart 3: Strategy trade-frequency heatmap ----
    fig, ax = plt.subplots(figsize=(10, max(6, len(strat_summary)*0.25)))
    sorted_strat = strat_summary.sort_values("trades_per_month", ascending=True)
    bars = ax.barh(sorted_strat["name"], sorted_strat["trades_per_month"], color="steelblue", alpha=0.8)
    ax.set_title("Strategy Frequency — Avg Trades per Month", fontsize=14)
    ax.set_xlabel("Trades per Month (avg across 5 sims)")
    ax.grid(axis="x", alpha=0.3)
    chart3 = fig_to_b64(fig)

    # ---- Aggregate stats ----
    n_blown = sum(1 for s in sims if s["blown"])
    final_bals = [s["ending_balance"] for s in sims]
    pnl_total = [b - START_BAL for b in final_bals]
    pnl_pct = [(b - START_BAL) / START_BAL * 100 for b in final_bals]
    n_pos = sum(1 for p in pnl_total if p > 0)
    overall_wr = np.mean([s["win_rate"] for s in sims if s["n_trades"] > 0])
    funded_wr = n_pos / len(sims)

    # ---- Tables ----
    sim_rows = ""
    for s in sims:
        end = s["ending_balance"]
        delta = end - START_BAL
        pct = delta / START_BAL * 100
        status = "BLOWN" if s["blown"] else ("PROFIT" if delta > 0 else "LOSS")
        color = "#dc3545" if s["blown"] else ("#28a745" if delta > 0 else "#6c757d")
        sim_rows += f"""
        <tr>
            <td>{s['sim_label']}</td>
            <td>${START_BAL:,.0f}</td>
            <td>${end:,.0f}</td>
            <td style="color:{color}; font-weight:bold;">${delta:+,.0f}</td>
            <td style="color:{color}; font-weight:bold;">{pct:+.1f}%</td>
            <td>{s['n_trades']:,}</td>
            <td>{s['win_rate']*100:.1f}%</td>
            <td><span style="color:{color}; font-weight:bold;">{status}</span></td>
        </tr>"""

    # Monthly table — average across 5 sims
    monthly_table = "<tr><th>Month</th>"
    for s in sims:
        monthly_table += f"<th>{s['sim_label']}</th>"
    monthly_table += "<th>Avg</th></tr>"
    for m in all_months:
        monthly_table += f"<tr><td><b>{m}</b></td>"
        vals = []
        for s in sims:
            v = s["monthly_pnl"].get(m, 0)
            vals.append(v)
            color = "#28a745" if v > 0 else "#dc3545" if v < 0 else "#6c757d"
            monthly_table += f"<td style='color:{color};'>${v:+,.0f}</td>"
        avg = np.mean(vals)
        c = "#28a745" if avg > 0 else "#dc3545" if avg < 0 else "#6c757d"
        monthly_table += f"<td style='color:{c}; font-weight:bold;'>${avg:+,.0f}</td></tr>"

    # Strategy table
    strat_rows = ""
    for _, r in strat_summary.sort_values("trades_per_month", ascending=False).iterrows():
        strat_rows += f"""
        <tr>
            <td>{r['name']}</td>
            <td>{r['side']}</td>
            <td>{r['n_trades']:.0f}</td>
            <td>{r['trades_per_week']:.1f}</td>
            <td>{r['trades_per_month']:.1f}</td>
            <td>{r['win_rate']*100:.1f}%</td>
            <td>${r['avg_pnl']:+,.0f}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>HFTBot — 12-Month 5-Sim Funded Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 1200px; margin: 24px auto; padding: 0 20px; color: #222; background: #f8f9fa; }}
h1 {{ font-size: 28px; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
h2 {{ font-size: 22px; margin-top: 36px; color: #007bff; }}
.summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 20px 0; }}
.card {{ background: white; padding: 16px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.06); }}
.card .num {{ font-size: 28px; font-weight: bold; }}
.card .lbl {{ color: #666; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
table {{ width: 100%; border-collapse: collapse; background: white; box-shadow: 0 2px 4px rgba(0,0,0,0.06); margin: 12px 0; }}
th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #e9ecef; font-size: 13px; }}
th {{ background: #f1f3f5; font-weight: 600; }}
tr:hover {{ background: #fafbfc; }}
img {{ max-width: 100%; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.06); margin: 12px 0; }}
.note {{ background: #fff3cd; padding: 12px 16px; border-left: 4px solid #ffc107; border-radius: 4px; font-size: 13px; }}
</style>
</head>
<body>

<h1>HFTBot — 12-Month TopStep Funded Simulation</h1>
<p style="color:#666;">5 staggered sims • Window: <b>{window[0]} → {window[1]}</b> • $50K Live Funded rules • v2 macro stack (NAAIM + AAII + HY + CFTC + WTI + yield-curve + TGA)</p>

<h2>Headline Numbers</h2>
<div class="summary">
  <div class="card"><div class="lbl">Funded Account Win Rate</div><div class="num">{funded_wr*100:.0f}%</div><div style="color:#666;font-size:12px;">{n_pos}/{len(sims)} accounts profitable</div></div>
  <div class="card"><div class="lbl">Per-Trade Win Rate (avg)</div><div class="num">{overall_wr*100:.1f}%</div></div>
  <div class="card"><div class="lbl">Blown Up</div><div class="num" style="color:{'#dc3545' if n_blown else '#28a745'}">{n_blown}/{len(sims)}</div></div>
  <div class="card"><div class="lbl">Median Take-Home</div><div class="num">${np.median(pnl_total):,.0f}</div><div style="color:#666;font-size:12px;">{np.median(pnl_pct):+.1f}% / yr</div></div>
</div>

<h2>Sim Results Summary</h2>
<table>
<tr><th>Sim</th><th>Start</th><th>End</th><th>P&L</th><th>%</th><th>Trades</th><th>WR</th><th>Status</th></tr>
{sim_rows}
</table>

<h2>Equity Curves (all 5 sims)</h2>
<img src="data:image/png;base64,{chart1}" />

<h2>Monthly P&L Per Sim</h2>
<table>
{monthly_table}
</table>
<img src="data:image/png;base64,{chart2}" />

<h2>Per-Strategy Trade Frequency</h2>
<p>Average across all 5 sims, after macro stack + funded-account sizing:</p>
<table>
<tr><th>Strategy</th><th>Side</th><th>Total Trades</th><th>Trades/Week</th><th>Trades/Month</th><th>Win Rate</th><th>Avg P&L/Trade</th></tr>
{strat_rows}
</table>
<img src="data:image/png;base64,{chart3}" />

<div class="note">
<b>Note on simulation realism:</b> This sim uses the bot's actual triple-barrier outcomes
on 1-minute bars (fixed-stop / fixed-target). It applies real TopStep rules:
$48K initial MLL trailing EOD high, locking at $50K once balance hits $52K,
$1K daily-loss-limit auto-flatten, 50 MNQ position cap, half-Kelly + 25%
buffer-of-MLL sizing. <b>Slippage is held at the ~2pt level used in earlier
backtests</b> — real-world fills will be slightly worse, especially around news.
</div>

<p style="color:#999; margin-top:40px; font-size:12px;">
Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} •
research/funded_5sim.py
</p>

</body>
</html>
"""


def main():
    print("=" * 70)
    print("12-MONTH FUNDED-ACCOUNT 5-SIM RUNNER")
    print("=" * 70)

    val = json.loads((DATA/"validation_results.json").read_text())
    sigs = val["signals"]
    per_wr = {n: float(s.get("win_rate") or 0.5) for n, s in sigs.items() if s.get("recommended")}
    per_n  = {n: int(s.get("trades") or 100)     for n, s in sigs.items() if s.get("recommended")}

    # Stagger 5 sims by 7 days
    starts = [pd.Timestamp("2025-03-26", tz="UTC") + pd.Timedelta(days=7*i) for i in range(5)]
    sims = []

    print(f"\nRunning 5 sims, each 12 months, staggered by 7 days starting Mar 26 2025 ...\n")
    all_strat_trades = defaultdict(list)
    for i, st in enumerate(starts):
        en = st + pd.Timedelta(days=WIN_DAYS)
        label = f"Sim {i+1}: {st.date()}"
        taken = gather_trades(st, en)
        if not taken:
            print(f"  {label}: NO TRADES IN WINDOW"); continue
        merged = merge_macro(taken)
        result = simulate_one(merged, label, per_wr, per_n)
        sims.append(result)
        # Strategy stats per sim
        for log in result["trade_log"]:
            if log.get("blew_up"): continue
            all_strat_trades[log["name"]].append({"sim": label, "pnl": log["pnl"]})
        bal = result["ending_balance"]
        print(f"  {label}  →  ${bal:,.0f}  ({(bal-START_BAL)/START_BAL*100:+.1f}%)  "
              f"trades={result['n_trades']}  WR={result['win_rate']*100:.1f}%  "
              f"{'BLOWN' if result['blown'] else ''}")

    # Strategy summary across all sims
    weeks_per_sim = WIN_DAYS / 7
    months_per_sim = WIN_DAYS / 30.44
    strat_rows = []
    for name, trades in all_strat_trades.items():
        n = len(trades)
        n_per_sim = n / len(sims)
        side = "?"
        for s in sims:
            for log in s["trade_log"]:
                if log["name"] == name and not log.get("blew_up"):
                    side = log["side"]; break
            if side != "?": break
        wins = sum(1 for t in trades if t["pnl"] > 0)
        wr = wins / max(1, n)
        avg_pnl = np.mean([t["pnl"] for t in trades]) if trades else 0
        strat_rows.append({
            "name": name, "side": side,
            "n_trades": n_per_sim,
            "trades_per_week": n_per_sim / weeks_per_sim,
            "trades_per_month": n_per_sim / months_per_sim,
            "win_rate": wr, "avg_pnl": avg_pnl,
        })
    strat_summary = pd.DataFrame(strat_rows)

    # Save JSON
    OUT_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sims": [{k: v for k, v in s.items() if k != "trade_log"} for s in sims],
        "n_sims": len(sims), "starts": [s.isoformat() for s in starts],
        "strat_summary": strat_summary.to_dict("records"),
    }, indent=2, default=str))

    # Build HTML
    window = (str(starts[0].date()), str((starts[0] + pd.Timedelta(days=WIN_DAYS)).date()))
    html = build_html(sims, strat_summary, window)
    OUT_HTML.write_text(html)
    print(f"\n  Wrote -> {OUT_JSON.relative_to(PROJECT_ROOT)}")
    print(f"  Wrote -> {OUT_HTML.relative_to(PROJECT_ROOT)}  ({OUT_HTML.stat().st_size/1024:.0f} KB)")

    # Headline summary
    print("\n" + "=" * 70)
    print("HEADLINE")
    print("=" * 70)
    n_blown = sum(1 for s in sims if s["blown"])
    n_pos = sum(1 for s in sims if s["ending_balance"] - START_BAL > 0)
    pnls = [s["ending_balance"] - START_BAL for s in sims]
    print(f"  Funded account WR:  {n_pos}/{len(sims)} = {n_pos/len(sims)*100:.0f}%")
    print(f"  Blow-ups:           {n_blown}/{len(sims)}")
    print(f"  Median P&L:         ${np.median(pnls):,.0f}  ({np.median(pnls)/START_BAL*100:+.1f}%)")
    print(f"  Best:               ${max(pnls):,.0f}")
    print(f"  Worst:              ${min(pnls):,.0f}")
    print(f"  Avg per-trade WR:   {np.mean([s['win_rate'] for s in sims if s['n_trades']>0])*100:.1f}%")


if __name__ == "__main__":
    main()
