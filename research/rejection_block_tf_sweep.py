"""
ICT Rejection Block — timeframe sweep on NQ.

Friend is actively winning with this on BTC 15m / 4h. BTC has much larger
percentage moves per bar than NQ, so NQ at low TFs has wicks too small
relative to swing distances. Higher TFs should produce wicks comparable to
BTC 15m → potentially the same edge structure.

Sweeps: 15-min, 30-min, 1-hour, 4-hour, daily — same canonical rules:
  - SD-filtered wick rejection (1.5x and 2.0x)
  - Wick must sweep prior N-bar high/low (real liquidity grab)
  - Entry at opposite block edge on return
  - SL at block extreme + buffer
  - Target = next confirmed swing pivot (liquidity)
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
STOP_BUFFER_PTS = 1


def detect_blocks(nq, sd_filter, sweep_lookback, min_wick_pts):
    o = nq["open"].to_numpy()
    h = nq["high"].to_numpy()
    l = nq["low"].to_numpy()
    c = nq["close"].to_numpy()
    rng_std = pd.Series(h - l).rolling(SD_LOOKBACK).std().to_numpy()
    blocks = []
    start = max(SD_LOOKBACK, sweep_lookback)
    for t in range(start, len(nq)):
        s = rng_std[t]
        if not np.isfinite(s) or s <= 0:
            continue
        prior_high = h[t - sweep_lookback:t].max()
        prior_low = l[t - sweep_lookback:t].min()
        body_top = max(o[t], c[t])
        body_bot = min(o[t], c[t])
        upper_wick = h[t] - body_top
        lower_wick = body_bot - l[t]
        if (h[t] > prior_high and c[t] < prior_high
                and upper_wick >= sd_filter * s
                and upper_wick >= min_wick_pts):
            blocks.append((t, "SHORT", float(h[t]), float(body_top)))
        if (l[t] < prior_low and c[t] > prior_low
                and lower_wick >= sd_filter * s
                and lower_wick >= min_wick_pts):
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


def find_liquidity(side, current_t, current_px, sh, sl, min_target_pts):
    if side == "SHORT":
        best = None
        for _, v, conf_t in sl:
            if conf_t > current_t: break
            if v < current_px - min_target_pts and (best is None or v > best):
                best = v
        return best
    best = None
    for _, v, conf_t in sh:
        if conf_t > current_t: break
        if v > current_px + min_target_pts and (best is None or v < best):
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


def resample(nq5, freq):
    out = nq5.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}).dropna()
    return out


def run_strategy(nq, sd_filter, sweep_lookback, min_wick_pts, min_target_pts,
                 max_block_age, max_hold, liquidity_k):
    blocks = detect_blocks(nq, sd_filter, sweep_lookback, min_wick_pts)
    sh, sl_list = find_swings(nq, liquidity_k)
    arr = nq[["open", "high", "low", "close"]].to_numpy()
    n = len(nq)
    blocks.sort(key=lambda b: b[0])

    trades = []
    active = []
    block_idx = 0
    active_until = -1
    for t in range(n - 1):
        while block_idx < len(blocks) and blocks[block_idx][0] <= t:
            active.append(blocks[block_idx]); block_idx += 1
        active = [b for b in active if t - b[0] <= max_block_age]
        if t < active_until:
            continue
        triggered = None
        for b in active:
            form_t, side, top, bot = b
            if t <= form_t: continue
            if side == "SHORT" and arr[t, 1] >= bot:
                entry_px = bot
                stop_px = top + STOP_BUFFER_PTS
                tgt = find_liquidity("SHORT", t, entry_px, sh, sl_list, min_target_pts)
                if tgt is None: continue
                triggered = (b, entry_px, stop_px, tgt, side); break
            if side == "LONG" and arr[t, 2] <= top:
                entry_px = top
                stop_px = bot - STOP_BUFFER_PTS
                tgt = find_liquidity("LONG", t, entry_px, sh, sl_list, min_target_pts)
                if tgt is None: continue
                triggered = (b, entry_px, stop_px, tgt, side); break
        if triggered is None:
            continue
        b, entry_px, stop_px, target_px, side = triggered
        if t + 1 >= n:
            active.remove(b); continue
        exit_loc, exit_px, exit_r = sim(t + 1, side, entry_px,
                                        stop_px, target_px, arr, max_hold)
        pnl_pts = (entry_px - exit_px) if side == "SHORT" else (exit_px - entry_px)
        risk = abs(stop_px - entry_px)
        reward = abs(target_px - entry_px)
        rr = reward / risk if risk > 0 else 0
        trades.append({
            "side": side, "pnl_usd": float(pnl_pts * SIZE * MNQ_PER_PT),
            "exit_reason": exit_r, "rr_planned": float(rr),
        })
        active_until = exit_loc + 1
        active.remove(b)

    if not trades:
        return None
    pnl = np.array([t["pnl_usd"] for t in trades])
    reasons = [t["exit_reason"] for t in trades]
    n_t = len(pnl)
    wins = int((pnl > 0).sum())
    gw = float(pnl[pnl > 0].sum())
    gl = float(-pnl[pnl < 0].sum())
    cum = np.cumsum(pnl)
    return {
        "n_blocks_detected": len(blocks),
        "n": n_t,
        "wr": wins / n_t,
        "pf": gw / gl if gl > 0 else float("inf"),
        "total": float(pnl.sum()),
        "avg": float(pnl.mean()),
        "maxdd": float((cum - np.maximum.accumulate(cum)).min()),
        "avg_rr": float(np.mean([t["rr_planned"] for t in trades])),
        "n_target": reasons.count("target"),
        "n_stop":   reasons.count("stop"),
        "n_timeout": reasons.count("timeout"),
    }


def main() -> None:
    print("=" * 96)
    print("ICT REJECTION BLOCK — TIMEFRAME SWEEP — NQ, 10 MNQ ($20/pt)")
    print("=" * 96)
    nq5 = load_intraday_5min("nq")
    if nq5.index.tz is None: nq5.index = nq5.index.tz_localize("UTC")
    nq5 = nq5.sort_index()

    # per-timeframe parameter recipes (scaled by bar size)
    tfs = [
        # (label, resample_freq, sweep_lb, min_wick, min_target, max_age, max_hold, k)
        ("15-min", "15min", 20, 8,  20,  100,  96, 10),
        ("30-min", "30min", 20, 12, 30,   60,  48, 10),
        ("1-hour",  "1h",    20, 18, 50,   40,  48, 10),
        ("4-hour",  "4h",    15, 30, 100,  20,  30,  6),
        ("daily",   "1D",    10, 60, 200,  15,  10,  5),
    ]

    rows = []
    for label, freq, sweep_lb, min_w, min_tg, max_age, max_h, k in tfs:
        print(f"\n>>> Loading {label} (resampled from 5-min)...")
        nq = resample(nq5, freq) if freq != "5min" else nq5
        print(f"    bars: {len(nq):,}   range: {nq.index[0].date()} -> {nq.index[-1].date()}")
        for sd in (1.5, 2.0):
            res = run_strategy(nq, sd, sweep_lb, min_w, min_tg, max_age, max_h, k)
            if res is None:
                print(f"    SD={sd}: no trades")
                rows.append({"tf": label, "sd": sd, "n": 0})
                continue
            rows.append({"tf": label, "sd": sd, **res})
            print(f"    SD={sd}: blocks={res['n_blocks_detected']:>5}  "
                  f"trades={res['n']:>5}  win={res['wr']*100:>4.1f}%  "
                  f"RR=1:{res['avg_rr']:.1f}  PF={res['pf']:.2f}  "
                  f"total=${res['total']:>+11,.0f}  maxDD=${res['maxdd']:>+10,.0f}  "
                  f"T/S/X={res['n_target']}/{res['n_stop']}/{res['n_timeout']}")

    print("\n" + "=" * 96)
    print("SUMMARY")
    print("=" * 96)
    print(f"{'tf':<8}{'SD':>5}{'n':>7}{'win%':>7}{'RR':>7}{'PF':>6}"
          f"{'total':>14}{'maxDD':>13}{'verdict':>10}")
    print("-" * 96)
    for r in rows:
        if r.get("n", 0) == 0:
            print(f"{r['tf']:<8}{r['sd']:>5}  (no trades)")
            continue
        v = "✓" if r["total"] > 0 else "✗"
        print(f"{r['tf']:<8}{r['sd']:>5}{r['n']:>7}{r['wr']*100:>6.1f}%"
              f"{r['avg_rr']:>6.1f} {r['pf']:>6.2f}"
              f"${r['total']:>+12,.0f}${r['maxdd']:>+11,.0f}{v:>10}")


if __name__ == "__main__":
    main()
