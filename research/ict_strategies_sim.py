"""
ICT strategies simulation — five distinct mechanical patterns on NQ 5-min,
8 years, 10 MNQ size, same framework as the user's top-tick test.

Patterns covered (the 18 user-supplied tutorials dedupe to these distinct
TRADEABLE patterns; the rest are filters/variants):

  1. Silver Bullet           — FVG in NY 10-11 ET aligned with daily bias
  2. Fair Value Gap retrace  — bias-aligned FVG; enter on retracement
  3. Order Block             — bias-aligned OB; enter on retracement
  4. Sweep + MSS             — PDH/PDL sweep followed by opposite MSS
  5. Market Structure Shift  — bias-aligned MSS; enter at next open

Filters applied across all (canonical ICT):
  - Daily bias (yesterday's close vs daily EMA20)
  - 1:2 reward-to-risk on stops anchored to structure
  - Stop has a 5-pt floor to avoid micro-stop whipsaw

Every detector lives in research.ict_signals — strictly point-in-time, no
look-ahead.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min
from research.ict_signals import (
    confirmed_swings, daily_bias, find_fvgs, find_order_blocks,
    kill_zones, liquidity_sweeps, mss_events,
)

SIZE = 10
MNQ_PER_PT = 2.0
MAX_HOLD_BARS = 576       # 48h
MIN_STOP_PTS = 5.0
MAX_STOP_PTS = 200.0      # discard structural stops wider than this


def simulate_trades(trades: list[dict], nq: pd.DataFrame) -> pd.DataFrame:
    """Walk 5-min bars from each entry until stop / target / 48h timeout.
    Stop is checked before target on any bar that could hit both."""
    idx = nq.index
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(idx)
    out = []
    for tr in trades:
        try:
            entry_loc = idx.get_loc(tr["entry_ts"])
        except KeyError:
            continue
        if entry_loc >= n - 1:
            continue
        side = tr["side"]
        entry_px, stop, target = tr["entry_px"], tr["stop_px"], tr["target_px"]
        end = min(entry_loc + MAX_HOLD_BARS, n - 1)
        exit_px = None
        exit_reason = "timeout"
        exit_ts = idx[end]
        for j in range(entry_loc, end + 1):
            o, h, l, c = arr[j]
            if side == "LONG":
                if l <= stop: exit_px, exit_reason, exit_ts = stop, "stop", idx[j]; break
                if h >= target: exit_px, exit_reason, exit_ts = target, "target", idx[j]; break
            else:
                if h >= stop: exit_px, exit_reason, exit_ts = stop, "stop", idx[j]; break
                if l <= target: exit_px, exit_reason, exit_ts = target, "target", idx[j]; break
        if exit_px is None:
            exit_px = float(arr[end, 3])
        pnl_pts = (exit_px - entry_px) if side == "LONG" else (entry_px - exit_px)
        out.append({**tr, "exit_ts": exit_ts, "exit_px": float(exit_px),
                    "exit_reason": exit_reason, "pnl_pts": float(pnl_pts),
                    "pnl_usd": float(pnl_pts * SIZE * MNQ_PER_PT)})
    return pd.DataFrame(out)


def report(name: str, df: pd.DataFrame) -> dict | None:
    if df is None or len(df) == 0:
        print(f"  {name:<28} (no trades)")
        return None
    tgt = int((df["exit_reason"] == "target").sum())
    stp = int((df["exit_reason"] == "stop").sum())
    tmo = int((df["exit_reason"] == "timeout").sum())
    wins = int((df["pnl_usd"] > 0).sum())
    total = float(df["pnl_usd"].sum())
    avg = float(df["pnl_usd"].mean())
    cum = df["pnl_usd"].cumsum().to_numpy()
    dd = float((cum - np.maximum.accumulate(cum)).min())
    print(f"  {name:<28} n={len(df):>5}  win={wins/len(df)*100:>4.0f}%"
          f"  total=${total:>+11,.0f}  avg=${avg:>+8,.0f}"
          f"  maxDD=${dd:>+11,.0f}  T/S/X={tgt}/{stp}/{tmo}")
    return {"n": int(len(df)), "win_pct": wins / len(df),
            "total_usd": total, "avg_usd": avg, "maxdd_usd": dd,
            "n_target": tgt, "n_stop": stp, "n_timeout": tmo}


# helpers to build trades with stop floor / target = 2R
def _build_long(idx, t, entry_px, stop_anchor):
    stop_px = stop_anchor - MIN_STOP_PTS
    risk = entry_px - stop_px
    if risk < MIN_STOP_PTS:
        stop_px = entry_px - MIN_STOP_PTS; risk = MIN_STOP_PTS
    if risk > MAX_STOP_PTS:
        return None
    return {"entry_ts": idx[t], "side": "LONG", "entry_px": float(entry_px),
            "stop_px": float(stop_px), "target_px": float(entry_px + 2 * risk)}


def _build_short(idx, t, entry_px, stop_anchor):
    stop_px = stop_anchor + MIN_STOP_PTS
    risk = stop_px - entry_px
    if risk < MIN_STOP_PTS:
        stop_px = entry_px + MIN_STOP_PTS; risk = MIN_STOP_PTS
    if risk > MAX_STOP_PTS:
        return None
    return {"entry_ts": idx[t], "side": "SHORT", "entry_px": float(entry_px),
            "stop_px": float(stop_px), "target_px": float(entry_px - 2 * risk)}


# ----- 1. Silver Bullet ------------------------------------------------- #
def silver_bullet_trades(nq, fvgs, bias, kz):
    trades = []
    in_sb = kz["silver_bullet"].to_numpy()
    bias_a = bias.to_numpy()
    fvg_dir = fvgs["fvg_dir"].to_numpy()
    fvg_top = fvgs["fvg_top"].to_numpy()
    fvg_bot = fvgs["fvg_bot"].to_numpy()
    o = nq["open"].to_numpy()
    idx = nq.index; n = len(nq)
    for t in range(n - 1):
        if not in_sb[t] or fvg_dir[t] == 0 or fvg_dir[t] != bias_a[t]:
            continue
        entry_px = o[t + 1]
        if fvg_dir[t] == 1:
            tr = _build_long(idx, t + 1, entry_px, fvg_bot[t])
        else:
            tr = _build_short(idx, t + 1, entry_px, fvg_top[t])
        if tr is not None:
            trades.append({**tr, "strategy": "silver_bullet"})
    return trades


# ----- 2. FVG retracement ----------------------------------------------- #
def fvg_retrace_trades(nq, fvgs, bias):
    trades = []
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy(); o = nq["open"].to_numpy()
    fvg_dir = fvgs["fvg_dir"].to_numpy()
    fvg_top = fvgs["fvg_top"].to_numpy()
    fvg_bot = fvgs["fvg_bot"].to_numpy()
    bias_a = bias.to_numpy()
    idx = nq.index; n = len(nq)
    active = []                 # (form_t, dir, top, bot)
    for t in range(n):
        if fvg_dir[t] != 0 and fvg_dir[t] == bias_a[t]:
            active.append((t, int(fvg_dir[t]), fvg_top[t], fvg_bot[t]))
        for fv in list(active):
            form_t, d, top, bot = fv
            if t <= form_t: continue
            if t - form_t > 50: active.remove(fv); continue
            if t + 1 >= n: active.remove(fv); continue
            if d == 1 and l[t] <= top and h[t] >= bot:
                tr = _build_long(idx, t + 1, o[t + 1], bot)
                if tr is not None: trades.append({**tr, "strategy": "fvg_retrace"})
                active.remove(fv)
            elif d == -1 and h[t] >= bot and l[t] <= top:
                tr = _build_short(idx, t + 1, o[t + 1], top)
                if tr is not None: trades.append({**tr, "strategy": "fvg_retrace"})
                active.remove(fv)
    return trades


# ----- 3. Order Block --------------------------------------------------- #
def order_block_trades(nq, obs, bias):
    trades = []
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy(); o = nq["open"].to_numpy()
    d_arr = obs["ob_dir"].to_numpy()
    t_arr = obs["ob_top"].to_numpy()
    b_arr = obs["ob_bot"].to_numpy()
    bias_a = bias.to_numpy()
    idx = nq.index; n = len(nq)
    active = []
    for t in range(n):
        if d_arr[t] != 0 and d_arr[t] == bias_a[t]:
            active.append((t, int(d_arr[t]), t_arr[t], b_arr[t]))
        for ob in list(active):
            form_t, d, top, bot = ob
            if t <= form_t: continue
            if t - form_t > 100: active.remove(ob); continue
            if t + 1 >= n: active.remove(ob); continue
            if d == 1 and l[t] <= top and h[t] >= bot:
                tr = _build_long(idx, t + 1, o[t + 1], bot)
                if tr is not None: trades.append({**tr, "strategy": "order_block"})
                active.remove(ob)
            elif d == -1 and h[t] >= bot and l[t] <= top:
                tr = _build_short(idx, t + 1, o[t + 1], top)
                if tr is not None: trades.append({**tr, "strategy": "order_block"})
                active.remove(ob)
    return trades


# ----- 4. Liquidity Sweep + MSS ---------------------------------------- #
def sweep_mss_trades(nq, sweeps, mss, bias):
    trades = []
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy(); o = nq["open"].to_numpy()
    sw = sweeps.to_numpy(); m = mss.to_numpy(); bias_a = bias.to_numpy()
    idx = nq.index; n = len(nq)
    pending = []
    for t in range(n - 1):
        if sw[t] == 1:  pending.append((t, 1,  float(h[t])))   # swept high
        if sw[t] == -1: pending.append((t, -1, float(l[t])))   # swept low
        for s in list(pending):
            sweep_t, sd, lvl = s
            if t <= sweep_t: continue
            if t - sweep_t > 50: pending.remove(s); continue
            if sd == 1 and m[t] == -1 and bias_a[t] == -1:
                tr = _build_short(idx, t + 1, o[t + 1], lvl)
                if tr is not None: trades.append({**tr, "strategy": "sweep_mss"})
                pending.remove(s)
            elif sd == -1 and m[t] == 1 and bias_a[t] == 1:
                tr = _build_long(idx, t + 1, o[t + 1], lvl)
                if tr is not None: trades.append({**tr, "strategy": "sweep_mss"})
                pending.remove(s)
    return trades


# ----- 5. MSS entry ----------------------------------------------------- #
def mss_entry_trades(nq, mss, bias):
    trades = []
    o = nq["open"].to_numpy()
    m = mss.to_numpy(); bias_a = bias.to_numpy()
    idx = nq.index; n = len(nq)
    sh, sl = confirmed_swings(nq, k=5)
    sh_a = sh.to_numpy(); sl_a = sl.to_numpy()
    for t in range(n - 1):
        if m[t] == 1 and bias_a[t] == 1 and not np.isnan(sl_a[t]):
            tr = _build_long(idx, t + 1, o[t + 1], sl_a[t])
            if tr is not None: trades.append({**tr, "strategy": "mss_entry"})
        elif m[t] == -1 and bias_a[t] == -1 and not np.isnan(sh_a[t]):
            tr = _build_short(idx, t + 1, o[t + 1], sh_a[t])
            if tr is not None: trades.append({**tr, "strategy": "mss_entry"})
    return trades


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None:
        nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    print("=" * 100)
    print("ICT STRATEGIES SIMULATION — NQ 5-min, 8 yrs, 10 MNQ ($20/pt)")
    print("=" * 100)
    print(f"Bars: {len(nq):,}   range: {nq.index[0].date()} -> {nq.index[-1].date()}")

    print("\nComputing signal layer ...")
    kz = kill_zones(nq.index)
    bias = daily_bias(nq)
    fvgs = find_fvgs(nq, min_atr_mult=1.5)
    obs = find_order_blocks(nq, min_atr_mult=1.5)
    mss = mss_events(nq, k=5)
    sweeps = liquidity_sweeps(nq)
    print(f"  bullish FVGs : {(fvgs['fvg_dir']==1).sum():>6,}    bearish : {(fvgs['fvg_dir']==-1).sum():>6,}")
    print(f"  bullish OBs  : {(obs['ob_dir']==1).sum():>6,}    bearish : {(obs['ob_dir']==-1).sum():>6,}")
    print(f"  bullish MSS  : {(mss==1).sum():>6,}    bearish : {(mss==-1).sum():>6,}")
    print(f"  high sweeps  : {(sweeps==1).sum():>6,}    low     : {(sweeps==-1).sum():>6,}")
    print(f"  silver-bullet bars : {kz['silver_bullet'].sum():>6,}")

    print("\nGenerating trades + simulating ...")
    runs = [
        ("1. Silver Bullet",       silver_bullet_trades(nq, fvgs, bias, kz)),
        ("2. FVG retracement",     fvg_retrace_trades(nq, fvgs, bias)),
        ("3. Order Block",         order_block_trades(nq, obs, bias)),
        ("4. Sweep + MSS",         sweep_mss_trades(nq, sweeps, mss, bias)),
        ("5. MSS entry",           mss_entry_trades(nq, mss, bias)),
    ]

    summary = {}
    for name, trades in runs:
        df = simulate_trades(trades, nq)
        summary[name] = report(name, df)

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  {'strategy':<28}{'n':>6}{'win%':>7}{'total':>14}{'avg':>11}{'maxDD':>14}")
    for name, r in summary.items():
        if r is None: continue
        print(f"  {name:<28}{r['n']:>6}{r['win_pct']*100:>6.0f}%"
              f"  ${r['total_usd']:>+11,.0f}  ${r['avg_usd']:>+8,.0f}"
              f"  ${r['maxdd_usd']:>+11,.0f}")


if __name__ == "__main__":
    main()
