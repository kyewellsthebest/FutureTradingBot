"""Round 69: QUOTES INSIDE THE STRATEGY (user's framing: signal from
price as normal, quotes as validation/timing/execution - not a
standalone quote trigger, not just a static filter). Untested uses:

  B. CALM-WAIT entry: BP-Final signal fires as normal, but instead
     of resting the limit immediately, wait (within the same 180s
     window) until the book calms (1s quote-rate drops below K x its
     trailing 10-min median). Enter the same trade, later, when the
     panic is exhausting. B2 = the opposite (enter while frantic).
  C. PANIC-EXIT: normal entry; while in the trade, if quote-rate
     spikes above K2 x median, bail immediately instead of holding
     the full 15 minutes. (Book says vol incoming -> fade in danger.)
  D. STRESS-OFFSET: rest the passive limit DEEPER when the spread is
     stressed at signal (get paid more for providing liquidity into
     panic): off = 1.0 + clip(spread - 0.5, 0, 3).

All on clean post-roll overlap days (no roll artifacts), faithful
tick fills, $1.50/RT, dis 60, EOD 20:55. Baseline = deployed BP.
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, QDIR
from round66_qstrats import tick_day
import round54_clock as K

LAT = 65_000_000
FEES, PT, TICK = 1.50, 2.0, 0.25
DIS = 60.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO, HI = 14.0, 20.73
CXL_NS = 180_000_000_000
HOLD_NS = 15 * 60_000_000_000


def day_signals(tsd, pxd):
    """Deployed BP-Final signal engine on this day's ticks -> list of
    (bar_close_ts, side) obeying guard; busy handled by caller."""
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
    ent = (hrs >= LO) & (hrs < HI) & (sdt <= 8.0)
    raw = np.where(mom < -1.2 * ninf, 1,
                   np.where(mom > 1.2 * ninf, -1, 0))
    sig = np.where(ent, raw, 0)
    out = [(int(bts[i]), int(sig[i]), float(c[i]))
           for i in np.flatnonzero(sig)]
    return out, (bts, sdt)


def run_arm(days, arm, prm):
    trades = []
    for d, day_ns, tsd, pxd, sigs, bar_sdt, grid, qr, qmed, spd in days:
        n = len(tsd)
        busy = 0
        bts_a, sdt_a = bar_sdt
        for t_sig, s, cbar in sigs:
            if t_sig < busy:
                continue
            t_arm = t_sig                       # when the limit rests
            if arm in ("B", "B2"):
                g0 = np.searchsorted(grid, t_sig)
                g1 = np.searchsorted(grid, t_sig + CXL_NS)
                if g0 >= len(grid):
                    continue
                seg = qr[g0:g1]; med = qmed[g0:g1]
                cond = seg < prm["k"] * med if arm == "B" \
                    else seg > prm["k"] * med
                w = np.flatnonzero(cond)
                if not len(w):
                    continue                    # never calmed: skip
                t_arm = int(grid[g0 + int(w[0])])
            off = 1.0
            if arm == "D":
                gj = min(np.searchsorted(grid, t_sig),
                         len(grid) - 1)
                off = 1.0 + min(max(spd[gj] - 0.5, 0.0), 3.0)
            j0 = np.searchsorted(tsd, t_arm + LAT, "left")
            if j0 >= n:
                break
            ref = pxd[max(j0 - 1, 0)] if arm in ("B", "B2") else cbar
            Lv = ref - off * s
            j1 = np.searchsorted(tsd, t_sig + CXL_NS, "left")
            seg2 = pxd[j0:j1]
            th = np.flatnonzero(seg2 * s < (Lv - TICK * s) * s + 1e-9)
            if not len(th):
                continue
            fi = j0 + int(th[0])
            t_x = min(tsd[fi] + HOLD_NS, day_ns + EOD_NS)
            xe = min(np.searchsorted(tsd, t_x, "left"), n - 1)
            if xe <= fi:
                continue
            # panic-exit cut time (arm C)
            t_cut = None
            if arm == "C":
                g0 = np.searchsorted(grid, tsd[fi])
                g1 = np.searchsorted(grid, tsd[xe])
                seg3 = qr[g0:g1]; med3 = qmed[g0:g1]
                w = np.flatnonzero(seg3 > prm["k2"] * med3)
                if len(w):
                    t_cut = int(grid[g0 + int(w[0])])
            fill = None; kx = xe
            stop_lvl = Lv - DIS * s
            seg4 = pxd[fi + 1:xe]
            if len(seg4):
                sh = np.flatnonzero(seg4 * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    kx = fi + 1 + int(sh[0])
                    rw = min(pxd[kx], stop_lvl) if s > 0 \
                        else max(pxd[kx], stop_lvl)
                    fill = rw - TICK * s
            if t_cut is not None and (fill is None or tsd[kx] > t_cut):
                kx = min(np.searchsorted(tsd, t_cut + LAT, "left"), xe)
                fill = pxd[kx] - TICK * s
            if fill is None:
                fill = pxd[xe] - TICK * s
                kx = xe
            trades.append((int(tsd[kx]),
                           (fill - Lv) * s * PT - FEES))
            busy = tsd[kx]
    return trades


def report(nm, trades, nwk):
    if len(trades) < 10:
        print(f"{nm:<30} n={len(trades)} (thin)", flush=True)
        return None
    p = np.array([t[1] for t in trades])
    et = np.array([t[0] for t in trades])
    dy = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
        .resample("D").sum()
    dy = dy[dy != 0]
    clip = p.sum() - np.sort(p)[-3:].sum()
    print(f"{nm:<30} {len(p):>4} {len(p)/nwk:>5.1f} "
          f"{(p>0).mean()*100:>3.0f}% {p.mean():>+7.2f} "
          f"{p.sum():>+7.0f} {p.sum()/nwk:>+6.0f} {clip:>+7.0f} "
          f"{(dy>0).mean()*100:>4.0f}% {dy.min():>+7.0f}", flush=True)
    return dict(n=len(p), usd_wk=round(p.sum()/nwk),
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
        qr1 = np.empty(len(grid))
        k1 = np.searchsorted(qts, grid - 1_000_000_000, "right")
        j1_ = np.searchsorted(qts, grid, "right")
        qr1 = (j1_ - k1).astype(np.float64)
        qmed = pd.Series(qr1).rolling(2400, min_periods=600) \
            .median().to_numpy()
        qmed = np.where(np.nan_to_num(qmed) > 0, qmed, np.inf)
        sigs, bar_sdt = day_signals(tsd, pxd)
        days.append((d, day_ns, tsd, pxd, sigs, bar_sdt,
                     grid, qr1, qmed, F["spread"]))
        del qts, bid, ask, bs, asz, F
        print(f"  {d} ready ({time.time()-t0:.0f}s)", flush=True)
    nwk = len(days) / 5.0
    print(f"\nclean days: {len(days)}", flush=True)
    print(f"{'arm':<30} {'n':>4} {'/wk':>5} {'WR':>4} {'avg$':>7} "
          f"{'tot$':>7} {'$/wk':>6} {'clip3':>7} {'posD':>5} "
          f"{'wd':>7}", flush=True)
    res = {}
    res["BASE"] = report("BASELINE BP (clean days)",
                         run_arm(days, "A", {}), nwk)
    for k in (0.6, 0.8, 1.0):
        res[f"B k{k}"] = report(f"B CALM-WAIT k={k}",
                                run_arm(days, "B", {"k": k}), nwk)
    for k in (2.0, 3.0):
        res[f"B2 k{k}"] = report(f"B2 FRANTIC-ONLY k={k}",
                                 run_arm(days, "B2", {"k": k}), nwk)
    for k2 in (3.0, 5.0, 8.0):
        res[f"C k{k2}"] = report(f"C PANIC-EXIT k2={k2}",
                                 run_arm(days, "C", {"k2": k2}), nwk)
    res["D"] = report("D STRESS-OFFSET",
                      run_arm(days, "D", {}), nwk)
    with open("research/round69_results.json", "w") as fo:
        json.dump(res, fo, indent=1)
    print(f"\nDONE ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
