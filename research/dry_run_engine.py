"""
Dry-run engine — simulates the real bot's `evaluate()` decision pipeline
across the entire 2-year history WITHOUT placing trades, just to count
how many candidates would survive each filter under each filter-mode.

Use this to answer "if I switch to AGGRESSIVE mode, how many trades per
day will the bot actually do?" before turning it on for live paper trading.

Usage:
    python -m research.dry_run_engine                     # current mode
    HFT_FILTER_MODE=AGGRESSIVE python -m research.dry_run_engine
    HFT_FILTER_MODE=MODERATE   python -m research.dry_run_engine
"""
from __future__ import annotations

import sys
import time
from collections import Counter

import pandas as pd

from research.filter_config import CONFIG, describe
from research.indicators import eq50
from research.local_data_loader import load_daily, load_intraday_5min
from research.signal_filters import (
    TradeRef,
    cooldown_filter,
    daily_bias_at,
    daily_bias_filter,
    derive_target,
    key_level_proximity_filter,
    kill_zone_filter,
    min_rr_filter,
    vol_regime_at,
)
from research.signal_generator import ALL_SIGNALS, _attach_prev_day_levels


def main() -> int:
    print("=" * 76)
    print("DRY-RUN ENGINE — counts trades per day across the 2-year history")
    print(f"  filter config: {describe()}")
    print("=" * 76)

    intraday = load_intraday_5min()
    daily = load_daily()
    print(f"  data: {len(intraday):,} 5-min bars across {(intraday.index[-1]-intraday.index[0]).days} days")

    df = _attach_prev_day_levels(intraday, daily)
    df["eq50"] = eq50(df["high"], df["low"], 50)

    # Pre-generate every signal once.
    print(f"  generating signals from {len(ALL_SIGNALS)} signal classes ...")
    all_sigs = []
    for sig_obj in ALL_SIGNALS:
        sigs = sig_obj.generate(intraday, daily)
        if not sigs.empty:
            all_sigs.append(sigs)
    if not all_sigs:
        print("  no signals at all.")
        return 1
    sig_df = pd.concat(all_sigs).sort_values("signal_time").reset_index(drop=True)
    print(f"  {len(sig_df):,} raw signals before any filter")

    # Filter cascade
    rejection_counts: Counter = Counter()
    accepted: list[dict] = []
    prior_trades: list[TradeRef] = []  # rolling trade ledger for cooldown

    t0 = time.time()
    for _, sig in sig_df.iterrows():
        name = sig["signal_name"]
        side = sig["side"]
        ts = sig["signal_time"]
        entry_px = float(sig["entry_px"])

        # 1. Daily bias
        bias = daily_bias_at(daily, ts)
        ok, _ = daily_bias_filter(side, bias, name)
        if not ok:
            rejection_counts["bias"] += 1
            continue

        # 2. Vol regime (never blocks; just supplies stop)
        vol = vol_regime_at(daily, ts)

        # 3. Kill zone
        ok, _ = kill_zone_filter(name, ts)
        if not ok:
            rejection_counts["killzone"] += 1
            continue

        # 4. Key-level proximity
        try:
            row = df.loc[ts]
        except KeyError:
            rejection_counts["bar_missing"] += 1
            continue
        pdh = float(row["pdh"]) if pd.notna(row["pdh"]) else float("nan")
        pdl = float(row["pdl"]) if pd.notna(row["pdl"]) else float("nan")
        eq = float(row["eq50"]) if pd.notna(row["eq50"]) else float("nan")
        ok, _ = key_level_proximity_filter(name, entry_px, pdh, pdl, eq)
        if not ok:
            rejection_counts["proximity"] += 1
            continue

        # 5. Target + R:R
        target_px = derive_target(name, side, entry_px, pdh, pdl, eq,
                                   sig.get("target_hint", float("nan")))
        ok, _, rr = min_rr_filter(name, side, entry_px, vol.stop_pts, target_px)
        if not ok:
            rejection_counts["min_rr"] += 1
            continue

        # 6. Cooldown
        ok, _ = cooldown_filter(ts, prior_trades)
        if not ok:
            rejection_counts["cooldown"] += 1
            continue

        # ACCEPTED — model the trade as a 30-min hold using next-bar close as proxy.
        accepted.append({"signal_name": name, "side": side, "ts": ts,
                         "rr": rr, "entry_px": entry_px})
        # Add to ledger (treat as instant exit + assume break-even for cooldown sim)
        prior_trades.append(TradeRef(
            entry_time=ts,
            exit_time=ts + pd.Timedelta(minutes=30),
            side=side, pnl=0.0, signal_name=name,
        ))

    elapsed = time.time() - t0
    days = max(1, (intraday.index[-1] - intraday.index[0]).days)
    print(f"\n  filtering done in {elapsed:.1f}s")
    print(f"  ACCEPTED: {len(accepted):,} trades  ({len(accepted)/days:.2f}/day  "
          f"{len(accepted)/days*5:.1f}/week)")
    print()
    print("  Rejection breakdown:")
    total_rej = sum(rejection_counts.values())
    for reason, n in rejection_counts.most_common():
        pct = 100.0 * n / total_rej if total_rej else 0.0
        print(f"    {reason:<14s}  {n:>7,}  ({pct:>5.1f}%)")
    print()
    print("  Per-signal acceptance:")
    by_sig = Counter(a["signal_name"] for a in accepted)
    for name, n in sorted(by_sig.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<26s}  {n:>5}  ({n/days:>5.2f}/day)")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
