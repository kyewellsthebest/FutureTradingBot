"""
ICT Rejection Block strategy on NQ 5-min, 8 years — strict version.

Per the article's emphasis: real rejection blocks need a LIQUIDITY SWEEP
plus extreme wick rejection. The looser single-candle wick interpretation
produced way too many noisy blocks. This version requires:

  1. Wick SWEPT a prior N-bar high/low (real liquidity grab)
  2. Wick excursion > SD threshold (significant rejection)
  3. Candle closed back inside the swept range (rejection confirmed)
  4. Liquidity target = LARGER swing pivot (k=30) for meaningful RR

Bearish RB (SHORT): h[t] > max(h[t-N..t-1]) AND c[t] < max(h[t-N..t-1])
  AND (h[t] - max(o[t],c[t])) > SD * rolling_std
Bullish RB (LONG): mirror.

Tests three SD thresholds — 1.5, 2.0, 2.5 — and two liquidity targets.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.local_data_loader import load_intraday_5min

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SIZE = 10
MNQ_PER_PT = 2.0
SD_LOOKBACK = 50
SWEEP_LOOKBACK = 20           # wick must take out the last N bars' extreme
MAX_BLOCK_AGE = 200
MAX_HOLD_BARS = 480
STOP_BUFFER_PTS = 1
MIN_WICK_PTS = 5
MIN_TARGET_PTS = 20           # liquidity target must be at least this far


def detect_blocks(nq, sd_filter, sweep_lookback):
    o = nq["open"].to_numpy()
    h = nq["high"].to_numpy()
    l = nq["low"].to_numpy()
    c = nq["close"].to_numpy()
    rng_std = pd.Series(h - l).rolling(SD_LOOKBACK).std().to_numpy()
    blocks = []
    for t in range(max(SD_LOOKBACK, sweep_lookback), len(nq)):
        s = rng_std[t]
        if not np.isfinite(s) or s <= 0:
            continue
        prior_high = h[t - sweep_lookback:t].max()
        prior_low = l[t - sweep_lookback:t].min()
        body_top = max(o[t], c[t])
        body_bot = min(o[t], c[t])
        upper_wick = h[t] - body_top
        lower_wick = body_bot - l[t]
        # Bearish RB: liquidity sweep above + rejected back below
        if (h[t] > prior_high and c[t] < prior_high
                and upper_wick >= sd_filter * s
                and upper_wick >= MIN_WICK_PTS):
            blocks.append((t, "SHORT", float(h[t]), float(body_top)))
        # Bullish RB: liquidity sweep below + rejected back above
        if (l[t] < prior_low and c[t] > prior_low
                and lower_wick >= sd_filter * s
                and lower_wick >= MIN_WICK_PTS):
            blocks.append((t, "LONG", float(body_bot), float(l[t])))
    return blocks


def find_swings(nq, k):
    h = nq["high"].to_numpy(); l = nq["low"].to_numpy()
    n = len(h)
    hs, ls = [], []
    for t in range(k, n - k):
        if h[t] == h[t - k:t + k + 1].max():
            hs.append((t, float(h[t]), t + k))
        if l[t] == l[t - k:t + k + 1].min():
            ls.append((t, float(l[t]), t + k))
    return hs, ls


def find_liquidity(side, current_t, current_px, sh, sl):
    if side == "SHORT":
        best = None
        for _, v, conf_t in sl:
            if conf_t > current_t: break
            if v < current_px - MIN_TARGET_PTS and (best is None or v > best):
                best = v
        return best
    best = None
    for _, v, conf_t in sh:
        if conf_t > current_t: break
        if v > current_px + MIN_TARGET_PTS and (best is None or v < best):
            best = v
    return best


def sim(entry_loc, side, entry_px, stop_px, target_px, arr, max_hold):
    n = len(arr)
    end = min(entry_loc + max_hold, n - 1)
    for j in range(entry_loc, end + 1):
        _, hh, ll, cc = arr[j]
        if side == "LONG":
            if ll <= stop_px:   return j, stop_px,  "stop"
            if hh >= target_px: return j, target_px, "target"
        else:
            if hh >= stop_px:   return j, stop_px,  "stop"
            if ll <= target_px: return j, target_px, "target"
    return end, float(arr[end, 3]), "timeout"


def run_variant(nq, arr, n, blocks, sh, sl_list, label):
    blocks = sorted(blocks, key=lambda b: b[0])
    trades = []
    active = []
    block_idx = 0
    active_until = -1
    for t in range(n - 1):
        while block_idx < len(blocks) and blocks[block_idx][0] <= t:
            active.append(blocks[block_idx])
            block_idx += 1
        active = [b for b in active if t - b[0] <= MAX_BLOCK_AGE]
        if t < active_until:
            continue
        triggered = None
        for b in active:
            form_t, side, top, bot = b
            if t <= form_t:
                continue
            if side == "SHORT" and arr[t, 1] >= bot:
                entry_px = bot
                stop_px = top + STOP_BUFFER_PTS
                tgt = find_liquidity("SHORT", t, entry_px, sh, sl_list)
                if tgt is None: continue
                triggered = (b, entry_px, stop_px, tgt, side); break
            if side == "LONG" and arr[t, 2] <= top:
                entry_px = top
                stop_px = bot - STOP_BUFFER_PTS
                tgt = find_liquidity("LONG", t, entry_px, sh, sl_list)
                if tgt is None: continue
                triggered = (b, entry_px, stop_px, tgt, side); break
        if triggered is None:
            continue
        b, entry_px, stop_px, target_px, side = triggered
        if t + 1 >= n:
            active.remove(b); continue
        exit_loc, exit_px, exit_r = sim(t + 1, side, entry_px,
                                        stop_px, target_px, arr, MAX_HOLD_BARS)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        risk = abs(stop_px - entry_px)
        reward = abs(target_px - entry_px)
        rr = reward / risk if risk > 0 else 0
        trades.append({
            "side": side,
            "entry_ts": nq.index[t + 1], "exit_ts": nq.index[exit_loc],
            "entry_px": entry_px, "exit_px": float(exit_px),
            "stop_px": float(stop_px), "target_px": float(target_px),
            "exit_reason": exit_r,
            "pnl_pts": float(pnl_pts),
            "pnl_usd": float(pnl_pts * SIZE * MNQ_PER_PT),
            "rr_planned": float(rr),
        })
        active_until = exit_loc + 1
        active.remove(b)

    if not trades:
        print(f"\n{label}: no trades")
        return None
    tdf = pd.DataFrame(trades)
    n_t = len(tdf)
    wins = int((tdf["pnl_usd"] > 0).sum())
    total = float(tdf["pnl_usd"].sum())
    avg = float(tdf["pnl_usd"].mean())
    cum = tdf["pnl_usd"].cumsum().to_numpy()
    maxdd = float((cum - np.maximum.accumulate(cum)).min())
    gw = float(tdf[tdf["pnl_usd"] > 0]["pnl_usd"].sum())
    gl = float(abs(tdf[tdf["pnl_usd"] < 0]["pnl_usd"].sum()))
    pf = gw / gl if gl > 0 else float("inf")
    avg_rr = float(tdf["rr_planned"].mean())
    targets = int((tdf["exit_reason"] == "target").sum())
    stops = int((tdf["exit_reason"] == "stop").sum())
    timeouts = int((tdf["exit_reason"] == "timeout").sum())
    print(f"\n--- {label} ---")
    print(f"  trades={n_t:,}  /mo={n_t/(8.1*12):.1f}  "
          f"win={wins/n_t*100:.1f}%  RR=1:{avg_rr:.1f}  "
          f"PF={pf:.2f}  total=${total:+,.0f}  "
          f"avg=${avg:+,.0f}  maxDD=${maxdd:+,.0f}")
    print(f"  T/S/X: {targets}/{stops}/{timeouts}  "
          f"largest +${tdf['pnl_usd'].max():,.0f} / "
          f"-${abs(tdf['pnl_usd'].min()):,.0f}")
    return {"n": n_t, "win_rate": wins / n_t, "pf": pf, "total": total,
            "maxdd": maxdd, "avg_rr": avg_rr}


def main() -> None:
    nq = load_intraday_5min("nq")
    if nq.index.tz is None: nq.index = nq.index.tz_localize("UTC")
    nq = nq.sort_index()
    print("=" * 84)
    print("ICT REJECTION BLOCK (sweep + SD filter) — NQ 5-min, 8 yrs, 10 MNQ")
    print("=" * 84)
    print(f"Bars: {len(nq):,}")

    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)

    # Build TWO liquidity-pivot sets — small (k=10) and large (k=30)
    print("\nPivots for liquidity targets ...")
    sh10, sl10 = find_swings(nq, 10)
    sh30, sl30 = find_swings(nq, 30)
    print(f"  k=10: highs={len(sh10):,} lows={len(sl10):,}")
    print(f"  k=30: highs={len(sh30):,} lows={len(sl30):,}")

    # Sweep × SD-threshold grid
    for sd in (1.5, 2.0, 2.5):
        for sweep_lb in (20, 50):
            blocks = detect_blocks(nq, sd, sweep_lb)
            n_s = sum(1 for b in blocks if b[1] == "SHORT")
            n_l = sum(1 for b in blocks if b[1] == "LONG")
            print(f"\n>>> SD={sd}, sweep={sweep_lb}-bar: "
                  f"{n_s} short RBs, {n_l} long RBs")
            run_variant(nq, arr, n, blocks, sh10, sl10,
                        f"SD={sd}/sweep={sweep_lb}  target=k10")
            run_variant(nq, arr, n, blocks, sh30, sl30,
                        f"SD={sd}/sweep={sweep_lb}  target=k30")


if __name__ == "__main__":
    main()
