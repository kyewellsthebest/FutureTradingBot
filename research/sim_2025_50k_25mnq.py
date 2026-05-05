"""
Detailed 2025 Simulation — ALL 119 user-pass v11 strategies on 50K Lucid Pro
Funded, 25 MNQ position size.

Window: 2025-01-01 → 2026-01-01 (1 full year)
Granularity: 5-min bars (same as mining)
Execution: First-fire-wins multiplexing across all 119 strategies, with
  one-position-at-a-time, max_hold lockout, post-loss cooldown, DLL,
  Lucid trail (locks at $50K when balance hits $51K), adaptive sizing
  near trail.

Outputs detailed statistics:
  * Total trades, win rate, profit factor
  * Monthly P&L breakdown
  * Equity curve
  * Time to first $1K, $5K, $10K profit (from start)
  * Time to bust (if applicable)
  * Per-strategy contribution
  * Funded pass rate from 100 MC trials starting at random dates in 2025
"""
from __future__ import annotations
import json
import logging
import random
import sys
from pathlib import Path
from typing import Optional
from collections import defaultdict
import io
import base64

import numpy as np
import pandas as pd

from research.pattern_miner_v6 import (
    build_v6_features, label_strategy, StrategyDef, MNQ_DPP, COMM_PER,
)
from research.pattern_miner_v7 import build_v7_extras
from research.pattern_miner_v8 import build_v8_extras
from research.pattern_miner_v9 import build_v9_extras
from research.pattern_miner_v11 import build_v11_extras, make_v11_detector_dicts
from research.local_data_loader import (
    load_daily, load_intraday_1min, load_intraday_5min, load_vix_5min,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
logger = logging.getLogger("sim_2025")

# === Configuration ===
INITIAL_BALANCE = 50000.0
INITIAL_TRAIL = 48000.0
DLL = 1200.0
TRAIL_DROP = 2000.0
TRAIL_LOCK_AT = 51000.0
TRAIL_LOCKED_FLOOR = 50000.0

BASE_SIZE = 25      # MNQ contracts (per user request)
COOLDOWN_BARS = 5

SIM_START = pd.Timestamp("2025-01-01", tz="UTC")
SIM_END = pd.Timestamp("2026-01-01", tz="UTC")

FEE_PER_ATTEMPT = 165.0


def adaptive_qty_factor(buffer: float) -> float:
    """Buffer-based scaling factor (relative to 50K account)."""
    if buffer < 200:    return 0.0
    if buffer < 500:    return 0.20
    if buffer < 1000:   return 0.40
    if buffer < 2000:   return 0.60
    if buffer < 4000:   return 0.85
    return 1.0


def build_signal_universe(strategies: list[dict]):
    """Build chronological universe of all signals across given strategies."""
    logger.info("Loading data + features (one-time)...")
    nq_5m = load_intraday_5min("nq")
    nq_1m = load_intraday_1min("nq")
    daily = load_daily("nq")
    es_5m = load_intraday_5min("es")
    rty_5m = load_intraday_5min("rty")
    vix_5m = load_vix_5min()
    for df in (nq_5m, nq_1m, daily, es_5m, rty_5m, vix_5m):
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")

    F = build_v6_features(nq_5m, daily, es_5m, rty_5m, vix_5m)
    F = build_v7_extras(F, nq_5m, es_5m, vix_5m)
    F = build_v8_extras(F, nq_5m, daily)
    F = build_v9_extras(F, nq_5m, daily, rty_5m)
    F = build_v11_extras(F, nq_5m, es_5m)

    contexts_d, triggers_d = make_v11_detector_dicts(F)

    logger.info(f"Labeling {len(strategies)} strategies...")
    all_sigs = []
    for i, s in enumerate(strategies):
        if i % 20 == 0:
            logger.info(f"  {i+1}/{len(strategies)}...")
        strat = StrategyDef(name=s["name"], side=s["side"], contexts=s["contexts"],
                              trigger=s["trigger"], context_window_bars=5,
                              stop_atr=s["stop_atr"], target_atr=s["target_atr"],
                              max_hold_min=s["max_hold_min"])
        try:
            tr = label_strategy(F, nq_5m, nq_1m, daily, strat, contexts_d, triggers_d)
        except Exception:
            continue
        if tr.empty:
            continue
        tr = tr.copy()
        tr["name"] = s["name"]
        tr["side"] = s["side"]
        tr["max_hold_min"] = s["max_hold_min"]
        ets = pd.to_datetime(tr["entry_ts"])
        if ets.dt.tz is None:
            ets = ets.dt.tz_localize("UTC")
        tr["entry_ts"] = ets
        all_sigs.append(tr)
    sigs = pd.concat(all_sigs, ignore_index=True)
    sigs = sigs.sort_values("entry_ts").reset_index(drop=True)
    logger.info(f"Total signals: {len(sigs)}")
    return sigs


def run_sim(sigs: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp,
              base_size: int, capture_trades: bool = True) -> dict:
    """Run a single funded-account simulation. Returns rich state."""
    balance = INITIAL_BALANCE
    trail = INITIAL_TRAIL
    daily_pnl = 0.0
    current_session = None
    last_exit_ts: Optional[pd.Timestamp] = None
    cooldown_until: Optional[pd.Timestamp] = None
    halted = False
    halt_ts = None
    halt_reason = ""
    trades = []
    equity_curve = [(start_ts, balance)]
    daily_pnl_log = {}
    strat_pnl = defaultdict(lambda: {"n": 0, "wins": 0, "pnl": 0.0})
    high_water = balance
    max_drawdown = 0.0
    # Time-to-milestone tracking
    times_to = {"first_profit": None, "1k": None, "5k": None, "10k": None,
                  "first_loss_day": None}

    window = sigs[(sigs["entry_ts"] >= start_ts) & (sigs["entry_ts"] <= end_ts)]
    n_signals = len(window)
    n_skipped_position = 0
    n_skipped_cooldown = 0
    n_skipped_dll = 0

    for _, sig in window.iterrows():
        if halted:
            break
        sig_ts = sig["entry_ts"]
        sess = sig_ts.tz_convert("America/New_York").date()
        if current_session != str(sess):
            current_session = str(sess)
            daily_pnl = 0.0

        if last_exit_ts is not None and sig_ts < last_exit_ts:
            n_skipped_position += 1
            continue
        if cooldown_until is not None and sig_ts < cooldown_until:
            n_skipped_cooldown += 1
            continue
        if daily_pnl <= -DLL:
            n_skipped_dll += 1
            continue

        buffer = balance - trail
        factor = adaptive_qty_factor(buffer)
        qty = max(1, int(base_size * factor)) if factor > 0 else 0
        if qty == 0:
            continue

        max_hold = int(sig.get("max_hold_min", 75))
        pts = float(sig.get("pts", 0))
        pnl = pts * MNQ_DPP * qty - COMM_PER * 2 * qty

        # DLL cap
        if daily_pnl + pnl < -DLL:
            pnl = -DLL - daily_pnl

        balance += pnl
        daily_pnl += pnl
        if balance > high_water:
            high_water = balance
        dd = high_water - balance
        if dd > max_drawdown:
            max_drawdown = dd

        # Trail update
        if balance >= TRAIL_LOCK_AT:
            trail = max(trail, TRAIL_LOCKED_FLOOR)
        else:
            trail = max(trail, balance - TRAIL_DROP)

        # Cooldown
        last_exit_ts = sig_ts + pd.Timedelta(minutes=max_hold)
        if pnl < 0:
            cooldown_until = last_exit_ts + pd.Timedelta(minutes=25)

        # Trail bust
        if balance < trail:
            halted = True
            halt_ts = sig_ts
            halt_reason = f"trail bust at ${balance:,.0f} < ${trail:,.0f}"

        net = balance - INITIAL_BALANCE
        if times_to["first_profit"] is None and net > 0:
            times_to["first_profit"] = (sig_ts - start_ts).total_seconds() / 86400
        if times_to["1k"] is None and net >= 1000:
            times_to["1k"] = (sig_ts - start_ts).total_seconds() / 86400
        if times_to["5k"] is None and net >= 5000:
            times_to["5k"] = (sig_ts - start_ts).total_seconds() / 86400
        if times_to["10k"] is None and net >= 10000:
            times_to["10k"] = (sig_ts - start_ts).total_seconds() / 86400

        if capture_trades:
            trades.append({
                "ts": sig_ts.isoformat(),
                "strategy": sig["name"],
                "side": sig["side"],
                "qty": qty,
                "pts": pts,
                "pnl": pnl,
                "balance": balance,
                "trail": trail,
            })
        equity_curve.append((sig_ts, balance))
        daily_pnl_log[str(sess)] = daily_pnl_log.get(str(sess), 0.0) + pnl
        strat_pnl[sig["name"]]["n"] += 1
        strat_pnl[sig["name"]]["pnl"] += pnl
        if pnl > 0:
            strat_pnl[sig["name"]]["wins"] += 1

    n = len(trades) if capture_trades else None
    if capture_trades:
        wins = sum(1 for t in trades if t["pnl"] > 0)
        gross_w = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_l = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    else:
        wins = 0; gross_w = 0; gross_l = 0; n = 0

    return {
        "halted": halted,
        "halt_ts": halt_ts.isoformat() if halt_ts else None,
        "halt_reason": halt_reason,
        "balance": balance,
        "high_water": high_water,
        "max_drawdown": max_drawdown,
        "n_signals_in_window": n_signals,
        "n_trades": n,
        "n_wins": wins,
        "win_rate": wins / n if n else 0,
        "gross_win": gross_w,
        "gross_loss": gross_l,
        "profit_factor": gross_w / gross_l if gross_l > 0 else 999,
        "net_profit": balance - INITIAL_BALANCE,
        "skipped_position": n_skipped_position,
        "skipped_cooldown": n_skipped_cooldown,
        "skipped_dll": n_skipped_dll,
        "trades": trades if capture_trades else None,
        "equity_curve": [(ts.isoformat() if hasattr(ts, "isoformat") else str(ts), b)
                            for ts, b in equity_curve],
        "daily_pnl": daily_pnl_log,
        "strategy_contribution": {k: dict(v) for k, v in strat_pnl.items()},
        "times_to": times_to,
    }


def monte_carlo_2025(sigs, base_size: int, n_trials: int = 100):
    """MC funded-account pass rate within 2025."""
    rng = random.Random(7)
    # Random start dates in 2025, 6-month run
    start_pool = pd.date_range("2025-01-01", "2025-06-30", freq="3D", tz="UTC")
    starts = [start_pool[rng.randint(0, len(start_pool)-1)] for _ in range(n_trials)]
    runs = []
    bust_days = []
    for sd in starts:
        ed = sd + pd.Timedelta(days=180)
        r = run_sim(sigs, sd, ed, base_size, capture_trades=False)
        runs.append(r)
        if r["halted"] and r["halt_ts"]:
            bust_days.append((pd.Timestamp(r["halt_ts"]) - sd).total_seconds() / 86400)
    n_passed = sum(1 for r in runs if not r["halted"])
    survivors = [r for r in runs if not r["halted"]]
    return {
        "n_trials": n_trials,
        "pass_rate": n_passed / n_trials,
        "avg_survivor_profit": np.mean([r["net_profit"] for r in survivors]) if survivors else 0,
        "median_survivor_profit": np.median([r["net_profit"] for r in survivors]) if survivors else 0,
        "max_survivor_profit": max([r["net_profit"] for r in survivors]) if survivors else 0,
        "avg_bust_days": np.mean(bust_days) if bust_days else 0,
        "median_bust_days": np.median(bust_days) if bust_days else 0,
        "ev_per_attempt": (n_passed / n_trials) * (np.mean([r["net_profit"] for r in survivors]) if survivors else 0)
                              - (1 - n_passed / n_trials) * FEE_PER_ATTEMPT,
    }


def fig_b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=85)
    buf.seek(0)
    s = base64.b64encode(buf.read()).decode()
    return s


def build_html(deterministic, mc):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # 1. Equity curve
    eq = deterministic["equity_curve"]
    ts = [pd.to_datetime(t).tz_convert(None) if pd.to_datetime(t).tz else pd.to_datetime(t) for t, _ in eq]
    bs = [b for _, b in eq]
    fig, ax = plt.subplots(figsize=(13, 5))
    color = "darkred" if deterministic["halted"] else "green"
    ax.plot(ts, bs, color=color, linewidth=1.5)
    ax.axhline(INITIAL_BALANCE, color="gray", linestyle=":", label="Start $50K")
    ax.axhline(INITIAL_TRAIL, color="red", linestyle="--", alpha=0.5, label="Initial trail $48K")
    ax.axhline(TRAIL_LOCKED_FLOOR, color="orange", linestyle="--", alpha=0.5, label="Locked trail $50K")
    ax.set_title(f"50K Lucid @ {BASE_SIZE} MNQ — All {N_STRATS} v11 strategies — 2025")
    ax.set_ylabel("Balance ($)")
    ax.legend(loc="best", fontsize=9)
    ax.grid(alpha=0.3)
    img_eq = fig_b64(fig); plt.close(fig)

    # 2. Monthly P&L
    daily_pnl = deterministic["daily_pnl"]
    df = pd.DataFrame(list(daily_pnl.items()), columns=["date", "pnl"])
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M")
    monthly = df.groupby("month")["pnl"].agg(["sum", "count"])
    fig, ax = plt.subplots(figsize=(13, 4))
    colors = ["green" if v > 0 else "red" for v in monthly["sum"]]
    ax.bar(range(len(monthly)), monthly["sum"], color=colors)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels([str(m) for m in monthly.index], rotation=45)
    ax.set_title("Monthly P&L breakdown — 2025")
    ax.set_ylabel("$")
    ax.grid(alpha=0.3)
    img_mo = fig_b64(fig); plt.close(fig)

    monthly_rows = ""
    for m, row in monthly.iterrows():
        c = "green" if row["sum"] > 0 else "red"
        monthly_rows += f"<tr><td>{m}</td><td>{int(row['count'])}</td><td style='color:{c}'>${row['sum']:,.0f}</td></tr>"

    # 3. Top 30 strategies by contribution
    sc = deterministic["strategy_contribution"]
    sc_list = sorted(sc.items(), key=lambda x: -x[1]["pnl"])[:30]
    strat_rows = ""
    for name, info in sc_list:
        c = "green" if info["pnl"] > 0 else "red"
        wr = (info["wins"] / info["n"] * 100) if info["n"] else 0
        strat_rows += f"<tr><td><code>{name[:60]}</code></td><td>{info['n']}</td><td>{wr:.1f}%</td><td style='color:{c}'>${info['pnl']:,.0f}</td></tr>"

    # 4. Trade frequency
    n_trades = deterministic["n_trades"]
    n_sigs = deterministic["n_signals_in_window"]
    tt = deterministic["times_to"]
    halt_str = ""
    if deterministic["halted"]:
        halt_str = f"<div class='warning'><b>Account HALTED:</b> {deterministic['halt_reason']} on {pd.to_datetime(deterministic['halt_ts']).date()}</div>"

    times_html = ""
    for k in ["first_profit", "1k", "5k", "10k"]:
        v = tt.get(k)
        if v is None:
            times_html += f"<tr><td>{k}</td><td>NEVER REACHED</td></tr>"
        else:
            days = float(v)
            wks = days / 7
            times_html += f"<tr><td>Time to {k}</td><td>{days:.1f} days ({wks:.1f} weeks)</td></tr>"

    # MC summary
    mc_html = f"""
<table>
<tr><th>Trials</th><td>{mc['n_trials']}</td></tr>
<tr><th>Pass rate</th><td><b>{mc['pass_rate']*100:.0f}%</b></td></tr>
<tr><th>Median survivor profit (180 days)</th><td>${mc['median_survivor_profit']:,.0f}</td></tr>
<tr><th>Average survivor profit</th><td>${mc['avg_survivor_profit']:,.0f}</td></tr>
<tr><th>Max survivor profit</th><td>${mc['max_survivor_profit']:,.0f}</td></tr>
<tr><th>Avg time to bust (when failed)</th><td>{mc['avg_bust_days']:.1f} days</td></tr>
<tr><th>EV per attempt</th><td><b style='color:{"green" if mc["ev_per_attempt"]>0 else "red"}'>${mc['ev_per_attempt']:,.0f}</b></td></tr>
</table>
"""

    html = f"""
<!DOCTYPE html>
<html>
<head>
<title>50K Lucid @ 25 MNQ — All 119 Strategies — 2025 Sim</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#fafafa; padding:20px; max-width:1280px; margin:0 auto; }}
h1, h2, h3 {{ color: #222; }}
h1 {{ border-bottom: 2px solid #1976d2; padding-bottom: 10px; }}
.metric {{ display:inline-block; margin:5px 15px 5px 0; padding:8px 12px; background:white; border:1px solid #ddd; border-radius:4px; }}
.metric .lbl {{ font-size:11px; color:#888; text-transform:uppercase; }}
.metric .val {{ font-size:20px; font-weight:600; }}
table {{ border-collapse: collapse; width: 100%; background:white; font-size:13px; }}
th, td {{ padding: 6px 10px; border-bottom:1px solid #eee; text-align:left; }}
th {{ background: #f5f5f5; }}
.section {{ background:white; padding:18px; margin:15px 0; border-radius:6px; border:1px solid #ddd; }}
.warning {{ background: #fee; border-left:4px solid red; padding:10px; margin:10px 0; }}
.callout {{ background:#e8f5e9; border-left:4px solid #4caf50; padding:14px; margin:15px 0; }}
img {{ max-width:100%; border:1px solid #ddd; border-radius:4px; margin:10px 0; }}
code {{ font-size:11px; }}
</style>
</head>
<body>
<h1>50K Lucid Pro Funded — All 119 v11 Strategies — Calendar 2025</h1>

<div class="section">
<h2>Configuration</h2>
<div class="metric"><div class="lbl">Account size</div><div class="val">$50,000</div></div>
<div class="metric"><div class="lbl">Starting trail</div><div class="val">$48,000</div></div>
<div class="metric"><div class="lbl">Daily loss limit</div><div class="val">$1,200</div></div>
<div class="metric"><div class="lbl">Position size</div><div class="val">{BASE_SIZE} MNQ</div></div>
<div class="metric"><div class="lbl">Strategies</div><div class="val">{N_STRATS}</div></div>
<div class="metric"><div class="lbl">Window</div><div class="val">2025-01-01 → 2026-01-01</div></div>
<p>Adaptive sizing reduces qty as buffer-to-trail shrinks. Standard Lucid 50K rules: trail starts at $48K, follows balance high - $2K, locks at $50K when balance reaches $51K. Daily loss limit $1,200.</p>
</div>

<h2>Deterministic 2025 simulation</h2>
{halt_str}

<div class="section">
<h3>Headline numbers</h3>
<div class="metric"><div class="lbl">Candidate signals</div><div class="val">{n_sigs:,}</div></div>
<div class="metric"><div class="lbl">Trades executed</div><div class="val">{n_trades}</div></div>
<div class="metric"><div class="lbl">Win rate</div><div class="val">{deterministic['win_rate']*100:.1f}%</div></div>
<div class="metric"><div class="lbl">Profit factor</div><div class="val">{deterministic['profit_factor']:.2f}</div></div>
<div class="metric"><div class="lbl">Net P&amp;L</div><div class="val" style="color:{'green' if deterministic['net_profit']>0 else 'red'}">${deterministic['net_profit']:+,.0f}</div></div>
<div class="metric"><div class="lbl">Ending balance</div><div class="val">${deterministic['balance']:,.0f}</div></div>
<div class="metric"><div class="lbl">High water</div><div class="val">${deterministic['high_water']:,.0f}</div></div>
<div class="metric"><div class="lbl">Max drawdown</div><div class="val">${deterministic['max_drawdown']:,.0f}</div></div>
</div>

<div class="section">
<h3>Equity curve (account balance)</h3>
<img src="data:image/png;base64,{img_eq}"/>
</div>

<div class="section">
<h3>Monthly P&amp;L</h3>
<img src="data:image/png;base64,{img_mo}"/>
<table><tr><th>Month</th><th>Trades</th><th>P&amp;L</th></tr>{monthly_rows}</table>
</div>

<div class="section">
<h3>Time to milestone (from 2025-01-01)</h3>
<table>{times_html}</table>
</div>

<div class="section">
<h3>Top 30 strategies by P&amp;L contribution</h3>
<table><tr><th>Strategy</th><th>n</th><th>WR</th><th>P&amp;L</th></tr>{strat_rows}</table>
</div>

<div class="section">
<h3>Skip statistics</h3>
<div class="metric"><div class="lbl">Skipped (in position)</div><div class="val">{deterministic['skipped_position']:,}</div></div>
<div class="metric"><div class="lbl">Skipped (cooldown)</div><div class="val">{deterministic['skipped_cooldown']:,}</div></div>
<div class="metric"><div class="lbl">Skipped (DLL hit)</div><div class="val">{deterministic['skipped_dll']:,}</div></div>
</div>

<h2>Funded pass rate (Monte Carlo)</h2>
<div class="callout">
<p>100 funded-account simulations starting at random dates in 2025-H1, each running 180 days. This estimates how often the account would survive long enough to make a profit, given different starting market regimes within 2025.</p>
{mc_html}
</div>

</body>
</html>
"""
    return html


def main():
    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(message)s",
                          handlers=[logging.StreamHandler(sys.stdout)])
    mined = json.load(open(DATA / "mined_v11_patterns.json"))
    user_pass = mined.get("user_passers", [])
    # Use ALL user-pass strategies as user requested
    global N_STRATS
    N_STRATS = len(user_pass)
    logger.info(f"Using ALL {N_STRATS} user-pass v11 strategies")

    sigs = build_signal_universe(user_pass)

    # Save signal universe for inspection
    sigs_summary = {
        "n_signals": len(sigs),
        "n_strategies": N_STRATS,
        "first_signal": sigs["entry_ts"].min().isoformat(),
        "last_signal": sigs["entry_ts"].max().isoformat(),
    }

    # Deterministic full-2025 simulation
    logger.info("Running deterministic 2025 simulation...")
    det = run_sim(sigs, SIM_START, SIM_END, BASE_SIZE, capture_trades=True)
    logger.info(f"  trades={det['n_trades']}, WR={det['win_rate']*100:.1f}%, "
                  f"net=${det['net_profit']:+,.0f}, halted={det['halted']}")

    # Monte Carlo within 2025
    logger.info("Running 100-trial Monte Carlo (random starts in 2025-H1)...")
    mc = monte_carlo_2025(sigs, BASE_SIZE, n_trials=100)
    logger.info(f"  pass_rate={mc['pass_rate']*100:.0f}%, "
                  f"median_profit=${mc['median_survivor_profit']:,.0f}, "
                  f"EV=${mc['ev_per_attempt']:,.0f}")

    out = DATA / "sim_2025_50k_25mnq.json"
    out.write_text(json.dumps({
        "config": {"start": SIM_START.isoformat(), "end": SIM_END.isoformat(),
                    "size": BASE_SIZE, "n_strategies": N_STRATS},
        "signal_universe": sigs_summary,
        "deterministic": det,
        "monte_carlo": mc,
    }, indent=2, default=str))
    logger.info(f"Wrote {out}")

    html = build_html(det, mc)
    html_out = DATA / "sim_2025_50k_25mnq.html"
    html_out.write_text(html)
    logger.info(f"Wrote {html_out}")

    print("\n" + "="*70)
    print("DETERMINISTIC 2025 SIMULATION (50K Lucid, 25 MNQ, all 119 strategies)")
    print("="*70)
    print(f"  Total signals in 2025:    {det['n_signals_in_window']:,}")
    print(f"  Trades executed:          {det['n_trades']}")
    print(f"  Win rate:                 {det['win_rate']*100:.1f}%")
    print(f"  Profit factor:            {det['profit_factor']:.2f}")
    print(f"  Net P&L:                  ${det['net_profit']:+,.0f}")
    print(f"  Ending balance:           ${det['balance']:,.0f}")
    print(f"  High water:               ${det['high_water']:,.0f}")
    print(f"  Max drawdown:             ${det['max_drawdown']:,.0f}")
    print(f"  Halted:                   {det['halted']}")
    if det['halted']:
        print(f"    halt reason:            {det['halt_reason']}")
        print(f"    halt date:              {pd.to_datetime(det['halt_ts']).date()}")
    tt = det["times_to"]
    print(f"  Time to first profit:     {tt['first_profit']:.1f} days" if tt['first_profit'] else "  Time to first profit:     NEVER")
    print(f"  Time to +$1K:             {tt['1k']:.1f} days" if tt['1k'] else "  Time to +$1K:             NEVER")
    print(f"  Time to +$5K:             {tt['5k']:.1f} days" if tt['5k'] else "  Time to +$5K:             NEVER")
    print(f"  Time to +$10K:            {tt['10k']:.1f} days" if tt['10k'] else "  Time to +$10K:            NEVER")
    print()
    print(f"MONTE CARLO (100 random starts in 2025-H1, 180-day runs)")
    print(f"  Pass rate:                {mc['pass_rate']*100:.0f}%")
    print(f"  Median survivor profit:   ${mc['median_survivor_profit']:,.0f}")
    print(f"  Avg survivor profit:      ${mc['avg_survivor_profit']:,.0f}")
    print(f"  Max survivor profit:      ${mc['max_survivor_profit']:,.0f}")
    print(f"  Avg time to bust:         {mc['avg_bust_days']:.1f} days")
    print(f"  EV per attempt (after $165 fee): ${mc['ev_per_attempt']:,.0f}")


if __name__ == "__main__":
    main()
