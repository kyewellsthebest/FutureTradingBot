"""Round 47: BP-FRONTIER battery. Avenues that only exist now that
FADESZ-BP (trend-day guard + tight stop) is the incumbent:
  A1 asymmetric guard: on an up-trend day block only shorts (fading
     INTO the trend); keep pullback-fade longs. And vice versa.
  A2 Brownian-normalized trend call: |c - day_open| / (ATR*sqrt(mins))
     -> detects trend days EARLY instead of waiting for 8 ATR.
  A3 efficiency-ratio gate: |net 120m move| / path length > E = trend.
  A4 exit acceleration: if the guard trips while holding, exit early.
  A5 stop cooldown: disaster stop firing = trend confirmation -> no
     entries for 60 min.
  A6 range-boost ladder: 3-lot only while day is still range-bound.
Baseline: FADESZ-BP {MOMR 10/1.2, dt 8, ladder 2/4, market, hold 15,
dis 60}. Dual-tape harness from round 46 (2026 folds + 2023-24 regime
pools; 2025 held out for the winner only).
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R

HN = R.HN


def prep(D):
    """Signed day-trend, minutes-since-open, efficiency ratio."""
    c, hrs, atr, idx = D["c"], D["hrs"], D["atr"], D["idx"]
    day = idx.normalize()
    rth_open = pd.Series(np.where(hrs >= 14.0, c, np.nan), index=idx) \
        .groupby(day).transform("first").to_numpy()
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    D["sdt"] = np.nan_to_num((c - rth_open) / pos_atr)      # signed ATRs
    mins = np.clip((hrs - 14.0) * 60.0, 1.0, None)
    D["dtn"] = np.nan_to_num(np.abs(c - rth_open)
                             / (pos_atr * np.sqrt(mins)))
    net = np.abs(c - np.roll(c, 120)); net[:120] = 0
    path = pd.Series(np.abs(np.diff(c, prepend=c[0]))).rolling(120) \
        .sum().to_numpy()
    D["er"] = np.nan_to_num(net / np.where(np.nan_to_num(path) > 0,
                                           path, np.inf))


def sim47(cfg, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr = D["c"], D["atr"]
    bts, nb, days = D["bts"], D["nb"], D["days"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    mom = D["moms"][10]
    thr = 1.2 * ninf
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    mag = np.abs(mom) / pos_atr
    sig = np.where(D["rth"], raw, 0)
    sdt, dtn, er = D["sdt"], D["dtn"], D["er"]
    g = cfg["guard"]
    if g[0] == "dt":
        sig = np.where(np.abs(sdt) > g[1], 0, sig)
    elif g[0] == "asym":
        # day up > +g[1] ATR: block shorts (sig=-1). day down: block longs.
        sig = np.where((sdt > g[1]) & (sig == -1), 0, sig)
        sig = np.where((sdt < -g[1]) & (sig == 1), 0, sig)
    elif g[0] == "dtn":
        sig = np.where(dtn > g[1], 0, sig)
    elif g[0] == "er":
        sig = np.where(er > g[1], 0, sig)
    elif g[0] == "dt_er":
        sig = np.where((np.abs(sdt) > g[1]) | (er > g[2]), 0, sig)
    l1, l2 = cfg["ladder"]
    rboost = cfg.get("rboost")          # 3-lot only if |sdt| < rboost
    xaccel = cfg.get("xaccel")          # early exit if |sdt| > xaccel
    cooldown = cfg.get("cooldown", 0)   # minutes after disaster stop
    dis = cfg["dis"]
    hold = 15
    sidx = np.flatnonzero(sig)
    out_t = []; out_p = []
    busy = 0; pause_until = 0
    for i in sidx:
        if bts[i] < busy or bts[i] < pause_until:
            continue
        s = sig[i]
        q = 3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1)
        if rboost is not None and q == 3 and abs(sdt[i]) > rboost:
            q = 2
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        xe = np.searchsorted(ts, ts[fi] + HN(hold) + R.LAT_NS, "left")
        if xe >= n: break
        if xaccel is not None:
            b0 = np.searchsorted(bts, ts[fi], "left")
            for j in range(b0 + 3, min(b0 + hold, nb)):
                if abs(sdt[j]) > xaccel:
                    xe2 = np.searchsorted(ts, bts[j] + R.LAT_NS, "left")
                    if xe2 < xe:
                        xe = xe2
                    break
        if xe >= n: break
        fill = None; k_exit = xe; dis_fired = False
        if dis is not None:
            stop_lvl = entry - dis * s
            seg2 = px[fi + 1:xe]
            if len(seg2):
                sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    k_exit = fi + 1 + int(sh[0])
                    raw_ = min(px[k_exit], stop_lvl) if s > 0 \
                        else max(px[k_exit], stop_lvl)
                    fill = raw_ - R.STOP_SLIP * s
                    dis_fired = True
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        pnl = ((fill - entry) * s * R.PT - R.FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        busy = ts[k_exit]
        if dis_fired and cooldown:
            pause_until = ts[k_exit] + HN(cooldown)
    return pd.Series(out_p,
                     index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                          utc=True))


def metrics(cfg):
    s26 = sim47(cfg, R.D26)
    folds = []
    for lo, hi in R.F26:
        f = s26[(s26.index >= pd.Timestamp(lo, tz="UTC"))
                & (s26.index < pd.Timestamp(hi, tz="UTC"))]
        wk = R.wk_of(f)
        folds.append(float(f.sum() / max(len(wk), 1)) if len(f) else -999)
    wk = R.wk_of(s26)
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    sH = sim47(cfg, R.DH)
    sH2324 = sH[sH.index < pd.Timestamp("2025-01-01", tz="UTC")]
    return dict(m26=round(min(folds)),
                all=round(float(s26.sum() / max(len(wk), 1))),
                pos=round((wk > 0).mean() * 100),
                ww=round(float(wk.min())), wd=round(float(dy.min())),
                trwk=round(len(s26) / max(len(wk), 1), 1),
                sH=round(R.pool_usd_wk(sH2324, R.STRONG_2324)),
                wH=round(R.pool_usd_wk(sH2324, R.WEAK_2324)))


def main():
    t0 = time.time()
    R.init_globals()
    prep(R.D26); prep(R.DH)
    BP = {"guard": ("dt", 8.0), "ladder": (2.0, 4.0), "dis": 60.0}
    tests = [
        ("BP baseline",            BP),
        ("A1 asym 8",              {**BP, "guard": ("asym", 8.0)}),
        ("A1 asym 6",              {**BP, "guard": ("asym", 6.0)}),
        ("A1 asym 5",              {**BP, "guard": ("asym", 5.0)}),
        ("A2 dtnorm 1.5",          {**BP, "guard": ("dtn", 1.5)}),
        ("A2 dtnorm 2.0",          {**BP, "guard": ("dtn", 2.0)}),
        ("A2 dtnorm 2.5",          {**BP, "guard": ("dtn", 2.5)}),
        ("A3 er .30",              {**BP, "guard": ("er", 0.30)}),
        ("A3 er .40",              {**BP, "guard": ("er", 0.40)}),
        ("A3 dt8 + er .35",        {**BP, "guard": ("dt_er", 8.0, 0.35)}),
        ("A4 dt8 + xaccel 8",      {**BP, "xaccel": 8.0}),
        ("A4 dt8 + xaccel 10",     {**BP, "xaccel": 10.0}),
        ("A5 dt8 + cooldown 60",   {**BP, "cooldown": 60}),
        ("A5 dt8 + cooldown 120",  {**BP, "cooldown": 120}),
        ("A6 dt8 + rboost 3",      {**BP, "rboost": 3.0}),
        ("A6 dt8 + rboost 5",      {**BP, "rboost": 5.0}),
    ]
    print(f"{'variant':<24} {'m26':>5} {'all':>5} {'pos':>4} {'ww':>6} "
          f"{'wd':>6} {'tr/wk':>6} {'sH':>5} {'wH':>6}")
    rows = {}
    for nm, cfg in tests:
        m = metrics(cfg)
        rows[nm] = m
        print(f"{nm:<24} {m['m26']:>5} {m['all']:>5} {m['pos']:>4} "
              f"{m['ww']:>6} {m['wd']:>6} {m['trwk']:>6} {m['sH']:>5} "
              f"{m['wH']:>6}", flush=True)
    with open("research/round47_results.json", "w") as f:
        json.dump(rows, f, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
