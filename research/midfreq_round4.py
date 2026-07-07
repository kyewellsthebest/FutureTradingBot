"""Round 4: untouched signal families, walk-forward protocol built in.

Families new to the hunt (none swept in rounds 1-3):
  SMEAN  session-mean reversion (VWAP-proxy: cumulative session mean)
  ODRIVE session-open drive continuation (first 30/60 min direction)
  GAP    RTH open gap fade / follow
  EMAPB  pullback-to-EMA20 in SMA200 trend (classic dip-buy)
  NRB    range-compression breakout (NR7 / inside bar)
  HTFA   thrust continuation gated by 1h EMA alignment

Protocol (hardened after round 3's out-of-sample failure):
  - metrics reported separately for SELECT window (2023-06..2024-12)
    and BLIND window (2025-01..2026-06)
  - the script itself prints the walk-forward table: configs are
    ranked ONLY by the select window; blind results shown unpicked
  - fills: entry next-bar open + 0.25 adverse, through-tick exits,
    both-hit=stop, $1.96 fees (same as rounds 1-3)
"""
from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd

from research.midfreq_search import (FEES, PT, SLIP, load_bars, resample,
                                     run_config_exit)

OUT = "research/midfreq_results4.csv"
SPLIT = pd.Timestamp("2025-01-01", tz="UTC")


def metrics_split(idx_ns, years, pnl, ts_list):
    if not pnl:
        return None
    a = np.asarray(pnl)
    t = pd.to_datetime(np.asarray(ts_list), utc=True)
    sel = t < SPLIT
    blind = ~sel
    def wk(mask, days):
        return round(float(a[mask].sum()) / max(days / 7.0, 1), 1)
    sel_days = 560   # 2023-06 .. 2024-12
    blind_days = 533  # 2025-01 .. 2026-06
    return {
        "trades": len(a),
        "trades_wk": round(len(a) / (1093 / 7.0), 1),
        "sel_usd_wk": wk(sel, sel_days),
        "blind_usd_wk": wk(blind, blind_days),
        "sel_total": round(float(a[sel].sum()), 0),
        "blind_total": round(float(a[blind].sum()), 0),
        "win_pct": round(100 * float((a > 0).mean()), 1),
    }


def run_exit_ts(o, h, l, c, atr, ts, years, sig, mode, p1, p2, max_hold):
    """run_config_exit variant that also returns exit timestamps."""
    n = len(c)
    out_pnl, out_ts, out_years = [], [], []
    i = 0
    while i < n - 2:
        s = sig[i]
        if s == 0:
            i += 1
            continue
        ei = i + 1
        entry = o[ei] + SLIP * s
        hard = entry - p2 * s if p2 > 0 else None
        peak = entry
        j = ei
        end = min(n - 1, ei + max_hold)
        pnl_pts = None
        while j <= end:
            if hard is not None and ((s > 0 and l[j] <= hard)
                                     or (s < 0 and h[j] >= hard)):
                pnl_pts = (hard - SLIP * s - entry) * s
                break
            if mode == "trail":
                peak = max(peak, h[j]) if s > 0 else min(peak, l[j])
                tp = peak - p1 * atr[j] * s
                if (s > 0 and l[j] <= tp) or (s < 0 and h[j] >= tp):
                    pnl_pts = (tp - SLIP * s - entry) * s
                    break
            elif mode == "time" and j - ei >= p1:
                pnl_pts = (c[j] - entry) * s
                break
            j += 1
        if pnl_pts is None:
            j = min(j, n - 1)
            pnl_pts = (c[j] - entry) * s
        out_pnl.append(pnl_pts * PT - FEES)
        out_ts.append(ts[j])
        out_years.append(years[ei])
        i = j + 1
    return out_years, out_pnl, out_ts


def main():
    t0 = time.time()
    base = load_bars()
    rows = []

    for tf in ("1min", "3min", "5min"):
        df = resample(base, tf)
        o = df["open"].to_numpy(); h = df["high"].to_numpy()
        l = df["low"].to_numpy(); c = df["close"].to_numpy()
        idx = df.index
        ts = idx.asi8
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        years = idx.year.to_numpy()
        days = idx.normalize()
        rth = (hrs >= 13.5) & (hrs < 20.9)
        sessions = {"all": np.ones(len(c), bool), "rth": rth}
        cs = pd.Series(c, index=idx)
        tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
        atr = pd.Series(tr).rolling(20).mean().to_numpy()

        fams = {}

        # SMEAN: session cumulative mean (VWAP proxy, no volume avail)
        day_grp = cs.groupby(days)
        smean = day_grp.expanding().mean().reset_index(level=0, drop=True)
        smean = smean.reindex(idx).to_numpy()
        for dev in (10, 18, 28):
            fams[f"SMEAN_d{dev}"] = (c < smean - dev, c > smean + dev)

        # ODRIVE: direction of 13:30-14:00 move, enter at 14:00+
        onh = pd.Series(np.where((hrs >= 13.5) & (hrs < 14.0), h, np.nan),
                        index=idx).groupby(days).transform("max").to_numpy()
        onl = pd.Series(np.where((hrs >= 13.5) & (hrs < 14.0), l, np.nan),
                        index=idx).groupby(days).transform("min").to_numpy()
        after = hrs >= 14.0
        fams["ODRIVE30"] = (after & (c > onh), after & (c < onl))

        # GAP: RTH open vs previous session close
        close_2055 = pd.Series(np.where((hrs >= 20.75) & (hrs < 20.92), c,
                                        np.nan), index=idx)
        prev_close = close_2055.groupby(days).transform("max").shift(1)
        prev_close = prev_close.groupby(days).transform(
            lambda s: s.ffill().bfill()).to_numpy()
        gap = c - prev_close
        at_open = (hrs >= 13.5) & (hrs < 13.7)
        for g in (20, 40):
            fams[f"GAPF_g{g}"] = (at_open & (gap <= -g), at_open & (gap >= g))
            fams[f"GAPC_g{g}"] = (at_open & (gap >= g), at_open & (gap <= -g))

        # EMAPB: dip to EMA20 in SMA200 uptrend
        ema20 = cs.ewm(span=20, adjust=False).mean().to_numpy()
        sma200 = cs.rolling(200).mean().to_numpy()
        up = c > sma200
        dn = c < sma200
        touch_dn = (l <= ema20) & up
        touch_up = (h >= ema20) & dn
        fams["EMAPB"] = (touch_dn, touch_up)

        # NRB: 7-bar narrowest range then break
        rng = pd.Series(h - l)
        nr7 = (rng == rng.rolling(7).min()).shift(1).fillna(False).to_numpy()
        fams["NRB"] = (nr7 & (c > np.roll(h, 1)), nr7 & (c < np.roll(l, 1)))

        # HTFA: k2.5 thrust gated by 60-bar EMA slope alignment
        ema60 = cs.ewm(span=60, adjust=False).mean()
        slope = (ema60 - ema60.shift(10)).to_numpy()
        thr = (h - l) > 2.5 * atr
        fams["HTFA_k2.5"] = (thr & (c > o) & (slope > 0),
                             thr & (c < o) & (slope < 0))

        for fname, (rl, rs_) in fams.items():
            for mode, p1s in (("time", (30, 60, 120)),
                              ("trail", (2.5, 4.0))):
                for p1 in p1s:
                    for p2 in (0, 15):
                        for sess, mask in sessions.items():
                            sig = np.where(rl & mask, 1,
                                           np.where(rs_ & mask, -1, 0))
                            ys, ps, tss = run_exit_ts(
                                o, h, l, c, atr, ts, years, sig,
                                mode, p1, p2, 300)
                            m = metrics_split(idx, ys, ps, tss)
                            if m:
                                rows.append({
                                    "name": f"{fname}_{tf}_{mode}{p1}"
                                            f"h{p2}_{sess}",
                                    "family": fname.split("_")[0],
                                    "tf": tf, "session": sess, **m})
        print(f"[{tf}] cum={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nALL {len(df)} configs -> {OUT}")
    # WALK-FORWARD TABLE: rank by SELECT window only, show blind result
    sel = df[df.sel_total > 0].sort_values("sel_usd_wk", ascending=False)
    cols = ["name", "sel_usd_wk", "blind_usd_wk", "trades_wk", "win_pct"]
    print("\nTop 25 by SELECT window (blind column = untouched verdict):")
    print(sel[cols].head(25).to_string(index=False))
    surv = sel.head(25)
    print(f"\nblind-positive among top 25: "
          f"{int((surv.blind_usd_wk > 0).sum())}/25")
    both = sel[(sel.blind_usd_wk > 0)]
    print(f"configs positive in BOTH windows: {len(both)}")
    print(both[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
