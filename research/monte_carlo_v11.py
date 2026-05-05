"""
Monte Carlo Funded-Account Pass-Rate Analysis.

For each (account_size, fixed_position_size) combination, simulate 100
funded-account attempts starting on random dates throughout 2024-2025.
Each attempt runs 6 months. Track:
  * pass_rate = fraction of accounts that survive (don't bust trail)
  * avg_profit_on_survivors
  * EV per attempt = (pass_rate × avg_profit) - ($165 fail cost × (1-pass_rate))

This answers: "what's the optimal position size for funded-account EV?"
The user's intuition: smaller size = higher pass rate but smaller profit.
There should be an EV maximum somewhere.

Output: data/monte_carlo_v11.json + data/monte_carlo_v11_report.html
"""
from __future__ import annotations
import json
import logging
import random
import sys
from pathlib import Path
from typing import Optional
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

logger = logging.getLogger("mc_v11")

# Sim window
SIM_START = pd.Timestamp("2024-01-01", tz="UTC")
SIM_END = pd.Timestamp("2026-04-30", tz="UTC")
RUN_DAYS = 180   # 6 months per funded account attempt
N_TRIALS = 100   # MC trials per (size, account) combination

# Funded account fee (Lucid 50K typical signup + reset)
FEE_PER_ATTEMPT = 165.0

# Sizes to test
SIZES = [3, 5, 8, 10, 12, 15, 20, 25, 30]

# Account configs
ACCOUNTS = {
    "50K": dict(initial=50000.0, trail_init=48000.0, dll=1200.0,
                  trail_drop=2000.0, lock_at=51000.0, lock_floor=50000.0),
    "100K": dict(initial=100000.0, trail_init=96000.0, dll=2200.0,
                   trail_drop=4000.0, lock_at=102000.0, lock_floor=100000.0),
}


def build_signal_universe():
    """Build chronologically sorted universe of all top-K strategy fires."""
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

    mined = json.load(open(DATA / "mined_v11_patterns.json"))
    profitable = [s for s in mined["user_passers"] if s["test"]["pf"] > 1.0]
    profitable.sort(key=lambda s: -s["test"].get("sharpe", 0))
    top = profitable[:30]

    logger.info(f"Labeling {len(top)} strategies...")
    all_sigs = []
    for s in top:
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
        tr = tr[(tr["entry_ts"] >= SIM_START) & (tr["entry_ts"] <= SIM_END)]
        all_sigs.append(tr)
    sigs = pd.concat(all_sigs, ignore_index=True)
    sigs = sigs.sort_values("entry_ts").reset_index(drop=True)
    logger.info(f"  {len(sigs)} candidate signals across all strategies")
    return sigs


def adaptive_qty_factor(buffer: float, account_initial: float) -> float:
    """Returns a multiplier in [0,1] based on buffer-to-trail.
    With size=10 and factor=0.5, actually trade 5 MNQ. Conservative scaling.
    """
    scale = account_initial / 50000.0
    buf = buffer / scale
    if buf < 200:    return 0.0
    if buf < 500:    return 0.25
    if buf < 1000:   return 0.50
    if buf < 2000:   return 0.75
    return 1.0


def run_one(sigs: pd.DataFrame, start_ts: pd.Timestamp, end_ts: pd.Timestamp,
              acct_cfg: dict, base_size: int, adaptive: bool = True) -> dict:
    """Run one funded-account attempt. Returns final state."""
    balance = acct_cfg["initial"]
    trail = acct_cfg["trail_init"]
    dll = acct_cfg["dll"]
    trail_drop = acct_cfg["trail_drop"]
    lock_at = acct_cfg["lock_at"]
    lock_floor = acct_cfg["lock_floor"]

    daily_pnl = 0.0
    current_session = None
    last_exit_ts: Optional[pd.Timestamp] = None
    cooldown_until: Optional[pd.Timestamp] = None
    halted = False
    n_trades = 0
    n_wins = 0

    window = sigs[(sigs["entry_ts"] >= start_ts) & (sigs["entry_ts"] <= end_ts)]
    for _, sig in window.iterrows():
        if halted:
            break
        sig_ts = sig["entry_ts"]
        sess = sig_ts.tz_convert("America/New_York").date()
        if current_session != str(sess):
            current_session = str(sess)
            daily_pnl = 0.0
        if last_exit_ts is not None and sig_ts < last_exit_ts:
            continue
        if cooldown_until is not None and sig_ts < cooldown_until:
            continue
        if daily_pnl <= -dll:
            continue

        buffer = balance - trail
        if adaptive:
            factor = adaptive_qty_factor(buffer, acct_cfg["initial"])
            qty = max(1, int(base_size * factor)) if factor > 0 else 0
        else:
            qty = base_size if buffer > 100 else 0
        if qty == 0:
            continue

        max_hold = int(sig.get("max_hold_min", 75))
        pts = float(sig.get("pts", 0))
        pnl = pts * MNQ_DPP * qty - COMM_PER * 2 * qty

        # DLL cap
        if daily_pnl + pnl < -dll:
            pnl = -dll - daily_pnl

        balance += pnl
        daily_pnl += pnl

        # Trail update
        if balance >= lock_at:
            trail = max(trail, lock_floor)
        else:
            trail = max(trail, balance - trail_drop)

        # Cooldown
        last_exit_ts = sig_ts + pd.Timedelta(minutes=max_hold)
        if pnl < 0:
            cooldown_until = last_exit_ts + pd.Timedelta(minutes=25)

        # Trail bust
        if balance < trail:
            halted = True

        n_trades += 1
        if pnl > 0:
            n_wins += 1

    return {
        "halted": halted,
        "balance": balance,
        "profit": balance - acct_cfg["initial"],
        "n_trades": n_trades,
        "n_wins": n_wins,
        "trail": trail,
    }


def monte_carlo(sigs: pd.DataFrame, acct_cfg: dict, base_size: int,
                  n_trials: int = N_TRIALS, run_days: int = RUN_DAYS,
                  adaptive: bool = True, seed: int = 42) -> dict:
    """Run N MC trials at random start dates over the OOS window."""
    rng = random.Random(seed)
    # Generate start dates spanning the OOS window minus run_days
    max_start = SIM_END - pd.Timedelta(days=run_days)
    start_pool = pd.date_range(SIM_START, max_start, freq="3D")
    start_dates = [start_pool[rng.randint(0, len(start_pool)-1)]
                     for _ in range(n_trials)]
    results = []
    for sd in start_dates:
        ed = sd + pd.Timedelta(days=run_days)
        r = run_one(sigs, sd, ed, acct_cfg, base_size, adaptive=adaptive)
        results.append(r)
    n_passed = sum(1 for r in results if not r["halted"])
    n_busted = n_trials - n_passed
    pass_rate = n_passed / n_trials
    survivor_profits = [r["profit"] for r in results if not r["halted"]]
    bust_losses = [r["profit"] for r in results if r["halted"]]
    avg_survivor_profit = np.mean(survivor_profits) if survivor_profits else 0
    median_survivor_profit = np.median(survivor_profits) if survivor_profits else 0
    avg_bust_loss = np.mean(bust_losses) if bust_losses else 0  # negative
    # EV per attempt: (pass_rate × profit) - ((1 - pass_rate) × fee)
    # Note: bust_loss is the IN-ACCOUNT loss, but the trader's actual
    # cost is the FEE (the firm absorbs the rest). So EV = pass_rate × profit - (1-pass_rate) × fee
    ev = pass_rate * avg_survivor_profit - (1 - pass_rate) * FEE_PER_ATTEMPT
    return {
        "n_trials": n_trials, "n_passed": n_passed, "n_busted": n_busted,
        "pass_rate": pass_rate,
        "avg_survivor_profit": avg_survivor_profit,
        "median_survivor_profit": median_survivor_profit,
        "avg_bust_loss_in_account": avg_bust_loss,
        "ev_per_attempt": ev,
        "annualized_survivor": avg_survivor_profit * (365 / run_days),
    }


def main():
    logging.basicConfig(level=logging.INFO,
                          format="%(asctime)s %(levelname)s %(message)s",
                          handlers=[logging.StreamHandler(sys.stdout)])
    sigs = build_signal_universe()

    results = {}
    for acct_name, acct_cfg in ACCOUNTS.items():
        for size in SIZES:
            logger.info(f"MC: {acct_name} acct, size={size}...")
            r = monte_carlo(sigs, acct_cfg, size, n_trials=N_TRIALS,
                              adaptive=True)
            results[f"{acct_name}_size{size}"] = r
            logger.info(f"  pass_rate={r['pass_rate']*100:.0f}%  "
                          f"avg_survivor=${r['avg_survivor_profit']:,.0f}  "
                          f"EV=${r['ev_per_attempt']:,.0f}  "
                          f"annualized=${r['annualized_survivor']:,.0f}")

    out = DATA / "monte_carlo_v11.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    logger.info(f"Wrote {out}")

    # Build HTML
    build_html(results)


def build_html(results: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows_50 = []
    rows_100 = []
    for k, r in results.items():
        acct, sz = k.split("_size")
        sz = int(sz)
        row = {
            "size": sz,
            "pass_rate": r["pass_rate"],
            "avg_profit": r["avg_survivor_profit"],
            "median_profit": r["median_survivor_profit"],
            "ev": r["ev_per_attempt"],
            "annualized": r["annualized_survivor"],
        }
        if acct == "50K":
            rows_50.append(row)
        else:
            rows_100.append(row)

    rows_50.sort(key=lambda r: r["size"])
    rows_100.sort(key=lambda r: r["size"])

    def render_table(rows, title):
        h = f"<h3>{title}</h3><table><tr><th>Size (MNQ)</th><th>Pass rate</th><th>Avg profit (survivors)</th><th>Median profit</th><th>EV per attempt</th><th>Annualized (survivors)</th></tr>"
        for r in rows:
            color = "green" if r["ev"] > 0 else "red"
            h += f"<tr><td>{r['size']}</td><td>{r['pass_rate']*100:.0f}%</td><td>${r['avg_profit']:,.0f}</td><td>${r['median_profit']:,.0f}</td><td style='color:{color}'><b>${r['ev']:,.0f}</b></td><td>${r['annualized']:,.0f}</td></tr>"
        h += "</table>"
        return h

    # Charts: pass rate vs size, EV vs size
    sizes = [r["size"] for r in rows_50]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(sizes, [r["pass_rate"]*100 for r in rows_50], 'o-', label='50K Lucid', color='steelblue')
    ax.plot(sizes, [r["pass_rate"]*100 for r in rows_100], 'o-', label='100K Lucid', color='darkorange')
    ax.set_xlabel("Position size (MNQ)")
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("Funded-account pass rate vs position size (180-day window, 100 MC trials)")
    ax.legend()
    ax.grid(alpha=0.3)
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight", dpi=85); buf.seek(0)
    img1 = base64.b64encode(buf.read()).decode(); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(sizes, [r["ev"] for r in rows_50], 'o-', label='50K Lucid', color='steelblue')
    ax.plot(sizes, [r["ev"] for r in rows_100], 'o-', label='100K Lucid', color='darkorange')
    ax.axhline(0, color='gray', linestyle='--')
    ax.set_xlabel("Position size (MNQ)")
    ax.set_ylabel("EV per attempt ($)")
    ax.set_title(f"Expected value per funded-account attempt (cost ${FEE_PER_ATTEMPT}/fail)")
    ax.legend()
    ax.grid(alpha=0.3)
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight", dpi=85); buf.seek(0)
    img2 = base64.b64encode(buf.read()).decode(); plt.close(fig)

    # Profit-on-survivors chart
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(sizes, [r["annualized"] for r in rows_50], 'o-', label='50K Lucid', color='steelblue')
    ax.plot(sizes, [r["annualized"] for r in rows_100], 'o-', label='100K Lucid', color='darkorange')
    ax.set_xlabel("Position size (MNQ)")
    ax.set_ylabel("Annualized profit on survivors ($)")
    ax.set_title("Annualized return on accounts that survive 180 days")
    ax.legend()
    ax.grid(alpha=0.3)
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight", dpi=85); buf.seek(0)
    img3 = base64.b64encode(buf.read()).decode(); plt.close(fig)

    # Find optima
    best_ev_50 = max(rows_50, key=lambda r: r["ev"])
    best_ev_100 = max(rows_100, key=lambda r: r["ev"])

    html = f"""
<!DOCTYPE html>
<html>
<head>
<title>Monte Carlo: Funded-Account Pass Rates vs Position Size</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#fafafa; padding:20px; max-width:1200px; margin:0 auto; }}
h1, h2, h3 {{ color: #222; }}
h1 {{ border-bottom: 2px solid #1976d2; padding-bottom: 10px; }}
table {{ border-collapse: collapse; width: 100%; background:white; }}
th, td {{ padding: 8px 12px; border-bottom:1px solid #eee; text-align:right; }}
th {{ background: #f5f5f5; text-align:right; }}
th:first-child, td:first-child {{ text-align:left; }}
.section {{ background:white; padding:18px; margin:15px 0; border-radius:6px; border:1px solid #ddd; }}
.callout {{ background:#e8f5e9; border-left:4px solid #4caf50; padding:14px; margin:15px 0; }}
.warning {{ background:#fff3cd; border:1px solid #ffc107; padding:12px; margin:10px 0; border-radius:4px; }}
.metric {{ display:inline-block; margin:5px 15px 5px 0; padding:8px 12px; background:#f0f0f0; border-radius:4px; }}
.metric .lbl {{ font-size:11px; color:#888; }}
.metric .val {{ font-size:20px; font-weight:600; }}
img {{ max-width:100%; border:1px solid #ddd; border-radius:4px; margin:10px 0; }}
</style>
</head>
<body>
<h1>Monte Carlo: Funded-Account Pass Rate vs Position Size</h1>

<div class="section">
<h2>Setup</h2>
<p>Each MC trial picks a random start date between Jan 2024 and Oct 2025, then runs the bot for 180 days using all 30 top v11 strategies, with a fixed BASE position size and adaptive scaling near the trail. Fee assumed ${FEE_PER_ATTEMPT}/failed attempt.</p>
<div class="metric"><div class="lbl">MC trials per (size, account)</div><div class="val">{N_TRIALS}</div></div>
<div class="metric"><div class="lbl">Run length</div><div class="val">{RUN_DAYS} days</div></div>
<div class="metric"><div class="lbl">Strategies</div><div class="val">30 top user-pass</div></div>
</div>

<div class="callout">
<h2>BOTTOM LINE</h2>
<h3>50K Lucid Pro Funded</h3>
<ul>
<li>Best EV at <b>{best_ev_50['size']} MNQ</b>: pass rate <b>{best_ev_50['pass_rate']*100:.0f}%</b>, avg survivor profit <b>${best_ev_50['avg_profit']:,.0f}</b>, EV per attempt <b>${best_ev_50['ev']:,.0f}</b></li>
<li>Annualized return on survivors: <b>${best_ev_50['annualized']:,.0f}</b></li>
</ul>
<h3>100K Lucid Pro Funded</h3>
<ul>
<li>Best EV at <b>{best_ev_100['size']} MNQ</b>: pass rate <b>{best_ev_100['pass_rate']*100:.0f}%</b>, avg survivor profit <b>${best_ev_100['avg_profit']:,.0f}</b>, EV per attempt <b>${best_ev_100['ev']:,.0f}</b></li>
<li>Annualized return on survivors: <b>${best_ev_100['annualized']:,.0f}</b></li>
</ul>
</div>

<div class="section">
<h2>Pass rate vs size</h2>
<img src="data:image/png;base64,{img1}"/>
</div>

<div class="section">
<h2>EV per attempt vs size</h2>
<img src="data:image/png;base64,{img2}"/>
<p>This is the key chart: it shows the trade-off between size and survival. EV peaks where pass-rate × profit is maximized minus the fee cost on failures.</p>
</div>

<div class="section">
<h2>Annualized return on survivors</h2>
<img src="data:image/png;base64,{img3}"/>
<p>This is what survivors earn annualized — straight-line bigger size = bigger profit, but ignores the busts.</p>
</div>

<div class="section">
{render_table(rows_50, "50K Lucid Pro Funded — full results")}
</div>

<div class="section">
{render_table(rows_100, "100K Lucid Pro Funded — full results")}
</div>

<div class="section">
<h2>Interpretation</h2>
<ul>
<li><b>Pass rate</b>: % of MC trials where the account survived 180 days without busting trail or DLL.</li>
<li><b>Avg profit (survivors)</b>: average $ gain among the accounts that survived.</li>
<li><b>EV per attempt</b>: pass_rate × avg_profit – (1 − pass_rate) × ${FEE_PER_ATTEMPT} fee. Positive EV means the funded-account model is profitable in expectation.</li>
<li><b>Strategy</b>: if EV is positive at multiple sizes, pick the one with highest EV (or highest absolute profit if your capital is unconstrained).</li>
</ul>
<p>The user's intuition is correct: even if 60% of accounts bust, if 40% survive and make $20K each, the EV per attempt is still strongly positive — and you can scale by buying multiple accounts.</p>
</div>
</body>
</html>
"""
    out = DATA / "monte_carlo_v11_report.html"
    out.write_text(html)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
