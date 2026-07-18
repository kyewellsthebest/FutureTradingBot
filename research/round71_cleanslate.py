"""Round 71: CLEAN SLATE. User mandate: completely NEW strategy
families (not the deployed fade with layers), searched on the
ticks+quotes overlap, dream-spec always in scope, and firm-tier
finds REPORTED (at $0.22/RT firm costs) even if undeployable.

Families (all new to this project):
  A RETRACE   - the user's original strategy rebuilt on tick data:
                trend leg -> passive limit at r% retrace -> bracket
                (target T / stop S pts) -> timer/EOD. High freq.
  C SWEEP     - single-tick price jump >= J pts -> fade it, bracket.
                Arm x2: only when spread stressed (vacuum) / always.
  D COMPRESS  - 15-bar range compression -> breakout entry with
                trend, bracket. Arm x2: book-fueled (qrate spike at
                break) / plain.
  E VWAP      - session VWAP from tick sizes; fade |dev| >= k ATR
                back toward VWAP, passive entry, exit at VWAP touch
                or timer. Arm x2: calm-book gate / always.
  B BOOKSCALP - firm-tier: 1-tick spread + one-sided depth -> join
                the heavy side, +/-2 tick scratch bracket. Reported
                at BOTH $1.50 (us) and $0.22 (firm) costs.

Fees $1.50/RT retail baseline; every config also evaluated at
$0.22/RT (firm tier). Dream detector on everything:
tr/wk >= 150, 45 <= WR <= 55, realized ratio >= 1.5, positive $/wk.
"""
import glob, json, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, "research")
from round65_qfactory import load_day, day_features, QDIR
from round66_qstrats import tick_day
import round54_clock as K

LAT = 65_000_000
PT, TICK = 2.0, 0.25
EOD_NS = (20 * 60 + 55) * 60_000_000_000
LO, HI = 14.0, 20.73
WTDIR = "/tmp/claude-0/weekticks"


def day_ctx(d, day_ns, tsd, pxd):
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
    # VWAP from the raw week file (has sizes)
    vwap_b = np.full(len(c), np.nan)
    fp = f"{WTDIR}/MNQU6_{d}.parquet"
    if glob.glob(fp):
        t = pd.read_parquet(fp, columns=["ts", "price", "size"])
        qts_ = t["ts"].to_numpy(np.int64)
        p_ = pd.to_numeric(t["price"], errors="coerce") \
            .to_numpy(np.float64)
        z_ = t["size"].to_numpy(np.float64)
        o = np.argsort(qts_, kind="stable")
        qts_, p_, z_ = qts_[o], p_[o], z_[o]
        s0 = np.searchsorted(qts_, day_ns + int(14.0 * 3600e9))
        cpv = np.concatenate(([0.0], np.cumsum(p_[s0:] * z_[s0:])))
        cv = np.concatenate(([0.0], np.cumsum(z_[s0:])))
        ei = np.searchsorted(qts_[s0:], bts, "left")
        with np.errstate(invalid="ignore", divide="ignore"):
            vw = cpv[ei] / np.maximum(cv[ei], 1.0)
        vwap_b = np.where(cv[ei] > 100, vw, np.nan)
    return dict(c=c, h=h, l=l, bts=bts, hrs=hrs, atr=atr, vwap=vwap_b)


def bracket(tsd, pxd, fi, entry, s, tgt, stop, t_max, n):
    xe = min(np.searchsorted(tsd, t_max, "left"), n - 1)
    if xe <= fi:
        return None, fi
    tl, sl = entry + tgt * s, entry - stop * s
    seg = pxd[fi + 1:xe]
    if not len(seg):
        return pxd[xe] - TICK * s, xe
    ht = np.flatnonzero(seg * s > (tl + TICK * s) * s - 1e-9)
    hs = np.flatnonzero(seg * s <= sl * s + 1e-9)
    it = ht[0] if len(ht) else 10**9
    is_ = hs[0] if len(hs) else 10**9
    if it < is_:
        return tl, fi + 1 + int(it)
    if is_ < it:
        k = fi + 1 + int(is_)
        rw = min(pxd[k], sl) if s > 0 else max(pxd[k], sl)
        return rw - TICK * s, k
    return pxd[xe] - TICK * s, xe


def run_family(days, fam, g):
    out_t, out_p = [], []
    for (d, day_ns, tsd, pxd, C, grid, qr, qmed, spd, imb) in days:
        n = len(tsd)
        busy = 0
        c, atr, hrs, bts = C["c"], C["atr"], C["hrs"], C["bts"]
        ok = (hrs >= LO) & (hrs < HI)
        if fam == "A":
            Lb = g["L"]
            leg = c - np.roll(c, Lb); leg[:Lb] = 0
            ninf = np.nan_to_num(atr, nan=np.inf)
            sig = np.where(ok & (np.abs(leg) >= g["m"] * ninf),
                           np.sign(leg), 0)
        elif fam == "D":
            rr = pd.Series(C["h"]).rolling(15).max().to_numpy() \
                - pd.Series(C["l"]).rolling(15).min().to_numpy()
            ninf = np.nan_to_num(atr, nan=np.inf)
            comp = rr <= 3.0 * ninf
            prev = np.roll(comp, 1); prev[0] = False
            hi15 = np.roll(pd.Series(C["h"]).rolling(15).max()
                           .to_numpy(), 1)
            lo15 = np.roll(pd.Series(C["l"]).rolling(15).min()
                           .to_numpy(), 1)
            sig = np.where(ok & prev & (c > hi15 + TICK), 1,
                           np.where(ok & prev & (c < lo15 - TICK),
                                    -1, 0))
        elif fam == "E":
            dev = (c - C["vwap"]) / np.where(
                np.nan_to_num(atr) > 0, atr, np.inf)
            dev = np.nan_to_num(dev)
            sig = np.where(ok & (np.abs(dev) >= g["k"]),
                           -np.sign(dev), 0)
        else:
            sig = None
        if fam in ("A", "D", "E"):
            for i in np.flatnonzero(sig):
                t_sig = int(bts[i]); s = int(sig[i])
                if t_sig < busy:
                    continue
                gj = min(np.searchsorted(grid, t_sig), len(grid) - 1)
                if fam == "D" and g.get("fuel") and \
                        qr[gj] < 1.5 * qmed[gj]:
                    continue
                if fam == "E" and g.get("calm") and \
                        qr[gj] > 2.0 * qmed[gj]:
                    continue
                if fam == "A":
                    ref = c[i]
                    Lv = ref - g["r"] * (c[i] - c[i - g["L"]])
                    j0 = np.searchsorted(tsd, t_sig + LAT, "left")
                    j1 = np.searchsorted(tsd,
                                         t_sig + 300_000_000_000,
                                         "left")
                    if j0 >= n:
                        break
                    seg = pxd[j0:j1]
                    th = np.flatnonzero(
                        seg * s < (Lv - TICK * s) * s + 1e-9)
                    if not len(th):
                        continue
                    fi = j0 + int(th[0])
                    entry = Lv
                elif fam == "E":
                    j0 = np.searchsorted(tsd, t_sig + LAT, "left")
                    j1 = np.searchsorted(tsd,
                                         t_sig + 180_000_000_000,
                                         "left")
                    if j0 >= n:
                        break
                    Lv = pxd[max(j0 - 1, 0)] - 1.0 * s
                    seg = pxd[j0:j1]
                    th = np.flatnonzero(
                        seg * s < (Lv - TICK * s) * s + 1e-9)
                    if not len(th):
                        continue
                    fi = j0 + int(th[0])
                    entry = Lv
                else:
                    fi = np.searchsorted(tsd, t_sig + LAT, "left")
                    if fi >= n:
                        break
                    entry = pxd[fi] + TICK * s
                t_max = min(tsd[fi] + g["tmax"] * 60_000_000_000,
                            day_ns + EOD_NS)
                if fam == "E" and not g.get("half"):
                    vw = C["vwap"][i]
                    tgt = abs(entry - vw) if np.isfinite(vw) else \
                        g["tgt"]
                    tgt = max(min(tgt, 60.0), 2.0)
                else:
                    tgt = g["tgt"]
                fill, k = bracket(tsd, pxd, fi, entry, s, tgt,
                                  g["stop"], t_max, n)
                if fill is None:
                    continue
                out_p.append((fill - entry) * s * PT)
                out_t.append(int(tsd[k]))
                busy = tsd[k]
        elif fam == "C":
            dj = np.diff(pxd)
            ev = np.flatnonzero(np.abs(dj) >= g["J"])
            for e in ev:
                t_e = int(tsd[e + 1])
                if t_e < busy:
                    continue
                hr = (t_e % 86_400_000_000_000) / 3600e9
                if not (LO <= hr < HI):
                    continue
                s = -int(np.sign(dj[e]))
                gj = min(np.searchsorted(grid, t_e), len(grid) - 1)
                if g.get("vac") and spd[gj] <= 0.5:
                    continue
                fi = np.searchsorted(tsd, t_e + LAT, "left")
                if fi >= n:
                    break
                entry = pxd[fi] + TICK * s
                t_max = min(tsd[fi] + g["tmax"] * 60_000_000_000,
                            day_ns + EOD_NS)
                fill, k = bracket(tsd, pxd, fi, entry, s, g["tgt"],
                                  g["stop"], t_max, n)
                if fill is None:
                    continue
                out_p.append((fill - entry) * s * PT)
                out_t.append(int(tsd[k]))
                busy = tsd[k]
        elif fam == "B":
            step = max(1, int(g.get("step", 4)))
            for gi in range(0, len(grid), step):
                t_e = int(grid[gi])
                if t_e < busy:
                    continue
                hr = (t_e % 86_400_000_000_000) / 3600e9
                if not (LO <= hr < HI):
                    continue
                if spd[gi] > 0.25 + 1e-9:
                    continue
                if abs(imb[gi] - 0.5) < g["ith"]:
                    continue
                s = 1 if imb[gi] > 0.5 else -1
                j0 = np.searchsorted(tsd, t_e + LAT, "left")
                if j0 >= n:
                    break
                Lv = pxd[max(j0 - 1, 0)] - TICK * s
                j1 = np.searchsorted(tsd, t_e + 30_000_000_000,
                                     "left")
                seg = pxd[j0:j1]
                th = np.flatnonzero(
                    seg * s < (Lv - TICK * s) * s + 1e-9)
                if not len(th):
                    continue
                fi = j0 + int(th[0])
                t_max = tsd[fi] + 60_000_000_000
                fill, k = bracket(tsd, pxd, fi, Lv, s, 0.5, 0.5,
                                  t_max, n)
                if fill is None:
                    continue
                out_p.append((fill - Lv) * s * PT)
                out_t.append(int(tsd[k]))
                busy = tsd[k]
    return np.array(out_p), np.array(out_t)


def metrics(gross, et, nwk, fee):
    p = gross - fee
    if len(p) < 15:
        return None
    dy = pd.Series(p, index=pd.to_datetime(et, utc=True)) \
        .resample("D").sum()
    dy = dy[dy != 0]
    wins = p[p > 0]
    ratio = (wins.mean() / abs(p[p < 0].mean())) \
        if (p < 0).any() and len(wins) else 0
    wr = (p > 0).mean() * 100
    clip = p.sum() - np.sort(p)[-3:].sum()
    m = dict(n=len(p), tr_wk=round(len(p) / nwk, 1),
             wr=round(wr, 1), ratio=round(ratio, 2),
             usd_wk=round(p.sum() / nwk),
             clip3=round(clip), posd=round((dy > 0).mean() * 100),
             wd=round(dy.min()))
    m["dream"] = (m["tr_wk"] >= 150 and 45 <= wr <= 55
                  and ratio >= 1.5 and m["usd_wk"] > 0)
    return m


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
        bi = bs[j]; ai = asz[j]
        imb_i = bi / np.maximum(bi + ai, 1.0)
        C = day_ctx(d, day_ns, tsd, pxd)
        days.append((d, day_ns, tsd, pxd, C, grid, qr1, qmed,
                     F["spread"], imb_i))
        del qts, bid, ask, bs, asz, F
        print(f"  {d} ready ({time.time()-t0:.0f}s)", flush=True)
    nwk = len(days) / 5.0
    print(f"\nclean days: {len(days)}", flush=True)
    GRIDS = []
    for m in (1.5, 2.5):
        for Lb in (5, 15):
            for r in (0.3, 0.5):
                for tgt, stop in ((12, 6), (8, 4), (6, 6), (15, 8)):
                    GRIDS.append(("A", dict(m=m, L=Lb, r=r, tgt=tgt,
                                            stop=stop, tmax=20)))
    for J in (3.0, 5.0, 8.0):
        for tgt, stop in ((6, 4), (10, 6), (15, 10)):
            for vac in (False, True):
                GRIDS.append(("C", dict(J=J, tgt=tgt, stop=stop,
                                        tmax=10, vac=vac)))
    for tgt, stop in ((15, 8), (25, 12), (40, 15)):
        for fuel in (False, True):
            GRIDS.append(("D", dict(tgt=tgt, stop=stop, tmax=30,
                                    fuel=fuel)))
    for k in (2.0, 3.0, 4.0):
        for calm in (False, True):
            GRIDS.append(("E", dict(k=k, stop=15.0, tgt=20.0,
                                    tmax=30, calm=calm)))
    for ith in (0.2, 0.3):
        GRIDS.append(("B", dict(ith=ith, step=4)))
    results = {}
    hdr = (f"{'config':<28} {'n':>5} {'tr/wk':>6} {'WR%':>5} "
           f"{'ratio':>5} {'$/wk@1.50':>10} {'$/wk@0.22':>10} "
           f"{'clip3':>7} {'posD%':>5}")
    print(hdr, flush=True)
    for fam, g in GRIDS:
        gross, et = run_family(days, fam, g)
        m1 = metrics(gross, et, nwk, 1.50)
        m2 = metrics(gross, et, nwk, 0.22)
        nm = f"{fam} " + " ".join(f"{k}{v}" for k, v in g.items()
                                  if k not in ("tmax", "step"))
        if m1 is None:
            continue
        flag = " DREAM!" if (m1["dream"] or (m2 and m2["dream"])) \
            else ""
        print(f"{nm:<28} {m1['n']:>5} {m1['tr_wk']:>6} "
              f"{m1['wr']:>5} {m1['ratio']:>5} "
              f"{m1['usd_wk']:>+10} "
              f"{(m2['usd_wk'] if m2 else 0):>+10} "
              f"{m1['clip3']:>+7} {m1['posd']:>5}{flag}", flush=True)
        results[nm] = dict(retail=m1, firm=m2)
    with open("research/round71_results.json", "w") as fo:
        json.dump(results, fo, indent=1)
    # summary buckets
    pos_r = [(nm, v) for nm, v in results.items()
             if v["retail"]["usd_wk"] > 0
             and v["retail"]["clip3"] > 0]
    pos_f = [(nm, v) for nm, v in results.items()
             if v["firm"] and v["firm"]["usd_wk"] > 0
             and v["retail"]["usd_wk"] <= 0]
    print(f"\nretail-viable (>$0/wk AND clip3>0): {len(pos_r)}")
    for nm, v in sorted(pos_r, key=lambda z: -z[1]['retail']
                        ['usd_wk'])[:10]:
        print(f"  {nm}: {v['retail']}")
    print(f"\nfirm-only (profitable at $0.22, not at $1.50): "
          f"{len(pos_f)}")
    for nm, v in sorted(pos_f, key=lambda z: -z[1]['firm']
                        ['usd_wk'])[:10]:
        print(f"  {nm}: firm {v['firm']}")
    print(f"\nDONE {len(GRIDS)} configs ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
