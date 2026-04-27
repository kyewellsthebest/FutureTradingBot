"""
End-to-end 2-year backtest with the full signal universe + filter chain.

What this does:
  1. Loads both 1-min AND 5-min NQ data + daily levels
  2. Generates signals from BOTH families:
       - ALL_SIGNALS (5-min, validated, 30 MNQ contracts)
       - ALL_HF_SIGNALS (1-min, candidates, 5 MNQ contracts)
  3. Merges into one chronological event stream
  4. Walks through every event applying the engine's full filter cascade
       (daily bias / kill zone / proximity / R:R / cooldown / vol regime
        — VPIN/HMM/GEX/macro skipped because no live snapshot exists for
        historical bars; this is the realistic *deterministic* part of the
        chain)
  5. For each trade that passes, simulates the actual fill on 1-min bars
       (intra-bar high/low walk) with per-signal contract-aware costs
  6. Tracks $50k equity through the entire 2-year window
  7. Reports trades/day, win rate, net P&L, max DD, Sharpe, Calmar,
       monthly equity curve, projected annual return on $50k

Usage:
    python -m research.combined_backtest                       # STRICT
    HFT_FILTER_MODE=AGGRESSIVE python -m research.combined_backtest
    python -m research.combined_backtest --hf-only             # only HF signals
    python -m research.combined_backtest --no-hf               # only 5-min signals
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.backtest_engine import (
    SLIP_ENTRY_PTS, SLIP_STOP_PTS,
    commission_for, compute_stats, dollars_per_pt_for, monte_carlo,
)
from research.filter_config import CONFIG, describe as describe_filters
from research.hf_signals import ALL_HF_SIGNALS
from research.indicators import eq50
from research.local_data_loader import load_daily, load_intraday_1min, load_intraday_5min
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "data" / "combined_backtest_report.json"

STARTING_BALANCE = 50_000.0
APEX_TARGET = 9_000.0
APEX_TRAILING_DD = 3_000.0


@dataclass
class FilledTrade:
    signal_name: str
    side: str
    entry_time: pd.Timestamp
    entry_px: float
    exit_time: pd.Timestamp
    exit_px: float
    stop_px: float
    target_px: float
    contracts: int
    pts: float
    pnl: float
    win: bool
    exit_reason: str   # target | stop | timeout
    bars_held: int
    rejection_chain: list[str] = field(default_factory=list)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hf-only", action="store_true", help="Only 1-min HF signals")
    p.add_argument("--no-hf", action="store_true", help="Skip HF heuristic signals")
    p.add_argument("--no-mined", action="store_true", help="Skip data-mined patterns")
    p.add_argument("--no-wr", action="store_true", help="Skip 60%+ WR mined patterns")
    p.add_argument("--no-fivemin", action="store_true", help="Skip 5-min validated signals")
    p.add_argument("--mined-only", action="store_true", help="Only mined patterns")
    p.add_argument("--whitelist-hf", default="",
                   help="Comma-separated HF signal names to include")
    p.add_argument("--max-hold-min", type=int, default=240,
                   help="Max minutes to hold any trade.")
    return p.parse_args()


def _simulate_fill(side: str, entry_px: float, stop_px: float, target_px: float,
                   bars: pd.DataFrame, bars_idx: dict, entry_time: pd.Timestamp,
                   max_hold_bars: int) -> tuple[pd.Timestamp, float, str, int]:
    """Walk bars from entry_time forward; return (exit_time, exit_px, reason, bars_held).
    Bars can be 1-min or 5-min — caller picks the appropriate frame for the signal's
    timeframe so we don't fabricate intra-bar stop hits that didn't exist at validation."""
    if entry_time not in bars_idx:
        i = bars.index.searchsorted(entry_time)
        if i >= len(bars):
            return entry_time, entry_px, "timeout", 0
    else:
        i = bars_idx[entry_time]
    end = min(i + 1 + max_hold_bars, len(bars))
    high = bars["high"].to_numpy()
    low = bars["low"].to_numpy()
    close = bars["close"].to_numpy()
    times = bars.index
    for j in range(i + 1, end):
        hi, lo = high[j], low[j]
        if side == "LONG":
            hit_stop = lo <= stop_px
            hit_target = hi >= target_px
        else:
            hit_stop = hi >= stop_px
            hit_target = lo <= target_px
        if hit_stop and hit_target:
            return times[j], stop_px, "stop", j - i  # conservative
        if hit_stop:
            return times[j], stop_px, "stop", j - i
        if hit_target:
            return times[j], target_px, "target", j - i
    last = end - 1
    return times[last], float(close[last]), "timeout", last - i


def main() -> int:
    args = parse_args()
    print("=" * 78)
    print("COMBINED 2-YEAR BACKTEST")
    print(f"  filter config: {describe_filters()}")
    print("=" * 78)

    print("\n[1/4] Loading 1-min + 5-min + daily ...", flush=True)
    t0 = time.time()
    m1 = load_intraday_1min()
    m5 = load_intraday_5min()
    d = load_daily()
    days = max(1, (m1.index[-1] - m1.index[0]).days)
    print(f"  1-min: {len(m1):,}   5-min: {len(m5):,}   daily: {len(d)}   "
          f"range: {m1.index[0].date()} -> {m1.index[-1].date()}  ({days} days)")

    # Prepare PDH/PDL/EQ50 helper frames + 20-bar rolling mean for ZSCORE targets
    df5 = _attach_prev_day_levels(m5, d)
    df5["eq50"] = eq50(df5["high"], df5["low"], 50)
    df5["mean20"] = df5["close"].rolling(20, min_periods=20).mean()
    df1 = _attach_prev_day_levels(m1, d)
    df1["eq50"] = eq50(df1["high"], df1["low"], 50)
    df1["mean20"] = df1["close"].rolling(20, min_periods=20).mean()

    # Generate signals
    print(f"\n[2/4] Generating signals ...", flush=True)
    sig_frames = []
    if not args.hf_only and not args.mined_only and not args.no_fivemin:
        for sig_obj in ALL_SIGNALS:
            sigs = sig_obj.generate(m5, d)
            if not sigs.empty:
                sigs["source_tf"] = "5min"
                sig_frames.append(sigs)
        n5 = sum(len(f) for f in sig_frames)
        print(f"  5-min validated: {n5:,} raw signals from {len(ALL_SIGNALS)} classes")

    if not args.no_hf and not args.mined_only:
        wl = set(args.whitelist_hf.split(",")) if args.whitelist_hf else None
        hf_n = 0
        for sig_obj in ALL_HF_SIGNALS:
            if wl and sig_obj.name not in wl:
                continue
            sigs = sig_obj.generate(m1, d)
            if not sigs.empty:
                sigs["source_tf"] = "1min"
                sig_frames.append(sigs)
                hf_n += len(sigs)
        print(f"  HF 1-min: {hf_n:,} raw signals from {len(ALL_HF_SIGNALS)} candidates")

    if not args.no_mined:
        try:
            from research.mined_signals import ALL_MINED_SIGNALS
        except Exception as e:
            ALL_MINED_SIGNALS = []
            print(f"  mined: import failed ({e!r}) — skipping")
        mined_n = 0
        for sig_obj in ALL_MINED_SIGNALS:
            sigs = sig_obj.generate(m1, d)
            if not sigs.empty:
                sigs["source_tf"] = "1min"
                sig_frames.append(sigs)
                mined_n += len(sigs)
        print(f"  mined: {mined_n:,} raw signals from {len(ALL_MINED_SIGNALS)} patterns")

    # WR-focused mined signals (the 60%+ WR set) — separate flag from --no-mined
    if not args.no_wr:
        try:
            from research.mined_wr_signals import ALL_WR_SIGNALS
        except Exception as e:
            ALL_WR_SIGNALS = []
            print(f"  WR mined: import failed ({e!r}) — skipping")
        wr_n = 0
        for sig_obj in ALL_WR_SIGNALS:
            sigs = sig_obj.generate(m1, d)
            if not sigs.empty:
                sigs["source_tf"] = "1min"
                sig_frames.append(sigs)
                wr_n += len(sigs)
        print(f"  WR mined: {wr_n:,} raw signals from {len(ALL_WR_SIGNALS)} 60%+WR patterns")

        # V3 patterns — rigorous CPCV-validated 55%+ WR @ 1:2 RR
        try:
            from research.mined_v3_signals import ALL_V3_SIGNALS
        except Exception as e:
            ALL_V3_SIGNALS = []
            print(f"  V3 mined: import failed ({e!r}) — skipping")
        v3_n = 0
        for sig_obj in ALL_V3_SIGNALS:
            sigs = sig_obj.generate(m1, d)
            if not sigs.empty:
                sigs["source_tf"] = "1min"
                sig_frames.append(sigs)
                v3_n += len(sigs)
        print(f"  V3 mined: {v3_n:,} raw signals from {len(ALL_V3_SIGNALS)} CPCV patterns")

    if not sig_frames:
        print("No signals generated.")
        return 1
    all_sigs = pd.concat(sig_frames).sort_values("signal_time").reset_index(drop=True)
    print(f"  TOTAL: {len(all_sigs):,} raw signals  (~{len(all_sigs)/days:.1f}/day)")

    # Build positional indices for fill simulation. We walk on the
    # signal's *native* timeframe — 5-min signals on 5-min bars, HF on 1-min —
    # so we don't fabricate intra-bar stop hits that didn't exist at validation.
    m1_idx = {ts: i for i, ts in enumerate(m1.index)}
    m5_idx = {ts: i for i, ts in enumerate(m5.index)}

    # Walk events chronologically through filter chain
    print(f"\n[3/4] Filtering + simulating fills ...", flush=True)
    accepted: list[FilledTrade] = []
    rejection_counts: dict[str, int] = {}
    prior_trades: list[TradeRef] = []
    t1 = time.time()

    for k, sig in enumerate(all_sigs.itertuples(index=False), 1):
        if k % 5000 == 0:
            elapsed = time.time() - t1
            print(f"  ... {k:>6,}/{len(all_sigs):>6,}  "
                  f"accepted={len(accepted):>4}  ({elapsed:.0f}s)", flush=True)

        name = sig.signal_name
        side = sig.side
        ts = sig.signal_time
        entry_raw = float(sig.entry_px)
        is_wr = name.startswith("WR_")
        is_v3 = name.startswith("V3_")
        is_hf = name.startswith("HF_") or name.startswith("MINED_") or is_wr or is_v3
        ref_df = df1 if is_hf else df5

        # 1. Daily bias
        bias = daily_bias_at(d, ts)
        ok, _ = daily_bias_filter(side, bias, name)
        if not ok:
            rejection_counts["bias"] = rejection_counts.get("bias", 0) + 1
            continue

        # 2. Vol regime sizing (never blocks)
        vol = vol_regime_at(d, ts)
        # Per-family stop/target — 5-min uses vol regime; HF uses 8pt; mined
        # uses 5pt with 2.5 RR matching the 10-bar forward window they were
        # discovered against (mean OOS edge ~9-43 pts).
        if is_v3:
            # V3 signals carry their own stop/target via the target_hint
            # (= entry +/- target_pts). Stop is encoded in the name (S{n}).
            v3_target_hint = float(sig.target_hint) if pd.notna(sig.target_hint) else None
            # parse 'V3_LONG_S10T20_01' → stop=10
            try:
                stop_pts_eff = float(name.split("_S")[1].split("T")[0])
            except Exception:
                stop_pts_eff = 10.0
            target_rr = 2.0   # by construction: target = 2× stop
        elif is_wr:
            # WR signals carry their own (target, stop) discovered by the miner
            # in target_hint and via the signal-class attribute.
            wr_target_hint = float(sig.target_hint) if pd.notna(sig.target_hint) else None
            # Pull stop from class attribute if accessible — fall back to 10pt
            stop_pts_eff = 10.0
            target_rr = (abs(wr_target_hint - entry_raw) / stop_pts_eff
                         if wr_target_hint is not None else 1.5)
        elif name.startswith("MINED_"):
            stop_pts_eff = 5.0
            target_rr = 2.5
        elif is_hf:
            stop_pts_eff = 8.0
            target_rr = 1.5
        else:
            stop_pts_eff = vol.stop_pts
            target_rr = 2.0

        # 3. Kill zone
        ok, _ = kill_zone_filter(name, ts)
        if not ok:
            rejection_counts["killzone"] = rejection_counts.get("killzone", 0) + 1
            continue

        # 4. Key-level proximity (HF signals use natural M1 levels but
        #    proximity filter only applies to 5-min validated set)
        if not is_hf:
            try:
                row = ref_df.loc[ts]
            except KeyError:
                rejection_counts["bar_missing"] = rejection_counts.get("bar_missing", 0) + 1
                continue
            pdh = float(row["pdh"]) if pd.notna(row["pdh"]) else float("nan")
            pdl = float(row["pdl"]) if pd.notna(row["pdl"]) else float("nan")
            eq = float(row["eq50"]) if pd.notna(row["eq50"]) else float("nan")
            mean20 = float(row["mean20"]) if pd.notna(row.get("mean20")) else float("nan")
            prev_close = float(row["prev_close"]) if pd.notna(row.get("prev_close")) else float("nan")
            ok, _ = key_level_proximity_filter(name, entry_raw, pdh, pdl, eq)
            if not ok:
                rejection_counts["proximity"] = rejection_counts.get("proximity", 0) + 1
                continue
            # Derive target via spec-correct anchors. ZSCORE signals
            # natively target the 20-bar rolling mean.
            if name.startswith("ZSCORE_") and mean20 == mean20:
                target_px_pre = mean20
            else:
                target_px_pre = derive_target(name, side, entry_raw, pdh, pdl, eq,
                                              getattr(sig, "target_hint", float("nan")),
                                              prev_close=prev_close)
            # Sanity: LONG target must be > entry, SHORT target < entry.
            # If anchor is on wrong side (rare but happens, e.g. eq50 below entry
            # for an oversold ZSCORE_LONG), fall back to a fixed RR target.
            min_target_dist = stop_pts_eff * target_rr
            if side == "LONG" and target_px_pre <= entry_raw + 1.0:
                target_px_pre = entry_raw + min_target_dist
            elif side == "SHORT" and target_px_pre >= entry_raw - 1.0:
                target_px_pre = entry_raw - min_target_dist
        else:
            target_hint = getattr(sig, "target_hint", float("nan"))
            if pd.notna(target_hint):
                target_px_pre = float(target_hint)
            else:
                target_px_pre = entry_raw + (stop_pts_eff * target_rr) if side == "LONG" \
                                else entry_raw - (stop_pts_eff * target_rr)

        # Apply slippage to entry
        slip = SLIP_ENTRY_PTS
        entry_px = entry_raw + slip if side == "LONG" else entry_raw - slip

        # Recompute stop/target around the slipped entry
        if side == "LONG":
            stop_px = entry_px - stop_pts_eff
        else:
            stop_px = entry_px + stop_pts_eff
        # Use the pre-derived target (in absolute price terms)
        target_px = target_px_pre

        # 5. Min R:R (HF signals use 1.5 floor; others 2.0)
        ok, _, rr = min_rr_filter(name, side, entry_px, stop_pts_eff, target_px)
        if not ok:
            rejection_counts["rr"] = rejection_counts.get("rr", 0) + 1
            continue

        # 6. Cooldown
        ok, _ = cooldown_filter(ts, prior_trades)
        if not ok:
            rejection_counts["cooldown"] = rejection_counts.get("cooldown", 0) + 1
            continue

        # ACCEPTED — simulate the fill on the signal's native timeframe.
        # 5-min signals walked on 5-min bars (matches their validation),
        # HF (1-min) signals walked on 1-min bars.
        if is_hf:
            fill_bars, fill_idx = m1, m1_idx
            max_hold = min(args.max_hold_min, 60)         # 60 1-min bars
        else:
            fill_bars, fill_idx = m5, m5_idx
            max_hold = max(1, args.max_hold_min // 5)     # convert min → 5-min bars
        exit_time, exit_px_raw, reason, bars = _simulate_fill(
            side, entry_px, stop_px, target_px, fill_bars, fill_idx, ts, max_hold,
        )
        # Apply stop slippage adverse direction
        if reason == "stop":
            exit_px = exit_px_raw - SLIP_STOP_PTS if side == "SHORT" else exit_px_raw + SLIP_STOP_PTS
            # Wait — adverse on stop means worse:
            exit_px = exit_px_raw + SLIP_STOP_PTS if side == "SHORT" else exit_px_raw - SLIP_STOP_PTS
        else:
            exit_px = exit_px_raw

        pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
        contracts = 5 if is_hf else 30
        dpp = contracts * 2.0
        comm = contracts * 2.0
        pnl = pts * dpp - comm
        win = pts > 0

        ft = FilledTrade(
            signal_name=name, side=side,
            entry_time=ts, entry_px=entry_px,
            exit_time=exit_time, exit_px=exit_px,
            stop_px=stop_px, target_px=target_px,
            contracts=contracts, pts=float(pts), pnl=float(pnl),
            win=win, exit_reason=reason, bars_held=bars,
        )
        accepted.append(ft)
        prior_trades.append(TradeRef(
            entry_time=ts, exit_time=exit_time, side=side,
            pnl=float(pnl), signal_name=name,
        ))

    print(f"  filtered + simulated in {time.time()-t1:.1f}s")
    print(f"  ACCEPTED: {len(accepted):,} trades  ({len(accepted)/days:.2f}/day)")

    if not accepted:
        print("\nNo trades accepted under current filter config.")
        return 0

    # ------ Reporting ------
    print(f"\n[4/4] Building report ...")
    pnls = np.array([t.pnl for t in accepted])
    wins_n = int((pnls > 0).sum())
    losses_n = int((pnls <= 0).sum())
    n = len(accepted)
    eq = STARTING_BALANCE + np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    max_dd = float(dd.min())
    final_equity = float(eq[-1])
    net_pnl = final_equity - STARTING_BALANCE
    pct_return = net_pnl / STARTING_BALANCE
    ann_return = (final_equity / STARTING_BALANCE) ** (365.0 / days) - 1
    avg_win = float(pnls[pnls > 0].mean()) if wins_n else 0.0
    avg_loss = float(pnls[pnls <= 0].mean()) if losses_n else 0.0
    pf_num = float(pnls[pnls > 0].sum()) if wins_n else 0.0
    pf_den = -float(pnls[pnls <= 0].sum()) if losses_n else 0.0
    pf = pf_num / pf_den if pf_den > 0 else float("inf")
    daily_pnl = pd.Series(pnls, index=[t.entry_time for t in accepted]).groupby(
        lambda d: d.date()).sum()
    sharpe = (daily_pnl.mean() / daily_pnl.std() * (252 ** 0.5)) if daily_pnl.std() > 0 else 0.0
    calmar = ann_return / abs(max_dd / STARTING_BALANCE) if max_dd < 0 else 0.0

    # Monte Carlo
    mc = monte_carlo([type("T", (), {"pnl": p, "entry_time": None})() for p in pnls],
                     n_paths=2000, starting_balance=STARTING_BALANCE,
                     apex_target=APEX_TARGET, apex_max_dd=APEX_TRAILING_DD)

    # Per-signal breakdown
    by_sig: dict[str, list[FilledTrade]] = {}
    for t in accepted:
        by_sig.setdefault(t.signal_name, []).append(t)
    per_signal = []
    for sname, trades in sorted(by_sig.items(), key=lambda kv: -sum(t.pnl for t in kv[1])):
        sn = len(trades)
        sw = sum(1 for t in trades if t.win)
        spnl = sum(t.pnl for t in trades)
        per_signal.append({
            "signal": sname, "trades": sn, "wins": sw,
            "win_rate": sw/sn, "net_pnl": spnl,
            "avg_pnl": spnl/sn, "trades_per_day": sn/days,
        })

    # ----- Print report -----
    print()
    print("=" * 78)
    print("RESULTS — $50,000 starting balance, 2-year NQ history")
    print("=" * 78)
    print(f"  Period:           {m1.index[0].date()} to {m1.index[-1].date()}  ({days} days)")
    print(f"  Total trades:     {n:,}")
    print(f"  Per day:          {n/days:.2f}")
    print(f"  Per week:         {n/days*5:.1f}")
    print(f"  Win rate:         {wins_n/n*100:.1f}%   ({wins_n} wins / {losses_n} losses)")
    print(f"  Profit factor:    {pf:.2f}")
    print(f"  Avg win:          ${avg_win:,.0f}")
    print(f"  Avg loss:         ${avg_loss:,.0f}")
    print()
    print(f"  Net P&L:          ${net_pnl:>10,.0f}     ({pct_return*100:+.1f}%)")
    print(f"  Final equity:     ${final_equity:>10,.0f}")
    print(f"  Max drawdown:     ${max_dd:>10,.0f}     ({max_dd/STARTING_BALANCE*100:+.1f}%)")
    print(f"  Annualized:       {ann_return*100:+.1f}%/yr")
    print(f"  Calmar ratio:     {calmar:.2f}")
    print(f"  Sharpe (daily):   {sharpe:.2f}")
    print()
    print("  Monte Carlo (2000 random orderings of trades):")
    print(f"    Median final:   ${mc['median_final']:>10,.0f}")
    print(f"    5th percentile: ${mc['p5_final']:>10,.0f}")
    print(f"    95th percentile:${mc['p95_final']:>10,.0f}")
    print(f"    P(Apex pass):   {mc['p_apex_pass']*100:.1f}%")
    print(f"    P(Apex blow):   {mc['p_apex_blow']*100:.1f}%")
    print()
    print("  Per-signal (top 15 by P&L):")
    print(f"    {'signal':<30s} {'n':>6} {'wr':>5} {'pnl':>12} {'/day':>5}")
    for ps in per_signal[:15]:
        print(f"    {ps['signal']:<30s} {ps['trades']:>6} "
              f"{ps['win_rate']*100:>4.0f}% ${ps['net_pnl']:>10,.0f} {ps['trades_per_day']:>5.2f}")
    print()
    print("  Filter rejection breakdown:")
    total_rej = sum(rejection_counts.values())
    for r, c in sorted(rejection_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {r:<14s} {c:>7,}  ({c/total_rej*100:>4.1f}%)")
    print("=" * 78)

    # Persist JSON
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": describe_filters(),
        "starting_balance": STARTING_BALANCE,
        "period": {"start": str(m1.index[0]), "end": str(m1.index[-1]), "days": days},
        "trades": n,
        "trades_per_day": n/days,
        "wins": wins_n, "losses": losses_n,
        "win_rate": wins_n/n,
        "profit_factor": pf if math.isfinite(pf) else None,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "net_pnl": net_pnl, "final_equity": final_equity,
        "max_drawdown": max_dd, "max_drawdown_pct": max_dd/STARTING_BALANCE,
        "annualized_return": ann_return,
        "calmar": calmar, "sharpe_daily": sharpe,
        "monte_carlo": mc,
        "per_signal": per_signal,
        "rejection_breakdown": rejection_counts,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  Wrote -> {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
