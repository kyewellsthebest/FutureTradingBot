"""Broker-realistic execution sim -- models what the bot would ACTUALLY
achieve on a live broker, vs the idealized backtest's idealized fills.

The honest_replay sim assumes:
  - Every detected setup fills at the strategy's intended LIMIT entry
  - Every stop fires at exact stop_px
  - Every target fires at exact target_px

Reality (which user is currently seeing as the paper-vs-broker gap):
  - LIMIT entries miss when price barely touches and bounces (brief touches)
  - LIMIT targets miss for the same reason
  - Stops slip 0-2pt past trigger during fast moves
  - Some signals get rejected by TradersPost (network / age)
  - Duplicate-entry edge cases produce catastrophic outliers

This sim runs the SAME strategy code but applies probabilistic fill
modeling per trade. Output: expected P&L delta, win rate change, and
which mechanism causes the most damage.

Usage:
    python3 research/sim_broker_realistic.py

Compare its output to research/sim_honest_replay.py to see the gap.
"""
from __future__ import annotations
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, "/home/user/HFTBot")
os.environ["FIB_AUTO_DLL"] = "0"

from bot.account_ctx import set_account, get_strategy_params, _LEGACY_DATA
set_account("1")
pf = _LEGACY_DATA / "manual_pause.json"
if pf.exists():
    pf.unlink()

from bot.pullback_strategy import (
    FibStrategyState, on_new_1m_bar, DEFAULT_SIZE,
    COOLDOWN_SECS, MAX_HOLD_SECS, MAX_WAIT_SECS,
)
from research.lucid_guard import LucidState


CSV = "/home/user/HFTBot/data/polygon/NQ_1min.csv"
N_MNQ = 2
COMM_RT = 0.74
MNQ_PER_PT = 2.0
HISTORY_BARS = 240

# -----------------------------------------------------------------
# Broker reality model -- tunable knobs.
# -----------------------------------------------------------------
# LIMIT entry fill probability: model brief touches. The honest sim
# assumes any bar whose range includes pullback_entry results in a fill.
# Reality: thin liquidity at exact level, partial fills, latency =
# misses. Tunable from 0.0 (never fills, no trades) to 1.0 (always
# fills, matches honest sim).
LIMIT_ENTRY_FILL_PROB = 0.85   # 85% fill rate -- reasonable for liquid NQ

# LIMIT target fill probability: same dynamic on the exit side. If the
# tick price brushes target and reverses, our limit may not fill. Bot's
# tick-panic close (within 0.5pt) catches some of these but not all.
LIMIT_TARGET_FILL_PROB = 0.75

# When the target limit doesn't fill, what happens? Three scenarios with
# their probabilities:
#   tick_panic   -- bot's tick-level panic-close fires at target-0.5pt
#                   (caps win at +11.5pt instead of +12pt)
#   reversal     -- price reverses, eventually hits stop (-6pt -> -$24)
#   timeout      -- price stays mid-range until 10min timeout
TARGET_MISS_SCENARIOS = {
    "tick_panic":  0.60,   # 60% caught by tick panic at target-0.5pt
    "reversal":    0.30,   # 30% reverse and stop out
    "timeout":     0.10,   # 10% time out at random mid-range price
}

# Stop slippage in points (slip past trigger before market fills).
# Models thin-book gap during fast moves.
STOP_SLIPPAGE_PTS_MEAN = 0.4   # typical
STOP_SLIPPAGE_PTS_STD = 0.5    # variability

# Signal age rejection probability -- removed in production already
# (was the 5s filter the user disabled), but useful for showing what it
# was costing.
SIGNAL_REJECT_PROB = 0.00   # 0 after the fix; was ~0.05 before

# Duplicate entry probability -- the catastrophic failure mode user saw
# (two same-entry positions, one missing stop). Fixed by latest commit.
DUPLICATE_ENTRY_PROB = 0.00   # 0 after the fix; was ~0.02 before
DUPLICATE_LOSS_PTS = 60.0     # average extra loss when duplicate fires

RNG = np.random.default_rng(seed=42)


def apply_broker_reality(trade: dict) -> dict:
    """Take an idealized trade from honest_replay and apply realistic
    execution modeling. Returns the modified trade with adjusted exit
    price and reason. Original kept for comparison."""

    original_exit = trade["exit_px"]
    original_pnl = trade["pnl_usd"]
    original_reason = trade["exit_reason"]

    # 1. Did the entry even fill?
    if RNG.random() > LIMIT_ENTRY_FILL_PROB:
        trade["broker_outcome"] = "entry_miss"
        trade["broker_pnl"] = 0.0
        trade["broker_exit_px"] = trade["entry_px"]
        trade["broker_exit_reason"] = "no_fill"
        return trade

    # 2. Did the signal get rejected (legacy 5s filter)?
    if RNG.random() < SIGNAL_REJECT_PROB:
        trade["broker_outcome"] = "signal_rejected"
        trade["broker_pnl"] = 0.0
        trade["broker_exit_px"] = trade["entry_px"]
        trade["broker_exit_reason"] = "rejected"
        return trade

    # 3. Did a duplicate fire (legacy bug)?
    if RNG.random() < DUPLICATE_ENTRY_PROB:
        # First position fills as normal; SECOND position runs without
        # a bracket and hits a worse exit. Model as extra loss to the
        # original.
        trade["broker_outcome"] = "duplicate_loss"
        trade["broker_pnl"] = original_pnl - DUPLICATE_LOSS_PTS * N_MNQ * MNQ_PER_PT
        trade["broker_exit_px"] = original_exit
        trade["broker_exit_reason"] = "duplicate"
        return trade

    # 4. Original was a stop: model slippage past trigger.
    if original_reason == "stop":
        slip = RNG.normal(STOP_SLIPPAGE_PTS_MEAN, STOP_SLIPPAGE_PTS_STD)
        slip = max(0.0, slip)
        side = trade["side"]
        if side == "LONG":
            adj_exit = trade["stop_px"] - slip
        else:
            adj_exit = trade["stop_px"] + slip
        if side == "LONG":
            adj_pnl_pts = adj_exit - trade["entry_px"]
        else:
            adj_pnl_pts = trade["entry_px"] - adj_exit
        adj_pnl_usd = adj_pnl_pts * N_MNQ * MNQ_PER_PT
        trade["broker_outcome"] = "stop_slipped"
        trade["broker_pnl"] = adj_pnl_usd
        trade["broker_exit_px"] = adj_exit
        trade["broker_exit_reason"] = "stop_slipped"
        return trade

    # 5. Original was a target: model limit fill failure scenarios.
    if original_reason == "target":
        if RNG.random() < LIMIT_TARGET_FILL_PROB:
            # Limit filled cleanly at target -- matches paper.
            trade["broker_outcome"] = "target_clean"
            trade["broker_pnl"] = original_pnl
            trade["broker_exit_px"] = original_exit
            trade["broker_exit_reason"] = "target_clean"
            return trade
        # Limit missed -- which scenario?
        scenario_rng = RNG.random()
        cumulative = 0.0
        scenario = "tick_panic"
        for s, p in TARGET_MISS_SCENARIOS.items():
            cumulative += p
            if scenario_rng <= cumulative:
                scenario = s
                break
        side = trade["side"]
        if scenario == "tick_panic":
            # Tick panic fires at target - 0.5pt for LONG, target + 0.5 SHORT
            if side == "LONG":
                adj_exit = trade["target_px"] - 0.5
            else:
                adj_exit = trade["target_px"] + 0.5
        elif scenario == "reversal":
            # Price reversed and hit stop
            if side == "LONG":
                adj_exit = trade["stop_px"]
            else:
                adj_exit = trade["stop_px"]
        else:  # timeout
            # Random mid-range exit
            mid = (trade["entry_px"] + trade["target_px"]) / 2
            adj_exit = mid + RNG.uniform(-2, 2)
        if side == "LONG":
            adj_pnl_pts = adj_exit - trade["entry_px"]
        else:
            adj_pnl_pts = trade["entry_px"] - adj_exit
        adj_pnl_usd = adj_pnl_pts * N_MNQ * MNQ_PER_PT
        trade["broker_outcome"] = f"target_miss_{scenario}"
        trade["broker_pnl"] = adj_pnl_usd
        trade["broker_exit_px"] = adj_exit
        trade["broker_exit_reason"] = f"target_miss_{scenario}"
        return trade

    # 6. Timeout: matches paper (closed at market when bar exit fired).
    trade["broker_outcome"] = "timeout_matched"
    trade["broker_pnl"] = original_pnl
    trade["broker_exit_px"] = original_exit
    trade["broker_exit_reason"] = "timeout"
    return trade


def run_with_broker_model(bars_df: pd.DataFrame, label: str):
    print(f"\n=== {label} ===")
    print(f"  Bars: {len(bars_df):,}  ({bars_df.index[0]} -> {bars_df.index[-1]})")

    state = FibStrategyState()
    lucid = LucidState()
    params = get_strategy_params("1")

    last_ny_date = None
    trades = []
    bar_index = bars_df.index
    bar_open = bars_df["open"].to_numpy()
    bar_high = bars_df["high"].to_numpy()
    bar_low = bars_df["low"].to_numpy()
    bar_close = bars_df["close"].to_numpy()
    bar_volume = bars_df["volume"].to_numpy()
    n = len(bars_df)

    progress_every = max(1, (n - HISTORY_BARS) // 10)
    for i in range(HISTORY_BARS, n):
        now = bar_index[i].to_pydatetime()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        try:
            from bot.lucid_account import _ny_date_iso
            ny_today = _ny_date_iso(now)
        except Exception:
            ny_today = now.date().isoformat()
        if last_ny_date is not None and ny_today != last_ny_date:
            lucid.cum_pnl += lucid.today_pnl
            lucid.today_pnl = 0.0
        last_ny_date = ny_today

        last_1m_bar = pd.Series({
            "open":  float(bar_open[i]),
            "high":  float(bar_high[i]),
            "low":   float(bar_low[i]),
            "close": float(bar_close[i]),
            "volume": float(bar_volume[i]),
        }, name=bar_index[i])
        bars_history = bars_df.iloc[max(0, i - HISTORY_BARS + 1):i + 1]
        trade = on_new_1m_bar(
            state=state, lucid=lucid,
            bars_setup=bars_history, last_1m_bar=last_1m_bar,
            now=now, n_mnq=N_MNQ, bars_trend=bars_history, params=params,
        )
        if trade is not None:
            pnl_usd = float(trade["pnl_usd"])
            pnl_after_comm = pnl_usd - COMM_RT * N_MNQ
            lucid.today_pnl += pnl_after_comm
            trade_rec = {
                "entry_ts": trade["entry_ts"],
                "exit_ts": trade["exit_ts"],
                "side": trade["side"],
                "entry_px": trade["entry_px"],
                "exit_px": trade["exit_px"],
                "stop_px": trade.get("stop_px", trade["entry_px"]),
                "target_px": trade.get("target_px", trade["entry_px"]),
                "exit_reason": trade["exit_reason"],
                "pnl_usd": pnl_usd - COMM_RT * N_MNQ,
                "hold_s": trade["hold_s"],
            }
            # Now apply broker reality
            trade_rec = apply_broker_reality(trade_rec)
            trade_rec["broker_pnl_net"] = trade_rec["broker_pnl"] - COMM_RT * N_MNQ * (1 if trade_rec["broker_outcome"] not in ("entry_miss", "signal_rejected") else 0)
            trades.append(trade_rec)
        if (i - HISTORY_BARS) % progress_every == 0:
            paper_total = sum(t["pnl_usd"] for t in trades)
            broker_total = sum(t["broker_pnl_net"] for t in trades)
            print(f"    progress  {100*(i-HISTORY_BARS)/(n-HISTORY_BARS):5.1f}%  "
                  f"trades={len(trades)}  paper=${paper_total:+,.0f}  "
                  f"broker=${broker_total:+,.0f}")
    return trades


def summarize(trades: list, label: str):
    n = len(trades)
    if not n:
        print(f"  No trades for {label}")
        return
    paper_total = sum(t["pnl_usd"] for t in trades)
    broker_total = sum(t["broker_pnl_net"] for t in trades)
    paper_wins = sum(1 for t in trades if t["pnl_usd"] > 0)
    broker_wins = sum(1 for t in trades if t["broker_pnl_net"] > 0)

    print(f"\n  === {label} -- Paper vs Broker reality ===")
    print(f"  Trades:           {n:,}")
    print(f"  Paper total:      ${paper_total:+,.0f}  ({100*paper_wins/n:.1f}% WR)")
    print(f"  Broker total:     ${broker_total:+,.0f}  ({100*broker_wins/n:.1f}% WR)")
    print(f"  Gap:              ${paper_total - broker_total:+,.0f}  "
          f"(~${(paper_total - broker_total)/n:+.2f}/trade)")
    print()
    print(f"  Per-trade outcome breakdown:")
    by_outcome = defaultdict(lambda: [0, 0.0])
    for t in trades:
        by_outcome[t["broker_outcome"]][0] += 1
        by_outcome[t["broker_outcome"]][1] += t["broker_pnl_net"]
    for outcome in sorted(by_outcome.keys(), key=lambda k: -by_outcome[k][1]):
        cnt, total = by_outcome[outcome]
        avg = total / cnt if cnt else 0
        print(f"    {outcome:<28}  n={cnt:4d}  avg=${avg:+7.2f}  total=${total:+,.0f}")


def main():
    print("Broker-realistic execution sim")
    print("=" * 60)
    print(f"Knobs:")
    print(f"  LIMIT_ENTRY_FILL_PROB  = {LIMIT_ENTRY_FILL_PROB}")
    print(f"  LIMIT_TARGET_FILL_PROB = {LIMIT_TARGET_FILL_PROB}")
    print(f"  STOP_SLIPPAGE_PTS      = N({STOP_SLIPPAGE_PTS_MEAN}, {STOP_SLIPPAGE_PTS_STD})")
    print(f"  TARGET_MISS_SCENARIOS  = {TARGET_MISS_SCENARIOS}")
    print()

    print("Loading bars...")
    df = pd.read_csv(CSV, parse_dates=["ts"], index_col="ts").sort_index()
    df = df[(df["high"] >= df["low"])]
    print(f"  {len(df):,} bars over {(df.index.max()-df.index.min()).days} days")

    # Last 7 days -- closest analog to current live conditions
    cutoff = df.index.max() - timedelta(days=7)
    last7 = df[df.index >= cutoff]
    trades = run_with_broker_model(last7, "LAST 7 DAYS")
    summarize(trades, "LAST 7 DAYS")

    # Last 30 days -- bigger sample
    cutoff = df.index.max() - timedelta(days=30)
    last30 = df[df.index >= cutoff]
    trades = run_with_broker_model(last30, "LAST 30 DAYS")
    summarize(trades, "LAST 30 DAYS")


if __name__ == "__main__":
    main()
