"""Round 5: next wave of untouched families. Same hardened protocol:
select on 2023-24, blind-judge 2025-26, week-tick gate for survivors.

New families:
  GAP2   gap fade/follow with the lookahead bug FIXED (true prior-day
         session close via daily shift)
  PDHL   prior-day high/low breaks with time exits
  FBR    failed-breakout reversal (break N-high, close back inside)
  CONSEC consecutive same-direction bars -> continue / fade
  FHR    first-hour range midpoint reversion
  BBSQ   Bollinger squeeze release breakout
  TDAY   trend-day rider: wide first hour + direction -> hold to close
  RNUM   round-number (x00/x50) level reactions
  PB3    3-bar pullback in EMA50 trend
  VREG   volatility-regime switch: thrust in high ATR, RSI2 in low
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from research.midfreq_search import load_bars, resample
from research.midfreq_round4 import metrics_split, run_exit_ts

OUT = "research/midfreq_results5.csv"


def main():
    t0 = time.time()
    base = load_bars()
    rows = []

    # daily series for gap/PDHL (properly shifted BY DAY, no leakage)
    d_close = base["close"].resample("1D").last().dropna()
    d_high = base["high"].resample("1D").max().dropna()
    d_low = base["low"].resample("1D").min().dropna()
    prev_close_by_day = d_close.shift(1)
    prev_high_by_day = d_high.shift(1)
    prev_low_by_day = d_low.shift(1)

    for tf in ("3min", "5min", "15min"):
        df = resample(base, tf)
        o = df["open"].to_numpy(); h = df["high"].to_numpy()
        l = df["low"].to_numpy(); c = df["close"].to_numpy()
        idx = df.index
        ts = idx.asi8
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        years = idx.year.to_numpy()
        day_key = idx.normalize()
        cs = pd.Series(c, index=idx)
        tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
        atr = pd.Series(tr).rolling(20).mean().to_numpy()
        rth = (hrs >= 13.5) & (hrs < 20.9)
        sessions = {"all": np.ones(len(c), bool), "rth": rth}

        pc = day_key.map(prev_close_by_day).to_numpy(float)
        ph = day_key.map(prev_high_by_day).to_numpy(float)
        pl_ = day_key.map(prev_low_by_day).to_numpy(float)

        fams = {}
        # GAP2 (fixed): at RTH open, distance from TRUE prior daily close
        at_open = (hrs >= 13.5) & (hrs < 13.75)
        gap = c - pc
        for g in (25, 50):
            fams[f"GAP2F_g{g}"] = (at_open & (gap <= -g), at_open & (gap >= g))
            fams[f"GAP2C_g{g}"] = (at_open & (gap >= g), at_open & (gap <= -g))
        # PDHL breaks
        fams["PDHL"] = (c > ph, c < pl_)
        # FBR: broke prior-day high intrabar but closed back inside
        fams["FBR"] = ((h > ph) & (c < ph), (l < pl_) & (c > pl_))
        # CONSEC: 4 same-color bars
        up1 = c > o
        run4 = (up1 & np.roll(up1, 1) & np.roll(up1, 2) & np.roll(up1, 3))
        dn1 = c < o
        run4d = (dn1 & np.roll(dn1, 1) & np.roll(dn1, 2) & np.roll(dn1, 3))
        fams["CONSECC"] = (run4, run4d)         # continuation
        fams["CONSECF"] = (run4d, run4)         # fade
        # FHR: first-hour range midpoint reversion after 15:00
        fhh = pd.Series(np.where((hrs >= 13.5) & (hrs < 14.5), h, np.nan),
                        index=idx).groupby(day_key).transform("max").to_numpy()
        fhl = pd.Series(np.where((hrs >= 13.5) & (hrs < 14.5), l, np.nan),
                        index=idx).groupby(day_key).transform("min").to_numpy()
        mid = (fhh + fhl) / 2
        late = hrs >= 15.0
        fams["FHR"] = (late & (c < fhl), late & (c > fhh))  # revert to mid
        # BBSQ: squeeze release
        ma20 = cs.rolling(20).mean()
        sd20 = cs.rolling(20).std()
        width = (4 * sd20).to_numpy()
        wpct = pd.Series(width).rolling(200).apply(
            lambda x: (x[-1] <= np.nanpercentile(x, 20)), raw=True
        ).fillna(0).astype(bool).to_numpy()
        upper = (ma20 + 2 * sd20).to_numpy()
        lower = (ma20 - 2 * sd20).to_numpy()
        fams["BBSQ"] = (wpct & (c > upper), wpct & (c < lower))
        # TDAY: wide+directional first hour -> ride to close
        fh_rng = fhh - fhl
        atr_day = pd.Series(atr).groupby(day_key).transform("first").to_numpy()
        wide = fh_rng > 3 * atr_day
        at2 = (hrs >= 14.5) & (hrs < 14.75)
        fams["TDAY"] = (wide & at2 & (c > mid + fh_rng / 4),
                        wide & at2 & (c < mid - fh_rng / 4))
        # RNUM: reactions at x00 levels
        dist100 = np.abs(c - np.round(c / 100) * 100)
        near = dist100 <= 2
        mom5 = cs.diff(5).to_numpy()
        fams["RNUMF"] = (near & (mom5 <= -8), near & (mom5 >= 8))
        # PB3: 3-bar pullback in EMA50 trend
        ema50 = cs.ewm(span=50, adjust=False).mean().to_numpy()
        pull3 = (c < np.roll(c, 1)) & (np.roll(c, 1) < np.roll(c, 2)) & \
                (np.roll(c, 2) < np.roll(c, 3))
        push3 = (c > np.roll(c, 1)) & (np.roll(c, 1) > np.roll(c, 2)) & \
                (np.roll(c, 2) > np.roll(c, 3))
        fams["PB3"] = (pull3 & (c > ema50), push3 & (c < ema50))
        # VREG: regime switch
        atr_hi = atr > np.nanmedian(atr) * 1.4
        thr = (h - l) > 2.5 * atr
        delta = cs.diff()
        upS = delta.clip(lower=0).rolling(2).mean()
        dnS = (-delta.clip(upper=0)).rolling(2).mean()
        rsi2 = (100 - 100 / (1 + upS / dnS.replace(0, np.nan))).to_numpy()
        sma200 = cs.rolling(200).mean().to_numpy()
        fams["VREG"] = (
            (atr_hi & thr & (c > o)) | (~atr_hi & (rsi2 < 10) & (c > sma200)),
            (atr_hi & thr & (c < o)) | (~atr_hi & (rsi2 > 90) & (c < sma200)))

        for fname, (rl, rs_) in fams.items():
            for mode, p1s in (("time", (30, 60, 120)), ("trail", (2.5, 4.0))):
                for p1 in p1s:
                    for p2 in (0, 15):
                        for sess, mask in sessions.items():
                            sig = np.where(np.nan_to_num(rl) & mask, 1,
                                           np.where(np.nan_to_num(rs_) & mask,
                                                    -1, 0))
                            ys, ps, tss = run_exit_ts(
                                o, h, l, c, atr, ts, years, sig,
                                mode, p1, p2, 300)
                            m = metrics_split(idx, ys, ps, tss)
                            if m:
                                rows.append({
                                    "name": f"{fname}_{tf}_{mode}{p1}"
                                            f"h{p2}_{sess}",
                                    "family": fname, "tf": tf,
                                    "session": sess, **m})
        print(f"[{tf}] cum={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    sel = df[df.sel_total > 0].sort_values("sel_usd_wk", ascending=False)
    cols = ["name", "sel_usd_wk", "blind_usd_wk", "trades_wk", "win_pct"]
    print(f"\nALL {len(df)} -> {OUT}")
    print("\nTop 30 by SELECT (blind = untouched verdict):")
    print(sel[cols].head(30).to_string(index=False))
    both = sel[sel.blind_usd_wk > 0]
    print(f"\npositive BOTH windows: {len(both)}; top 15:")
    print(both[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
