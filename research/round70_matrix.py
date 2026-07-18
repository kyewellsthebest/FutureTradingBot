"""Round 70: THE QUOTES x STRATEGY MATRIX. User: take the OLD
higher-frequency strategy (FADESZ+P: no trend-day guard, no xaccel,
no disaster stop - the version that traded ~2x the signals) and run
it WITH the quote products. Then sweep every untested quote-role on
the fade family. Grid per strategy variant:
    plain | qrate GATE (skip if 1s qrate > gx10-min median) |
    CALM-WAIT (k=0.6) | GATE+CALM-WAIT
Strategies:
    OLD  = guardless fade (the 100+ tr/wk engine), flat 1
    BP   = deployed BP-Final (guard 8 / xaccel 10 / dis 60), flat 1
Extra quote roles on BP (never tested):
    HOLDMOD: hold 15m normally, but 25m when book calm at entry+10m
    WIDESTOP: dis 60 normally, 90 when frantic at entry (survive the
              last shake instead of getting tagged)
14 clean post-roll overlap days; faithful fills; $1.50/RT.
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, QDIR
from round66_qstrats import tick_day
import round54_clock as K

LAT = 65_000_000
FEES, PT, TICK = 1.50, 2.0, 0.25
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO, HI = 14.0, 20.73
CXL_NS = 180_000_000_000


def day_bars(tsd, pxd):
    m = tsd // 60_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    c = pxd[en - 1]
    h = np.maximum.reduceat(pxd, st)
    l = np.minimum.reduceat(pxd, st)
    bts = (m[st] + 1) * 60_000_000_000
    hrs = (m[st] % 1440) / 60.0
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    day_open = np.nan
    sdt = np.zeros(len(c))
    for i in range(len(c)):
        if np.isnan(day_open) and hrs[i] >= 14.0:
            day_open = c[i]
        if not np.isnan(day_open) and atr[i] and atr[i] > 0:
            sdt[i] = abs(c[i] - day_open) / atr[i]
    kb = 10
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    ninf = np.nan_to_num(atr, nan=np.inf)
    raw = np.where(mom < -1.2 * ninf, 1,
                   np.where(mom > 1.2 * ninf, -1, 0))
    ent = (hrs >= LO) & (hrs < HI)
    return dict(bts=bts, sdt=sdt, sig=np.where(ent, raw, 0), hrs=hrs)


def sim(days, strat, qmode, prm):
    """strat: OLD|BP; qmode: plain|gate|wait|gatewait|holdmod|widestop"""
    trades = []
    for d, day_ns, tsd, pxd, B, grid, qr, qmed in days:
        n = len(tsd)
        busy = 0
        bts, sdt, sig = B["bts"], B["sdt"], B["sig"]
        for i in np.flatnonzero(sig):
            t_sig = int(bts[i]); s = int(sig[i])
            if t_sig < busy:
                continue
            if strat == "BP" and sdt[i] > 8.0:
                continue
            gj = min(np.searchsorted(grid, t_sig), len(grid) - 1)
            frantic = qr[gj] > prm.get("g", 2.0) * qmed[gj]
            if qmode in ("gate", "gatewait") and frantic:
                continue
            t_arm = t_sig
            if qmode in ("wait", "gatewait"):
                g0 = np.searchsorted(grid, t_sig)
                g1 = np.searchsorted(grid, t_sig + CXL_NS)
                if g0 >= len(grid):
                    continue
                w = np.flatnonzero(qr[g0:g1] < 0.6 * qmed[g0:g1])
                if not len(w):
                    continue
                t_arm = int(grid[g0 + int(w[0])])
            j0 = np.searchsorted(tsd, t_arm + LAT, "left")
            if j0 >= n:
                break
            ref = pxd[max(j0 - 1, 0)] if t_arm > t_sig else None
            Lv = (ref if ref is not None else
                  pxd[max(np.searchsorted(tsd, t_sig, "left") - 1, 0)]) \
                - 1.0 * s
            j1 = np.searchsorted(tsd, t_sig + CXL_NS, "left")
            seg = pxd[j0:j1]
            th = np.flatnonzero(seg * s < (Lv - TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = j0 + int(th[0])
            hold_m = 15
            if qmode == "holdmod":
                gq = min(np.searchsorted(grid, tsd[fi]
                                         + 600_000_000_000),
                         len(grid) - 1)
                if qr[gq] < 0.8 * qmed[gq]:
                    hold_m = 25
            t_x = min(tsd[fi] + hold_m * 60_000_000_000,
                      day_ns + EOD_NS)
            xe = min(np.searchsorted(tsd, t_x, "left"), n - 1)
            if xe <= fi:
                continue
            dis = None
            if strat == "BP":
                dis = 60.0
                if qmode == "widestop" and frantic:
                    dis = 90.0
            fill = None; kx = xe
            # xaccel for BP: day-trend blowout during hold
            x_cut = None
            if strat == "BP":
                b0 = np.searchsorted(bts, tsd[fi], "left")
                b1 = np.searchsorted(bts, tsd[xe], "left")
                xb = b0 + np.flatnonzero(sdt[b0:b1] > 10.0)
                if len(xb):
                    x_cut = int(bts[xb[0]])
            if dis is not None:
                stop_lvl = Lv - dis * s
                seg2 = pxd[fi + 1:xe]
                if len(seg2):
                    sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                    if len(sh):
                        kx = fi + 1 + int(sh[0])
                        rw = min(pxd[kx], stop_lvl) if s > 0 \
                            else max(pxd[kx], stop_lvl)
                        fill = rw - TICK * s
            if x_cut is not None and (fill is None or tsd[kx] > x_cut):
                kx = min(np.searchsorted(tsd, x_cut, "left"), xe)
                fill = pxd[kx] - TICK * s
            if fill is None:
                fill = pxd[xe] - TICK * s
                kx = xe
            trades.append((int(tsd[kx]), (fill - Lv) * s * PT - FEES))
            busy = tsd[kx]
    return trades


def report(nm, trades, nwk, res):
    if len(trades) < 10:
        print(f"{nm:<34} n={len(trades)} (thin)", flush=True)
        return
    p = np.array([t[1] for t in trades])
    et = np.array([t[0] for t in trades])
    dy = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
        .resample("D").sum()
    dy = dy[dy != 0]
    clip = p.sum() - np.sort(p)[-3:].sum()
    print(f"{nm:<34} {len(p):>4} {len(p)/nwk:>5.1f} "
          f"{(p>0).mean()*100:>3.0f}% {p.mean():>+7.2f} "
          f"{p.sum():>+7.0f} {p.sum()/nwk:>+6.0f} {clip:>+7.0f} "
          f"{(dy>0).mean()*100:>4.0f}% {dy.min():>+7.0f}", flush=True)
    res[nm] = dict(n=len(p), usd_wk=round(p.sum()/nwk),
                   wr=round((p>0).mean()*100), clip3=round(clip),
                   posd=round((dy>0).mean()*100), wd=round(dy.min()))


def main():
    t0 = time.time()
    K.build_tape()
    ts_all, px_all = K.D["ts"], K.D["px"]
    days = []
    for f in sorted(glob.glob(f"{QDIR}/Q_MNQU6_*.parquet")):
        d = f.split("_")[-1][:8]
        if d < "20260627" or pd.Timestamp(d).dayofweek >= 5:
            continue
        day_ns = int(pd.Timestamp(d).value)
        tsd, pxd = tick_day(ts_all, px_all, day_ns)
        if len(tsd) < 100_000:
            continue
        qts, bid, ask, bs, asz = load_day(f)
        if len(qts) < 1_000_000:
            continue
        grid, j, mid, F = day_features(qts, bid, ask, bs, asz)
        k1 = np.searchsorted(qts, grid - 1_000_000_000, "right")
        j1_ = np.searchsorted(qts, grid, "right")
        qr1 = (j1_ - k1).astype(np.float64)
        qmed = pd.Series(qr1).rolling(2400, min_periods=600) \
            .median().to_numpy()
        qmed = np.where(np.nan_to_num(qmed) > 0, qmed, np.inf)
        B = day_bars(tsd, pxd)
        days.append((d, day_ns, tsd, pxd, B, grid, qr1, qmed))
        del qts, bid, ask, bs, asz, F
        print(f"  {d} ready ({time.time()-t0:.0f}s)", flush=True)
    nwk = len(days) / 5.0
    print(f"\nclean days: {len(days)}", flush=True)
    print(f"{'variant':<34} {'n':>4} {'/wk':>5} {'WR':>4} {'avg$':>7} "
          f"{'tot$':>7} {'$/wk':>6} {'clip3':>7} {'posD':>5} "
          f"{'wd':>7}", flush=True)
    res = {}
    for strat in ("OLD", "BP"):
        report(f"{strat} plain", sim(days, strat, "plain", {}), nwk, res)
        for g in (1.5, 2.0, 3.0):
            report(f"{strat} GATE g={g}",
                   sim(days, strat, "gate", {"g": g}), nwk, res)
        report(f"{strat} CALM-WAIT",
               sim(days, strat, "wait", {}), nwk, res)
        for g in (2.0, 3.0):
            report(f"{strat} GATE+WAIT g={g}",
                   sim(days, strat, "gatewait", {"g": g}), nwk, res)
    report("BP HOLDMOD 15->25 calm",
           sim(days, "BP", "holdmod", {}), nwk, res)
    report("BP WIDESTOP 60->90 frantic",
           sim(days, "BP", "widestop", {}), nwk, res)
    with open("research/round70_results.json", "w") as fo:
        json.dump(res, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
