"""
Fibonacci 50% retracement strategy under FULL Lucid 50K Pro Funded rules.

Lucid constants (from research/lucid_guard.py):
  Start balance      : $50,000
  Initial trail floor: $48,000   (max loss = $2,000 below start)
  Trail drop         :  $2,000   (trail follows balance, never closer)
  Trail locks at     : $52,000   (peak EOD; then floor = $50,000 break-even)
  Daily Loss Limit   :  $1,200   (auto-flatten at this loss)
  Max MNQ            :  40       (1 MNQ and 20 MNQ both well within)
  Profit target      :  $500     (first payout eligibility)

Cost model:
  Commission RT      : $0.50 per MNQ per side ($1.00 round trip)
  Slippage           : 1 tick (0.25pt) per side = $0.50 per MNQ per side
  Total              : ~$2.00 per MNQ per RT

Tests two sizes:
  * 1 MNQ  — conservative
  * 20 MNQ — aggressive (half of Lucid's max)

Strategy is unchanged from fib_50_retrace_sim.py — confirmed swing pivots,
50% retrace touch, wide swing-extreme stop. Same engine.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NY = "America/New_York"

# Lucid rules
START_BAL = 50_000.0
INITIAL_TRAIL = 48_000.0
TRAIL_DROP = 2_000.0
TRAIL_LOCK_AT = 52_000.0
TRAIL_LOCKED_FLOOR = 50_000.0
DLL = 1_200.0
TRAIL_SAFETY = 300.0          # extra buffer above trail (per lucid_guard default)
MAX_MNQ = 40

# Fib strategy
PIVOT_K = 5
MIN_LEG_PTS = 20
MAX_HOLD_BARS = 96
MAX_SETUP_AGE = 50
MNQ_PER_PT = 2.0

# Costs
COMM_PER_MNQ_RT = 1.00        # $1 round trip per MNQ (commission)
SLIP_PT_PER_SIDE = 0.25       # 1 tick per side


def find_pivots_vec(high, low, k):
    h = high.to_numpy(); l = low.to_numpy()
    rmax = pd.Series(h).rolling(2 * k + 1, center=True).max().to_numpy()
    rmin = pd.Series(l).rolling(2 * k + 1, center=True).min().to_numpy()
    is_h = (h == rmax) & np.isfinite(rmax)
    is_l = (l == rmin) & np.isfinite(rmin)
    highs = [(int(i), float(h[i])) for i in np.where(is_h)[0]]
    lows = [(int(i), float(l[i])) for i in np.where(is_l)[0]]
    return highs, lows


def build_pivot_track(highs, lows, k, n):
    rh_src = np.full(n, -1, dtype=np.int32)
    rl_src = np.full(n, -1, dtype=np.int32)
    rh_val = np.full(n, np.nan)
    rl_val = np.full(n, np.nan)
    h_idx = l_idx = 0
    cur_h_src, cur_h_val = -1, np.nan
    cur_l_src, cur_l_val = -1, np.nan
    for t in range(n):
        while h_idx < len(highs) and highs[h_idx][0] + k <= t:
            cur_h_src, cur_h_val = highs[h_idx]; h_idx += 1
        while l_idx < len(lows) and lows[l_idx][0] + k <= t:
            cur_l_src, cur_l_val = lows[l_idx]; l_idx += 1
        rh_src[t] = cur_h_src; rh_val[t] = cur_h_val
        rl_src[t] = cur_l_src; rl_val[t] = cur_l_val
    return rh_src, rh_val, rl_src, rl_val


def simulate_trade(entry_loc, side, entry_px, stop_px, target_px, arr):
    n = len(arr)
    end = min(entry_loc + MAX_HOLD_BARS, n - 1)
    for j in range(entry_loc, end + 1):
        _, h, l, c = arr[j]
        if side == "LONG":
            if l <= stop_px:   return j, stop_px,  "stop"
            if h >= target_px: return j, target_px, "target"
        else:
            if h >= stop_px:   return j, stop_px,  "stop"
            if l <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def cost_per_trade(n_mnq: int) -> float:
    """Commission + slippage round-trip in dollars."""
    return n_mnq * COMM_PER_MNQ_RT + n_mnq * SLIP_PT_PER_SIDE * 2.0 * MNQ_PER_PT


def run_lucid_sim(nq, n_mnq, model_costs=True, slice_label=""):
    """Run Fib 50% strategy with full Lucid funded rules on the given slice."""
    rh_src, rh_val, rl_src, rl_val = build_pivot_track(
        *find_pivots_vec(nq["high"], nq["low"], PIVOT_K), PIVOT_K, len(nq))
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    ny_dates = pd.DatetimeIndex(nq.index.tz_convert(NY)).date
    n = len(nq)

    balance = START_BAL
    peak_eod = START_BAL
    trail_floor = INITIAL_TRAIL
    trail_locked = False
    daily_pnl = 0.0
    current_date = ny_dates[0]
    days_traded = 0
    account_blown = False
    blown_at = None
    daily_pnl_log = []          # (date, daily_pnl, balance_eod)

    trades = []
    blocked_dll = 0
    blocked_trail = 0
    active_until = -1
    used = set()

    cpt = cost_per_trade(n_mnq) if model_costs else 0.0
    dollar_per_pt = n_mnq * MNQ_PER_PT

    for t in range(n - 1):
        bar_date = ny_dates[t]
        if bar_date != current_date:
            # close out previous day
            daily_pnl_log.append((current_date, daily_pnl, balance))
            days_traded += 1
            # EOD trail handling
            if balance > peak_eod:
                peak_eod = balance
            if not trail_locked and peak_eod >= TRAIL_LOCK_AT:
                trail_locked = True
                trail_floor = TRAIL_LOCKED_FLOOR
            if not trail_locked:
                new_floor = balance - TRAIL_DROP
                if new_floor > trail_floor:
                    trail_floor = new_floor
            current_date = bar_date
            daily_pnl = 0.0

        if account_blown:
            continue
        if daily_pnl <= -DLL:
            continue                  # day already auto-flattened
        if t < active_until:
            continue
        if rh_src[t] < 0 or rl_src[t] < 0 or rh_src[t] == rl_src[t]:
            continue
        leg = abs(rh_val[t] - rl_val[t])
        if leg < MIN_LEG_PTS:
            continue
        p1_src = max(rh_src[t], rl_src[t])
        if t - (p1_src + PIVOT_K) > MAX_SETUP_AGE:
            continue
        key = (int(rh_src[t]), int(rl_src[t]))
        if key in used:
            continue
        level50 = (rh_val[t] + rl_val[t]) / 2.0
        side = None
        if rh_src[t] < rl_src[t]:
            if arr[t, 1] >= level50: side = "SHORT"
        else:
            if arr[t, 2] <= level50: side = "LONG"
        if side is None:
            continue
        entry_px = float(arr[t + 1, 0])
        if side == "SHORT":
            stop_px = float(rh_val[t]); target_px = (level50 + rl_val[t]) / 2.0
        else:
            stop_px = float(rl_val[t]); target_px = (level50 + rh_val[t]) / 2.0
        risk_pts = abs(stop_px - entry_px)
        worst_loss = risk_pts * dollar_per_pt + cpt
        # Lucid gate 1 — DLL pre-check
        if daily_pnl - worst_loss <= -DLL:
            blocked_dll += 1; used.add(key); continue
        # Lucid gate 2 — trail-floor pre-check (with safety margin)
        if balance - worst_loss <= trail_floor + TRAIL_SAFETY:
            blocked_trail += 1; used.add(key); continue

        exit_loc, exit_px, exit_r = simulate_trade(t + 1, side, entry_px,
                                                   stop_px, target_px, arr)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        gross = pnl_pts * dollar_per_pt
        net = gross - cpt
        balance += net
        daily_pnl += net

        trades.append({
            "date": str(bar_date),
            "entry_ts": nq.index[t + 1],
            "exit_ts": nq.index[exit_loc],
            "side": side, "entry_px": entry_px, "exit_px": float(exit_px),
            "pnl_pts": float(pnl_pts), "gross_pnl": float(gross),
            "net_pnl": float(net), "balance": float(balance),
            "exit_reason": exit_r,
        })

        if balance <= trail_floor:
            account_blown = True
            blown_at = nq.index[t + 1]
        active_until = exit_loc + 1
        used.add(key)

    # close final day
    if current_date is not None:
        daily_pnl_log.append((current_date, daily_pnl, balance))
        days_traded += 1

    return {
        "label": slice_label,
        "n_mnq": n_mnq,
        "trades": trades,
        "daily_log": daily_pnl_log,
        "final_balance": balance,
        "peak_eod": peak_eod,
        "trail_floor": trail_floor,
        "trail_locked": trail_locked,
        "days_traded": days_traded,
        "account_blown": account_blown,
        "blown_at": blown_at,
        "blocked_dll": blocked_dll,
        "blocked_trail": blocked_trail,
    }


def report(res, label):
    print(f"\n{'='*88}\n{label}  —  n_mnq={res['n_mnq']}\n{'='*88}")
    if not res["trades"]:
        print("  No trades.")
        return
    tdf = pd.DataFrame(res["trades"])
    pnl = tdf["net_pnl"].to_numpy()
    bal = tdf["balance"].to_numpy()
    n = len(tdf)
    wins = int((pnl > 0).sum())
    gw = float(pnl[pnl > 0].sum())
    gl = float(-pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else float("inf")
    cum = np.cumsum(pnl)
    maxdd_dollar = float((cum - np.maximum.accumulate(cum)).min())
    # account-balance drawdown vs running peak
    bal_peak = np.maximum.accumulate(bal)
    bal_dd = float((bal - bal_peak).min())

    daily = pd.DataFrame(res["daily_log"], columns=["date", "daily_pnl", "balance_eod"])
    profitable_days = int((daily["daily_pnl"] > 0).sum())
    losing_days = int((daily["daily_pnl"] < 0).sum())
    flat_days = int((daily["daily_pnl"] == 0).sum())
    days_dll_hit = int((daily["daily_pnl"] <= -DLL).sum())
    best_day = float(daily["daily_pnl"].max())
    worst_day = float(daily["daily_pnl"].min())

    # Consistency check — biggest day vs total
    total_net = float(tdf["net_pnl"].sum())
    if total_net > 0 and best_day / total_net > 0.40:
        consistency_violated = True
    else:
        consistency_violated = False

    targets = int((tdf["exit_reason"] == "target").sum())
    stops = int((tdf["exit_reason"] == "stop").sum())
    timeouts = int((tdf["exit_reason"] == "timeout").sum())

    print(f"\n  --- Account ---")
    print(f"  Start balance      : ${START_BAL:>10,.0f}")
    print(f"  Final balance      : ${res['final_balance']:>10,.0f}")
    print(f"  Net P&L            : ${res['final_balance'] - START_BAL:>+10,.0f}")
    print(f"  Peak EOD balance   : ${res['peak_eod']:>10,.0f}")
    print(f"  Final trail floor  : ${res['trail_floor']:>10,.0f}   "
          f"locked={res['trail_locked']}")
    print(f"  ACCOUNT BLOWN?     : {res['account_blown']}"
          f"{'  blown at: ' + str(res['blown_at']) if res['account_blown'] else ''}")

    print(f"\n  --- Trades ---")
    print(f"  Trades fired       : {n:,}")
    print(f"  Trades/month       : {n / (8.1 * 12):.1f}")
    print(f"  Long / Short       : {(tdf['side']=='LONG').sum()} / "
          f"{(tdf['side']=='SHORT').sum()}")
    print(f"  Win rate           : {wins/n*100:.1f}%")
    print(f"  Profit factor      : {pf:.2f}")
    print(f"  Avg per trade      : ${pnl.mean():+,.2f}")
    print(f"  Largest win / loss : ${pnl.max():+,.0f} / ${pnl.min():+,.0f}")
    print(f"  Exit mix           : target={targets}  stop={stops}  timeout={timeouts}")
    print(f"  Cost per trade     : ${cost_per_trade(res['n_mnq']):.2f}")

    print(f"\n  --- Lucid gating ---")
    print(f"  Trades blocked by DLL   : {res['blocked_dll']:,}")
    print(f"  Trades blocked by trail : {res['blocked_trail']:,}")
    print(f"  Days hit DLL (auto-flat): {days_dll_hit}")

    print(f"\n  --- Days ---")
    print(f"  Days traded        : {res['days_traded']:,}")
    print(f"  Profitable / Losing/ Flat : {profitable_days} / {losing_days} / {flat_days}")
    print(f"  Best day / Worst day      : ${best_day:+,.0f} / ${worst_day:+,.0f}")

    print(f"\n  --- Risk ---")
    print(f"  Max DD (cum P&L)   : ${maxdd_dollar:+,.0f}")
    print(f"  Max DD (balance)   : ${bal_dd:+,.0f}")
    print(f"  Consistency (40%): "
          f"largest day = {best_day/total_net*100:.1f}% of total  "
          f"{'VIOLATED' if consistency_violated else 'ok'}")

    # Per-year breakdown
    tdf["year"] = pd.to_datetime(tdf["entry_ts"]).dt.year
    print(f"\n  --- Per-year breakdown ---")
    print(f"  {'year':<6}{'trades':>9}{'net P&L':>14}{'win%':>7}{'PF':>7}")
    for y, gy in tdf.groupby("year"):
        p = gy["net_pnl"].to_numpy()
        if len(p) == 0: continue
        yw = int((p > 0).sum())
        ygw = float(p[p > 0].sum())
        ygl = float(-p[p < 0].sum())
        ypf = ygw / ygl if ygl > 0 else float("inf")
        print(f"  {y:<6}{len(gy):>9,}{float(p.sum()):>+13,.0f} "
              f"{yw/len(gy)*100:>5.1f}%  {ypf:>5.2f}")


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    print("=" * 88)
    print("FIB 50% RETRACEMENT — FULL LUCID FUNDED RULES + COSTS")
    print("=" * 88)
    print(f"Bars: {len(nq):,}   range: {nq.index[0].date()} -> {nq.index[-1].date()}")
    print(f"Lucid 50K Pro: start $50k, trail $48k drop $2k, lock @$52k,")
    print(f"               DLL $1,200, max 40 MNQ, cost ~$2/MNQ RT")

    # full 8 years, multiple sizes to find Lucid bind point
    for n_mnq in (1, 2, 5, 10, 20):
        res = run_lucid_sim(nq, n_mnq, model_costs=True,
                            slice_label="full 8 years")
        report(res, f"FULL 8 YEARS, {n_mnq} MNQ")

    # Walk-forward — split chronologically
    print("\n" + "=" * 88)
    print("WALK-FORWARD — first half (train) vs second half (test)")
    print("=" * 88)
    mid = len(nq) // 2
    nq_train = nq.iloc[:mid]
    nq_test = nq.iloc[mid:]
    print(f"Train: {nq_train.index[0].date()} -> {nq_train.index[-1].date()}   "
          f"({len(nq_train):,} bars)")
    print(f"Test : {nq_test.index[0].date()} -> {nq_test.index[-1].date()}   "
          f"({len(nq_test):,} bars)")

    for n_mnq in (1, 20):
        res_tr = run_lucid_sim(nq_train, n_mnq, model_costs=True,
                               slice_label="TRAIN (first 4 yrs)")
        res_te = run_lucid_sim(nq_test, n_mnq, model_costs=True,
                               slice_label="TEST (last 4 yrs)")
        report(res_tr, f"WALK-FORWARD TRAIN, {n_mnq} MNQ")
        report(res_te, f"WALK-FORWARD TEST,  {n_mnq} MNQ")


if __name__ == "__main__":
    main()
