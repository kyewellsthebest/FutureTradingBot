"""Engine-based backtest. Uses the SAME code path as live trading:
  engine.strategies.pullback.PullbackImpulse
  engine.fills.sim.SimFillModel
  engine.risk.engine.RiskEngine
  engine.runtime.Runtime

This is the honest backtest. Whatever P&L it shows is what the bot would
produce live if Tradovate behaved exactly like SimFillModel (which is
calibrated conservatively for NQ microstructure).

Compares THREE configurations:
  A. NAKED:  no risk gates, no realistic fills (matches old optimistic sim)
  B. REALISTIC FILLS: SimFillModel ON, risk gates OFF
  C. FULL: SimFillModel + all risk gates (US RTH skip, DLL, sizer, etc.)

The delta A -> B tells us how much "edge" is execution dishonesty.
The delta B -> C tells us how much the risk engine costs vs how much
account-preservation value it provides.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/user/HFTBot")

from engine.fills.sim import SimFillModel, SimFillParams
from engine.market_context import build_market_context
from engine.risk.engine import RiskEngine
from engine.risk.gates import (
    AccountState, ActiveLockoutGate, ConsecutiveLossesGate, CooldownGate,
    DailyLossLimitGate, MaxTradesPerDayGate, NewsBlackoutGate,
    TradingWindowGate, TrailDistanceSizerGate, TrailFloorBufferGate,
)
from engine.runtime import Runtime
from engine.strategies.pullback import PullbackImpulse


CSV = "/home/user/HFTBot/data/polygon/NQ_1min.csv"
STARTING_BAL = 50_000.0
TRAIL_FLOOR_INITIAL = 48_000.0  # Lucid 50K Pro starting trail


def load_bars():
    df = pd.read_csv(CSV, parse_dates=["ts"], index_col="ts").sort_index()
    df = df[(df["high"] >= df["low"])]
    return df


class NaiveFillModel:
    """Stand-in for the old optimistic backtest behaviour: limits fill at
    intended price the instant a bar touches them; stops fill at trigger
    + 0.25pt; targets are LIMIT fills with 100% fill probability. Used
    to show the OLD backtest's optimistic baseline."""
    def __init__(self):
        pass

    def check_limit_fill(self, order, bar, ctx):
        from engine.types import Fill, Side
        bar_low = float(bar["low"]); bar_high = float(bar["high"])
        touched = (order.side is Side.LONG and bar_low <= order.price) or \
                  (order.side is Side.SHORT and bar_high >= order.price)
        if not touched: return None
        return Fill(order_side=order.side, intended_price=order.price,
                    fill_price=order.price, qty=order.qty,
                    ts=bar.name.to_pydatetime() if hasattr(bar.name, "to_pydatetime") else bar.name,
                    latency_ms=200.0, slippage_pts=0.0)

    def fill_stop(self, order, bar, ctx):
        from engine.types import Fill, Side
        bar_low = float(bar["low"]); bar_high = float(bar["high"])
        if order.side is Side.SHORT:
            triggered = bar_low <= order.trigger_price
            fill_px = order.trigger_price - 0.25
        else:
            triggered = bar_high >= order.trigger_price
            fill_px = order.trigger_price + 0.25
        if not triggered: return None
        return Fill(order_side=order.side, intended_price=order.trigger_price,
                    fill_price=fill_px, qty=order.qty,
                    ts=bar.name.to_pydatetime() if hasattr(bar.name, "to_pydatetime") else bar.name,
                    latency_ms=50.0, slippage_pts=0.25)

    def fill_market(self, side, qty, bar, ctx):
        from engine.types import Fill
        close = float(bar["close"])
        slip = 0.25 if side.value == "SHORT" else 0.25
        fill_px = close - slip if side.value == "SHORT" else close + slip
        return Fill(order_side=side, intended_price=close,
                    fill_price=fill_px, qty=qty,
                    ts=bar.name.to_pydatetime() if hasattr(bar.name, "to_pydatetime") else bar.name,
                    latency_ms=200.0, slippage_pts=slip)


def make_account():
    return AccountState(
        balance=STARTING_BAL,
        starting_balance=STARTING_BAL,
        trail_floor=TRAIL_FLOOR_INITIAL,
        today_pnl=0.0,
        today_trades=0,
        consecutive_losses=0,
    )


def make_runtime(label: str, *, use_sim_fills: bool, use_risk: bool):
    strategy = PullbackImpulse()
    fill_model = SimFillModel(SimFillParams(seed=42)) if use_sim_fills else NaiveFillModel()
    if use_risk:
        risk = RiskEngine([
            ActiveLockoutGate(),
            DailyLossLimitGate(limit_usd=700.0),
            TrailFloorBufferGate(min_buffer_usd=800.0),
            ConsecutiveLossesGate(max_losses=4, pause_minutes=60),
            TradingWindowGate(disabled_windows=[(7, 13)]),
            NewsBlackoutGate(enabled=False),  # no calendar wired yet
            MaxTradesPerDayGate(max_trades=80),
            CooldownGate(seconds=60),
            TrailDistanceSizerGate(),
        ])
    else:
        risk = RiskEngine([])  # no-op
    return Runtime(
        strategy=strategy,
        fill_model=fill_model,
        risk_engine=risk,
        account=make_account(),
        strategy_params={"TARGET_PTS": 12.0},
        default_qty=2,
    )


HISTORY_BARS = 240


def run_backtest(bars: pd.DataFrame, rt: Runtime, label: str,
                 start_bar: int = HISTORY_BARS) -> dict:
    print(f"\n=== RUN: {label} ===")
    n = len(bars)
    last_ny_date = None
    progress_every = max(1, (n - start_bar) // 10)
    for i in range(start_bar, n):
        bar = bars.iloc[i]
        now = bar.name
        if now.tz is None:
            now = now.tz_localize("UTC")
        now = now.to_pydatetime()
        history = bars.iloc[max(0, i - HISTORY_BARS + 1):i + 1]
        ctx = build_market_context(history, now)
        # NY day roll: NY date = current ET date with 16:00 rollover
        # (simplified, ignores DST). UTC -> ET = -4hr; NY date rolls at 16 ET = 20 UTC.
        try:
            from engine.market_context import ET_OFFSET_HOURS
            ny_date = (now + timedelta(hours=ET_OFFSET_HOURS - 16)).date()
        except Exception:
            ny_date = now.date()
        if last_ny_date is not None and ny_date != last_ny_date:
            rt.roll_ny_day(now)
        last_ny_date = ny_date

        rt.on_bar(bar, history, now, ctx)
        # Update trail floor: peak-EOD high - 2000, but only roll EOD on day change
        if rt.account.balance - 2000 > rt.account.trail_floor:
            rt.account.trail_floor = rt.account.balance - 2000

        if (i - start_bar) % progress_every == 0:
            pct = 100 * (i - start_bar) / max(1, n - start_bar - 1)
            cum = sum(t.pnl_usd(2.0, 0.74) for t in rt.closed_trades)
            print(f"  {pct:5.1f}%  bar {now}  "
                  f"trades={len(rt.closed_trades)}  "
                  f"cum=${cum:+,.0f}  bal=${rt.account.balance:,.0f}",
                  flush=True)

    # Final stats
    return summarize(rt.closed_trades, rt.account, rt.risk.denial_counts, label)


def summarize(closed_trades, account, denial_counts, label):
    if not closed_trades:
        print(f"  {label}: 0 trades closed")
        return {"label": label, "n": 0}
    n = len(closed_trades)
    pnls = [t.pnl_usd(2.0, 0.74) for t in closed_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    total = sum(pnls)
    wr = 100 * len(wins) / n
    rr = (-np.mean(wins) / np.mean(losses)) if wins and losses else 0.0
    exp_per_trade = total / n
    # Equity curve + max DD
    eq = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    dd = float((peak - eq).max())
    # Per-day
    by_day = {}
    for t in closed_trades:
        d = t.closed_at.date()
        by_day.setdefault(d, 0)
        by_day[d] += t.pnl_usd(2.0, 0.74)
    worst_day = min(by_day.values()) if by_day else 0
    best_day = max(by_day.values()) if by_day else 0
    n_breach = sum(1 for v in by_day.values() if v <= -1200)
    # Span
    span_d = (closed_trades[-1].closed_at - closed_trades[0].closed_at).days
    months = span_d / 30.44 if span_d > 0 else 0.01
    monthly = (total / STARTING_BAL) * 100 / months
    # Stop slippage stats
    slips = [t.exit_fill.slippage_pts for t in closed_trades
             if t.exit_reason.value == "stop"]
    avg_stop_slip = float(np.mean(slips)) if slips else 0
    # Fast stops (< 60s)
    fast_stops = sum(1 for t in closed_trades
                     if t.exit_reason.value == "stop" and t.hold_seconds < 60)
    all_stops = sum(1 for t in closed_trades if t.exit_reason.value == "stop")
    print(f"  Trades:        {n:,}")
    print(f"  Win rate:      {wr:.1f}%")
    print(f"  Realized RR:   {rr:.2f}")
    print(f"  Expectancy:    ${exp_per_trade:+.2f}/trade")
    print(f"  Total P&L:     ${total:+,.0f}")
    print(f"  Monthly ret:   {monthly:+.2f}%")
    print(f"  Max DD:        ${dd:,.0f}")
    print(f"  Worst day:     ${worst_day:+,.0f}")
    print(f"  Best day:      ${best_day:+,.0f}")
    print(f"  DLL breaches:  {n_breach}")
    print(f"  Avg stop slip: {avg_stop_slip:.2f}pt")
    print(f"  Fast stops:    {fast_stops}/{all_stops}")
    if denial_counts:
        print(f"  Risk denials by reason:")
        for k, v in sorted(denial_counts.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {k}: {v}")
    return {
        "label": label, "n": n, "wr": wr, "rr": rr, "exp": exp_per_trade,
        "total": total, "monthly": monthly, "max_dd": dd,
        "worst_day": worst_day, "best_day": best_day, "dll_breaches": n_breach,
        "avg_stop_slip": avg_stop_slip,
        "denials": denial_counts,
    }


def main():
    print("Loading 1-min Polygon data...")
    bars = load_bars()
    print(f"  {len(bars):,} bars, {bars.index.min()} → {bars.index.max()}")

    # Restrict to last 6 months for speed (we already have 6mo + 30d + 7d numbers)
    cutoff = bars.index.max() - timedelta(days=180)
    bars = bars[bars.index >= cutoff]
    print(f"  Restricted to last 180 days: {len(bars):,} bars")

    results = []
    print("\n" + "="*70)
    print("A. NAIVE: optimistic fills + no risk gates (matches old backtest)")
    print("="*70)
    rt_a = make_runtime("A", use_sim_fills=False, use_risk=False)
    r_a = run_backtest(bars, rt_a, "A. NAIVE")
    results.append(r_a)

    print("\n" + "="*70)
    print("B. REALISTIC FILLS: SimFillModel, but no risk gates")
    print("="*70)
    rt_b = make_runtime("B", use_sim_fills=True, use_risk=False)
    r_b = run_backtest(bars, rt_b, "B. REALISTIC FILLS")
    results.append(r_b)

    print("\n" + "="*70)
    print("C. FULL: SimFillModel + all risk gates (production target)")
    print("="*70)
    rt_c = make_runtime("C", use_sim_fills=True, use_risk=True)
    r_c = run_backtest(bars, rt_c, "C. FULL")
    results.append(r_c)

    # Side-by-side
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"{'metric':<22} {'A.naive':>12} {'B.real_fills':>14} {'C.full':>12}")
    for k, label in [("n","trades"), ("wr","win rate %"),
                      ("exp","$/trade"), ("monthly","monthly %"),
                      ("max_dd","max DD $"),
                      ("worst_day","worst day"), ("dll_breaches","DLL breaches"),
                      ("avg_stop_slip","stop slip pt")]:
        a = results[0].get(k, 0) if results[0] else 0
        b = results[1].get(k, 0) if results[1] else 0
        c = results[2].get(k, 0) if results[2] else 0
        print(f"  {label:<20} {a:>12.2f} {b:>14.2f} {c:>12.2f}")


if __name__ == "__main__":
    main()
