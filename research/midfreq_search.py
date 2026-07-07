"""Mid-frequency strategy hunt: >=$3k/week at 1 MNQ, 100-300 trades/wk.

HONESTY RULES (non-negotiable, learned the hard way 2026-07-06):
  - signal on CLOSED bar i -> entry at bar i+1 OPEN (first real price
    after the signal exists) +/- 0.25pt adverse slip
  - stop fill: stop_px -/+ 0.25 slip when bar range crosses it
  - target fill: requires the bar to trade THROUGH target by 0.25
  - stop and target in the same bar -> STOP (pessimistic)
  - $1.96 fees per round trip
  - $2/pt (MNQ). No compounding, 1 contract always.

Families: Donchian breakout, EMA-deviation fade, impulse fade
(current bot's DNA, tightened), ATR thrust continuation, prev-day
level breaks -- each x timeframes x exits x sessions.

Output: CSV of every config with weekly $, trades/wk, per-year P&L,
max DD; printed frontier of qualifiers (>= $1k/wk shown, target 3k).
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import os as _os
PT = 2.0
FEES = float(_os.environ.get("SIM_FEES", "1.96"))
SLIP = float(_os.environ.get("SIM_SLIP", "0.25"))
BARS_PARQUET = "data/tick/nq_bars_1m_2p5y.parquet"
OUT = os.environ.get("MFS_OUT", "research/midfreq_results.csv")
MAX_HOLD_BARS = 240


def load_bars():
    df = pd.read_parquet(BARS_PARQUET)
    df.columns = [c.lower() for c in df.columns]
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    need = ["open", "high", "low", "close"]
    df = df[need].dropna()
    return df


def resample(df, rule):
    if rule == "1min":
        return df
    return pd.DataFrame({
        "open": df["open"].resample(rule).first(),
        "high": df["high"].resample(rule).max(),
        "low": df["low"].resample(rule).min(),
        "close": df["close"].resample(rule).last(),
    }).dropna()


def run_config_exit(o, h, l, c, atr, years, sig, mode, p1, p2, max_hold):
    """Exit-engineered variant. Modes:
      trail : p1 = ATR multiple trail from peak, p2 = hard stop pts
      time  : p1 = hold bars, p2 = hard stop pts
      eodstop: exit at hour>=20.9 (needs hrs via closure) unsupported
               here -- handled by max_hold on RTH masks instead
    Entry: next bar open + adverse slip. Both-checks pessimistic."""
    n = len(c)
    out_years, out_pnl = [], []
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
            if hard is not None:
                if (s > 0 and l[j] <= hard) or (s < 0 and h[j] >= hard):
                    pnl_pts = (hard - SLIP * s - entry) * s
                    break
            if mode == "trail":
                peak = max(peak, h[j]) if s > 0 else min(peak, l[j])
                tr_px = peak - p1 * atr[j] * s
                if (s > 0 and l[j] <= tr_px) or (s < 0 and h[j] >= tr_px):
                    pnl_pts = (tr_px - SLIP * s - entry) * s
                    break
            elif mode == "time" and j - ei >= p1:
                pnl_pts = (c[j] - entry) * s
                break
            j += 1
        if pnl_pts is None:
            j = min(j, n - 1)
            pnl_pts = (c[j] - entry) * s
        out_years.append(years[ei])
        out_pnl.append(pnl_pts * PT - FEES)
        i = j + 1
    return out_years, out_pnl


def run_config(o, h, l, c, hrs, years, sig, stop_pts, tgt_pts, max_hold):
    """sig: +1/-1/0 per bar (signal evaluated on bar close). Entry at
    next bar open with adverse slip. Returns per-trade (year, pnl$)."""
    n = len(c)
    out_years = []
    out_pnl = []
    i = 0
    while i < n - 2:
        s = sig[i]
        if s == 0:
            i += 1
            continue
        ei = i + 1
        entry = o[ei] + SLIP * s          # adverse entry slip
        stop = entry - stop_pts * s
        tgt = entry + tgt_pts * s
        j = ei
        pnl_pts = None
        end = min(n - 1, ei + max_hold)
        while j <= end:
            if s > 0:
                if l[j] <= stop:
                    pnl_pts = (stop - SLIP) - entry
                    break
                if h[j] >= tgt + 0.25:
                    pnl_pts = tgt - entry
                    break
            else:
                if h[j] >= stop:
                    pnl_pts = entry - (stop + SLIP)
                    break
                if l[j] <= tgt - 0.25:
                    pnl_pts = entry - tgt
                    break
            j += 1
        if pnl_pts is None:
            j = min(j, n - 1)
            pnl_pts = (c[j] - entry) * s
        out_years.append(years[ei])
        out_pnl.append(pnl_pts * PT - FEES)
        i = j + 1                          # single position, no overlap
    return out_years, out_pnl


def metrics(years, pnl, span_days):
    if not pnl:
        return None
    a = np.asarray(pnl)
    n = len(a)
    total = a.sum()
    wk = total / (span_days / 7.0)
    tr_wk = n / (span_days / 7.0)
    eq = np.cumsum(a)
    dd = float(np.max(np.maximum.accumulate(eq) - eq)) if n else 0.0
    yr = {}
    for y, p in zip(years, pnl):
        yr[y] = yr.get(y, 0.0) + p
    return {
        "trades": n, "trades_wk": round(tr_wk, 1),
        "usd_wk": round(wk, 1), "usd_total": round(total, 0),
        "win_pct": round(100 * float((a > 0).mean()), 1),
        "max_dd": round(dd, 0),
        "pos_years": sum(1 for v in yr.values() if v > 0),
        "n_years": len(yr),
        "yearly": {str(k): round(v, 0) for k, v in sorted(yr.items())},
    }


def main():
    t0 = time.time()
    base = load_bars()
    span_days = (base.index[-1] - base.index[0]).days
    print(f"bars={len(base):,} span={span_days}d "
          f"{base.index[0]} -> {base.index[-1]}", flush=True)

    rows = []
    def emit(name, fam, tf, sess, res):
        if res is None:
            return
        rows.append({"name": name, "family": fam, "tf": tf,
                     "session": sess, **{k: v for k, v in res.items()
                                          if k != "yearly"},
                     "yearly": json.dumps(res["yearly"])})

    for tf in ("1min", "3min", "5min"):
        df = resample(base, tf)
        o = df["open"].to_numpy(); h = df["high"].to_numpy()
        l = df["low"].to_numpy(); c = df["close"].to_numpy()
        idx = df.index
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
        years = np.asarray(idx.year)
        rth = (hrs >= 13.5) & (hrs < 20.9)
        sessions = {"all": np.ones(len(c), bool), "rth": rth}

        cs = pd.Series(c)
        hi_s = pd.Series(h); lo_s = pd.Series(l)
        tr = np.maximum(h - l, np.abs(c - np.roll(c, 1)))
        atr = pd.Series(tr).rolling(20).mean().to_numpy()

        # ---- A. Donchian breakout ------------------------------------
        for N in (8, 12, 20, 40):
            dh = hi_s.rolling(N).max().shift(1).to_numpy()
            dl = lo_s.rolling(N).min().shift(1).to_numpy()
            raw_long = c > dh
            raw_short = c < dl
            for (sp, tp) in ((4, 8), (6, 12), (8, 16), (10, 20), (10, 30),
                             (12, 40)):
                for sess, mask in sessions.items():
                    sig = np.where(raw_long & mask, 1,
                                   np.where(raw_short & mask, -1, 0))
                    ys, ps = run_config(o, h, l, c, hrs, years, sig,
                                        sp, tp, MAX_HOLD_BARS)
                    emit(f"DON_{tf}_N{N}_s{sp}t{tp}_{sess}", "don", tf,
                         sess, metrics(ys, ps, span_days))

        # ---- B. EMA-deviation fade -----------------------------------
        for span in (20, 50):
            ema = cs.ewm(span=span, adjust=False).mean().to_numpy()
            for dev in (8, 12, 18, 25):
                raw_long = c < ema - dev     # stretched down -> fade long
                raw_short = c > ema + dev
                for (sp, tp) in ((5, 8), (6, 12), (8, 16), (10, 20)):
                    for sess, mask in sessions.items():
                        sig = np.where(raw_long & mask, 1,
                                       np.where(raw_short & mask, -1, 0))
                        ys, ps = run_config(o, h, l, c, hrs, years, sig,
                                            sp, tp, 120)
                        emit(f"FADE_{tf}_e{span}d{dev}_s{sp}t{tp}_{sess}",
                             "fade", tf, sess, metrics(ys, ps, span_days))

        # ---- C. Impulse fade (bot DNA, tightened) --------------------
        for W in (2, 3):
            mom = cs.diff(W).to_numpy()
            for imp in (4, 6, 9, 14):
                raw_long = mom <= -imp       # fade the down impulse
                raw_short = mom >= imp
                for (sp, tp) in ((5, 10), (6, 15), (8, 20), (8, 30)):
                    for sess, mask in sessions.items():
                        sig = np.where(raw_long & mask, 1,
                                       np.where(raw_short & mask, -1, 0))
                        ys, ps = run_config(o, h, l, c, hrs, years, sig,
                                            sp, tp, 120)
                        emit(f"IMPF_{tf}_w{W}i{imp}_s{sp}t{tp}_{sess}",
                             "impfade", tf, sess, metrics(ys, ps, span_days))

        # ---- D. ATR thrust continuation ------------------------------
        rng = h - l
        body = c - o
        for k in (1.5, 2.0, 3.0):
            thr = rng > k * atr
            raw_long = thr & (body > 0)
            raw_short = thr & (body < 0)
            for (sp, tp) in ((6, 12), (8, 16), (10, 25), (12, 36)):
                for sess, mask in sessions.items():
                    sig = np.where(raw_long & mask, 1,
                                   np.where(raw_short & mask, -1, 0))
                    ys, ps = run_config(o, h, l, c, hrs, years, sig,
                                        sp, tp, 180)
                    emit(f"THR_{tf}_k{k}_s{sp}t{tp}_{sess}", "thrust",
                         tf, sess, metrics(ys, ps, span_days))
        # ---- E. Exit-engineered variants (round 2): trailing & time
        # exits on the signal families -- the June winners' shape.
        if os.environ.get("MFS_ROUND2", "1") == "1":
            rsi_n = 2
            delta = cs.diff()
            up = delta.clip(lower=0).rolling(rsi_n).mean()
            dn = (-delta.clip(upper=0)).rolling(rsi_n).mean()
            rsi2 = (100 - 100 / (1 + up / dn.replace(0, np.nan))).to_numpy()
            sma200 = cs.rolling(200).mean().to_numpy()
            fams = {}
            for N in (8, 20, 40):
                dh = hi_s.rolling(N).max().shift(1).to_numpy()
                dl = lo_s.rolling(N).min().shift(1).to_numpy()
                fams[f"DONX_N{N}"] = (c > dh, c < dl)
            for k in (1.5, 2.5):
                thr = (h - l) > k * atr
                fams[f"THRX_k{k}"] = (thr & (c > o), thr & (c < o))
            fams["RSI2"] = ((rsi2 < 10) & (c > sma200),
                            (rsi2 > 90) & (c < sma200))
            for W, imp in ((2, 6), (3, 9)):
                mom = cs.diff(W).to_numpy()
                fams[f"IMPX_w{W}i{imp}"] = (mom <= -imp, mom >= imp)
            for fname, (rl, rs_) in fams.items():
                for mode, p1s in (("trail", (1.5, 2.5, 4.0)),
                                  ("time", (10, 30, 60))):
                    for p1 in p1s:
                        for p2 in (0, 10, 20):
                            for sess, mask in sessions.items():
                                sig = np.where(rl & mask, 1,
                                               np.where(rs_ & mask, -1, 0))
                                ys, ps = run_config_exit(
                                    o, h, l, c, atr, years, sig,
                                    mode, p1, p2, 300)
                                emit(f"{fname}_{tf}_{mode}{p1}h{p2}_{sess}",
                                     "exit_eng", tf, sess,
                                     metrics(ys, ps, span_days))
        print(f"[{tf}] done cum_configs={len(rows)} "
              f"({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"\nALL {len(df)} configs -> {OUT} ({time.time()-t0:.0f}s)")
    q = df[(df.trades_wk >= 100) & (df.trades_wk <= 300)]
    q = q.sort_values("usd_wk", ascending=False)
    print(f"\nIN-BAND (100-300 tr/wk): {len(q)} configs; top 20:")
    cols = ["name", "usd_wk", "trades_wk", "win_pct", "max_dd",
            "pos_years", "n_years"]
    print(q[cols].head(20).to_string(index=False))
    robust = q[(q.pos_years == q.n_years)]
    print(f"\nROBUST in-band (positive every year): {len(robust)}; top 10:")
    print(robust[cols].head(10).to_string(index=False))
    best_any = df.sort_values("usd_wk", ascending=False)
    print("\nBest regardless of band (top 10):")
    print(best_any[cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
