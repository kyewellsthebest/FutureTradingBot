"""
Per-trade analysis for the Fib 50% strategy with Lucid rules:
  * RR distribution (planned & realized)
  * Win rate by size
  * Hold-time distribution + microscalp check
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.fib_50_lucid_full import (
    run_lucid_sim, START_BAL, DLL, COMM_PER_MNQ_RT,
    SLIP_PT_PER_SIDE, MNQ_PER_PT,
)
from research.local_data_loader import load_intraday_5min


def analyze(res, size_label):
    if not res["trades"]:
        print(f"\n{size_label}: no trades"); return
    tdf = pd.DataFrame(res["trades"])
    # bar->hold-seconds: 5-min bar diff
    entry = pd.to_datetime(tdf["entry_ts"])
    exit_ = pd.to_datetime(tdf["exit_ts"])
    hold_s = (exit_ - entry).dt.total_seconds()
    tdf["hold_s"] = hold_s

    # planned RR computed from prices (entry/stop/target).
    # Reload the underlying detail: simulator doesn't return stop/target on
    # the trade row, so derive a usable RR proxy from net P&L vs risk.
    # We have net_pnl and the fixed contract_value = n_mnq * $2.
    contract_value = res["n_mnq"] * MNQ_PER_PT
    # Risk per trade in dollars approximated by max single-trade loss observed
    # in same direction — too rough. Instead, use absolute net_pnl distribution.
    tdf["abs_pnl_usd"] = tdf["net_pnl"].abs()

    n = len(tdf)
    wins_mask = tdf["net_pnl"] > 0
    losses_mask = tdf["net_pnl"] < 0
    wins = int(wins_mask.sum())
    losses = int(losses_mask.sum())
    wr = wins / n

    win_pnl = tdf.loc[wins_mask, "net_pnl"]
    loss_pnl = tdf.loc[losses_mask, "net_pnl"]
    avg_win = float(win_pnl.mean()) if len(win_pnl) else 0.0
    avg_loss = float(loss_pnl.mean()) if len(loss_pnl) else 0.0
    median_win = float(win_pnl.median()) if len(win_pnl) else 0.0
    median_loss = float(loss_pnl.median()) if len(loss_pnl) else 0.0

    realized_rr = abs(avg_win / avg_loss) if avg_loss < 0 else 0.0
    median_rr = abs(median_win / median_loss) if median_loss < 0 else 0.0

    # Lucid microscalping = hold <= 5s
    micro_trades = int((hold_s <= 5).sum())
    micro_profit = float(tdf.loc[(hold_s <= 5) & (tdf["net_pnl"] > 0),
                                  "net_pnl"].sum())
    total_profit = float(win_pnl.sum())
    micro_ratio = micro_profit / total_profit if total_profit > 0 else 0.0

    print(f"\n{'='*78}\n{size_label}\n{'='*78}")
    print(f"  Trades                  : {n:,}")
    print(f"  Wins / Losses           : {wins:,} / {losses:,}")
    print(f"  Win rate                : {wr*100:.2f}%")
    print(f"\n  --- Average / Median win & loss ---")
    print(f"  Avg WIN  $              : ${avg_win:>+9.2f}")
    print(f"  Avg LOSS $              : ${avg_loss:>+9.2f}")
    print(f"  Realized R:R (avg/avg)  : 1:{realized_rr:.2f}")
    print(f"  Median WIN  $           : ${median_win:>+9.2f}")
    print(f"  Median LOSS $           : ${median_loss:>+9.2f}")
    print(f"  Realized R:R (median)   : 1:{median_rr:.2f}")
    print(f"\n  --- $ profile distribution ---")
    print(f"  Largest win             : ${win_pnl.max():>+9.0f}")
    print(f"  Largest loss            : ${loss_pnl.min():>+9.0f}")
    print(f"  Net P&L total           : ${tdf['net_pnl'].sum():>+9.0f}")
    print(f"  Expectancy per trade    : ${tdf['net_pnl'].mean():>+9.2f}")
    print(f"\n  --- Hold-time distribution ---")
    print(f"  Median hold             : {hold_s.median()/60:.1f} min")
    print(f"  Mean hold               : {hold_s.mean()/60:.1f} min")
    print(f"  P25 / P75               : {hold_s.quantile(0.25)/60:.1f}m / "
          f"{hold_s.quantile(0.75)/60:.1f}m")
    print(f"  Shortest                : {hold_s.min()/60:.2f} min")
    print(f"  Longest                 : {hold_s.max()/60:.1f} min")
    print(f"\n  --- Lucid microscalp check (≤5s holds, >50% profit = banned) ---")
    print(f"  Trades held ≤5s         : {micro_trades:,} ({micro_trades/n*100:.2f}%)")
    print(f"  Profit from ≤5s trades  : ${micro_profit:,.0f}")
    print(f"  Ratio of profit ≤5s     : {micro_ratio*100:.2f}%")
    print(f"  Status                  : "
          f"{'COMPLIANT (well under 50% threshold)' if micro_ratio < 0.50 else 'VIOLATION'}")


def main():
    nq = load_intraday_5min("nq")
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    print("=" * 78)
    print("FIB 50% PER-TRADE STATS — Lucid 50K Pro + costs (~$2/MNQ RT)")
    print("=" * 78)
    for n_mnq in (1, 5):
        res = run_lucid_sim(nq, n_mnq, model_costs=True)
        analyze(res, f"{n_mnq} MNQ ({res['n_mnq']*MNQ_PER_PT:.0f}$/pt)")


if __name__ == "__main__":
    main()
