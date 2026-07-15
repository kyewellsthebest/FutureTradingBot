"""Round 46: BULLETPROOF GA - the maximum-power search.

Objective (the user's exact ask): more consistent, more reliable, more
bulletproof to bad conditions - not just more $/wk.

New machinery never combined before:
  1. DUAL-TAPE fitness: every price-based genome is simmed on the 2026
     tape (52M ticks, sizes) AND on 2023-2024 history (part of the
     280M-tick 2.5y tape). 2025 is fully HELD OUT and only used to
     judge the finalists.
  2. REGIME FOLDS from round 45: weekly reversion coefficient labels
     each week. Fitness demands profit in strong-reversion history
     (mechanism present) and penalizes bleed in weak-reversion
     (trending = FADESZ-hostile) history. 2026 fitness = min over
     JanFeb/MarApr/May/JunJul folds, with penalties for pos-week%<80,
     worst week <-1200, worst day <-800.
  3. DEFENSIVE GENOME SPACE: guards {daytrend D, dayrange R, daystop C,
     loss-streak n, causal 3-day reversion gate}, sizes {flat, ladder,
     trend-capped ladder, fvol-capped ladder (2026-only)}, plus signal
     families {MOMR, dual-horizon MOMR2, z-score fade ZS, Keltner
     fade KELT}, passive/market entries, holds, disaster stops.

Protocol guards:
  - tick-walked fills, 65ms latency, 1 adverse tick each side on
    market fills, $1.50/RT.
  - genomes using flow (fvol cap) get a fitness handicap because they
    cannot be verified on history.
  - finalists (top 12 distinct) judged on held-out 2025 + $2.50/RT
    fee stress before anything is reported.
Results -> research/round46_results.json
"""
import hashlib, json, time
import numpy as np, pandas as pd
from multiprocessing import get_context

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
STOP_SLIP = 0.25
HN = lambda m: int(m * 60_000_000_000)
RNG = np.random.default_rng(46)
D26 = {}
DH = {}


# ---------------------------------------------------------------- data --
def bars_of(ts, px):
    m = ts // 60_000_000_000
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    idx = pd.to_datetime(m[st] * 60_000_000_000, utc=True)
    return dict(o=px[st], h=np.maximum.reduceat(px, st),
                l=np.minimum.reduceat(px, st), c=px[en - 1], idx=idx)


def build(ts, px, sz=None):
    D = {}
    D["ts"], D["px"] = ts, px
    b = bars_of(ts, px)
    idx = b["idx"]
    o, h, l, c = b["o"], b["h"], b["l"], b["c"]
    D["o"], D["c"] = o, c
    D["idx"] = idx
    D["bts"] = idx.asi8 + 60_000_000_000
    D["nb"] = len(c)
    hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0
    D["hrs"] = hrs
    D["days"] = idx.normalize().asi8
    D["rth"] = (hrs >= 14.0) & (hrs < 20.9)
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(h - l, np.abs(r1))
    atr = pd.Series(tr).rolling(20).mean().to_numpy()
    D["atr"] = atr
    D["moms"] = {k: np.concatenate(([0.0] * k, c[k:] - c[:-k]))
                 for k in (5, 8, 10, 12, 15, 20)}
    # z-score denominators (1-day rolling std of the k-min move)
    D["msd"] = {k: pd.Series(D["moms"][k]).rolling(390).std().to_numpy()
                for k in (10, 15, 20)}
    ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    D["kdev"] = c - ema20
    # day-open (first bar at/after 14:00 UTC each day) -> day-trend units
    df = pd.DataFrame({"c": c, "hrs": hrs}, index=idx)
    day = idx.normalize()
    rth_open = pd.Series(np.where(hrs >= 14.0, c, np.nan), index=idx) \
        .groupby(day).transform("first").to_numpy()
    dt = np.abs(c - rth_open) / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    D["dt"] = np.nan_to_num(dt)
    # cumulative day range in ATR units
    g = pd.DataFrame({"h": h, "l": l}, index=idx).groupby(day)
    drng = (g["h"].cummax() - g["l"].cummin()).to_numpy() \
        / np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    D["drng"] = np.nan_to_num(drng)
    # causal 3-day reversion gauge: mom10 known 15 bars ago vs the
    # realized 15-bar return since - trailing 1170-bar correlation
    x = np.roll(D["moms"][10], 15); x[:15] = 0
    y = c - np.roll(c, 15); y[:15] = 0
    D["rev3d"] = pd.Series(x).rolling(1170).corr(pd.Series(y)).to_numpy()
    if sz is not None:
        d_ = np.sign(np.diff(px, prepend=px[0]))
        m = ts // 60_000_000_000
        st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
        iv = np.add.reduceat(d_ * sz, st)
        fvol = pd.Series(np.abs(iv)).rolling(120).std().to_numpy()
        D["fvol_hi"] = fvol > np.nanquantile(fvol[D["rth"]], 0.9)
    else:
        D["fvol_hi"] = None
    # weekly reversion labels (round 45 fingerprint) for regime folds
    mom10 = pd.Series(D["moms"][10], index=idx)
    fwd15 = pd.Series(np.roll(c, -15) - c, index=idx); fwd15.iloc[-15:] = 0
    rmask = D["rth"]
    wkrev = {}
    sub = pd.DataFrame({"m": mom10[rmask], "f": fwd15[rmask]})
    for w, gg in sub.groupby(pd.Grouper(freq="W")):
        if len(gg) > 800:
            wkrev[str(pd.Period(w.tz_localize(None), freq="W"))] = \
                gg["m"].corr(gg["f"])
    D["wkrev"] = pd.Series(wkrev)
    return D


# ----------------------------------------------------------------- sim --
def sim(gn, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr, hrs = D["c"], D["atr"], D["hrs"]
    bts, nb, days = D["bts"], D["nb"], D["days"]
    ninf = np.nan_to_num(atr, nan=np.inf)
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    st = gn["sig"]
    if st[0] == "MOMR":
        k, a = st[1], st[2]
        mom = D["moms"][k]; thr = a * ninf
        raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
        mag = np.abs(mom) / pos_atr
    elif st[0] == "MOMR2":
        k1, a1, k2, a2 = st[1], st[2], st[3], st[4]
        m1, m2 = D["moms"][k1], D["moms"][k2]
        t1, t2 = a1 * ninf, a2 * ninf
        raw = np.where((m1 < -t1) & (m2 < -t2), 1,
                       np.where((m1 > t1) & (m2 > t2), -1, 0))
        mag = np.abs(m1) / pos_atr
    elif st[0] == "ZS":
        k, z = st[1], st[2]
        sd = np.where(np.nan_to_num(D["msd"][k]) > 0, D["msd"][k], np.inf)
        zz = D["moms"][k] / sd
        raw = np.where(zz < -z, 1, np.where(zz > z, -1, 0))
        mag = np.abs(D["moms"][k]) / pos_atr
    else:  # KELT
        a = st[1]
        kd = D["kdev"]; thr = a * ninf
        raw = np.where(kd < -thr, 1, np.where(kd > thr, -1, 0))
        mag = np.abs(kd) / pos_atr
    sig = np.where(D["rth"], raw, 0)
    gd = gn["guard"]
    if gd is not None and gd[0] == "daytrend":
        sig = np.where(D["dt"] > gd[1], 0, sig)
    elif gd is not None and gd[0] == "dayrng":
        sig = np.where(D["drng"] > gd[1], 0, sig)
    elif gd is not None and gd[0] == "revgate":
        sig = np.where(np.nan_to_num(D["rev3d"]) > gd[1], 0, sig)
    sz_ = gn["size"]
    ladder = sz_[0] != "flat"
    fvcap = sz_[0] == "ladder_fvcap" and D["fvol_hi"] is not None
    tcap = sz_[0] == "ladder_tcap"
    passive = gn["entry"][0]
    hold, dis = gn["hold"], gn["dis"]
    sidx = np.flatnonzero(sig)
    out_t = []; out_p = []
    busy = 0; cur_day = -1; day_pnl = 0.0; streak = 0; pause_until = 0
    daystop = gd[1] if (gd is not None and gd[0] == "daystop") else None
    nstreak = gd[1] if (gd is not None and gd[0] == "streak") else None
    for i in sidx:
        if bts[i] < busy or bts[i] < pause_until:
            continue
        s = sig[i]
        if days[i] != cur_day:
            cur_day = days[i]; day_pnl = 0.0; streak = 0
        if daystop is not None and day_pnl <= -daystop:
            continue
        q = 1
        if ladder:
            l1, l2 = sz_[1], sz_[2]
            q = 3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1)
            if fvcap and D["fvol_hi"][i]:
                q = 1
            if tcap and D["dt"][i] > sz_[3]:
                q = 1
        if passive:
            off, cxl = gn["entry"][1], gn["entry"][2]
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(cxl * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                continue
            fi = a0 + th_[0]
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + TICK * s
        xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, "left")
        if xe >= n: break
        fill = None; k_exit = xe
        if dis is not None:
            stop_lvl = entry - dis * s
            seg2 = px[fi + 1:xe]
            if len(seg2):
                sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
                if len(sh):
                    k_exit = fi + 1 + int(sh[0])
                    raw_ = min(px[k_exit], stop_lvl) if s > 0 \
                        else max(px[k_exit], stop_lvl)
                    fill = raw_ - STOP_SLIP * s
        if fill is None:
            fill = px[xe] - TICK * s
            k_exit = xe
        pnl = ((fill - entry) * s * PT - FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl
        busy = ts[k_exit]
        if nstreak is not None:
            streak = streak + 1 if pnl < 0 else 0
            if streak >= nstreak:
                pause_until = ts[k_exit] + HN(30)
                streak = 0
    return pd.Series(out_p,
                     index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                          utc=True))


# ------------------------------------------------------------- fitness --
F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]


def wk_of(s):
    wk = s.resample("W").sum()
    return wk[wk != 0]


def pool_usd_wk(s, weeks):
    if not len(s):
        return 0.0
    lab = s.index.to_period("W").astype(str)
    s2 = s[np.isin(lab, list(weeks))]
    wk = wk_of(s2)
    return float(s2.sum() / max(len(wk), 1)) if len(s2) else 0.0


def eval_genome(gn):
    s26 = sim(gn, D26)
    if len(s26) < 300:
        return (-9999.0,) + (0,) * 9
    folds = []
    for lo, hi in F26:
        f = s26[(s26.index >= pd.Timestamp(lo, tz="UTC"))
                & (s26.index < pd.Timestamp(hi, tz="UTC"))]
        wk = wk_of(f)
        folds.append(float(f.sum() / max(len(wk), 1)) if len(f) else -999.0)
    wk26 = wk_of(s26)
    dy26 = s26.resample("D").sum(); dy26 = dy26[dy26 != 0]
    pos26 = (wk26 > 0).mean() * 100
    ww26, wd26 = float(wk26.min()), float(dy26.min())
    trwk = len(s26) / max(len(wk26), 1)
    if trwk < 40:
        return (-9999.0,) + (0,) * 9
    m26 = min(folds)
    pen = (15.0 * max(0.0, 80.0 - pos26)
           + 0.30 * max(0.0, -ww26 - 1200)
           + 0.15 * max(0.0, -wd26 - 800))
    uses_flow = gn["size"][0] == "ladder_fvcap"
    strongH = weakH = 0.0
    if not uses_flow:
        sH = sim(gn, DH)
        sH = sH[sH.index < pd.Timestamp("2025-01-01", tz="UTC")]
        strongH = pool_usd_wk(sH, STRONG_2324)
        weakH = pool_usd_wk(sH, WEAK_2324)
        if strongH <= 0:
            fit = -5000.0 + strongH
        else:
            fit = m26 - pen - 0.5 * max(0.0, -weakH)
    else:
        fit = m26 - pen - 300.0
    return (round(fit, 1), round(m26), round(float(s26.sum() / max(len(wk26), 1))),
            round(pos26), round(ww26), round(wd26), round(trwk, 1),
            round(strongH), round(weakH), len(s26))


# ------------------------------------------------------------- genomes --
def pick(lst):
    return lst[int(RNG.integers(len(lst)))]


def rand_genome():
    fam = pick(["MOMR", "MOMR", "MOMR", "MOMR2", "ZS", "KELT"])
    if fam == "MOMR":
        sig = (fam, pick([5, 8, 10, 12, 15, 20]),
               pick([1.0, 1.2, 1.5, 2.0]))
    elif fam == "MOMR2":
        sig = (fam, pick([5, 8, 10]), pick([0.8, 1.0, 1.2]),
               pick([15, 20]), pick([0.8, 1.0, 1.2]))
    elif fam == "ZS":
        sig = (fam, pick([10, 15, 20]), pick([2.0, 2.5, 3.0]))
    else:
        sig = (fam, pick([1.5, 2.0, 2.5]))
    guard = pick([None, None,
                  ("daytrend", pick([4.0, 6.0, 8.0, 10.0])),
                  ("dayrng", pick([6.0, 8.0, 10.0])),
                  ("daystop", pick([350.0, 500.0, 700.0])),
                  ("streak", pick([3, 4, 5])),
                  ("revgate", pick([0.0, 0.05]))])
    size = pick([("flat",),
                 ("ladder", pick([1.5, 2.0]), pick([3.0, 4.0])),
                 ("ladder", pick([1.5, 2.0]), pick([3.0, 4.0])),
                 ("ladder_tcap", pick([1.5, 2.0]), pick([3.0, 4.0]),
                  pick([4.0, 6.0, 8.0])),
                 ("ladder_fvcap", pick([1.5, 2.0]), pick([3.0, 4.0]))])
    entry = (True, pick([0.5, 1.0, 1.5]), pick([60, 180, 300])) \
        if RNG.random() < 0.75 else (False,)
    return {"sig": sig, "guard": guard, "size": size, "entry": entry,
            "hold": pick([10, 15, 20, 25]),
            "dis": pick([None, None, 60.0, 100.0])}


def mutate(gn):
    g2 = dict(gn)
    key = pick(["sig", "guard", "size", "entry", "hold", "dis"])
    g2[key] = rand_genome()[key]
    return g2


def crossover(a, b):
    return {k: (a[k] if RNG.random() < 0.5 else b[k]) for k in a}


def gkey(gn):
    return hashlib.md5(json.dumps(gn, sort_keys=True,
                                  default=str).encode()).hexdigest()


# ---------------------------------------------------------------- main --
STRONG_2324 = set()
WEAK_2324 = set()


def init_globals():
    global STRONG_2324, WEAK_2324
    t0 = time.time()
    import pyarrow.parquet as pq
    z = np.load("data/tick/ytd2026sz.npz")
    D26.update(build(z["ts"], z["px"], sz=z["sz"]))
    print(f"2026 tape built: {D26['nb']:,} bars ({time.time()-t0:.0f}s)",
          flush=True)
    tb = pq.read_table("data/tick/nq_ticks_2p5y.parquet",
                       columns=["ts", "price"])
    hts = tb["ts"].to_numpy(); hpx = tb["price"].to_numpy()
    del tb
    # trim history to < 2026 (2026 lives on the sized tape)
    cut = np.searchsorted(hts, pd.Timestamp("2026-01-01", tz="UTC").value)
    DH.update(build(hts[:cut], hpx[:cut]))
    print(f"history tape built: {DH['nb']:,} bars ({time.time()-t0:.0f}s)",
          flush=True)
    wr = DH["wkrev"]
    wr2324 = wr[[w for w in wr.index if w < "2025-01-01"]]
    q1, q3 = wr2324.quantile(0.25), wr2324.quantile(0.75)
    STRONG_2324 = set(wr2324[wr2324 <= q1].index)
    WEAK_2324 = set(wr2324[wr2324 >= q3].index)
    print(f"regime folds: strong23-24 {len(STRONG_2324)} wks, "
          f"weak23-24 {len(WEAK_2324)} wks", flush=True)


def main():
    t0 = time.time()
    init_globals()
    champion = {"sig": ("MOMR", 10, 1.2), "guard": None,
                "size": ("ladder", 2.0, 3.0),
                "entry": (True, 1.0, 180), "hold": 15, "dis": None}
    seeds = [champion,
             {**champion, "guard": ("daytrend", 6.0)},
             {**champion, "guard": ("daytrend", 8.0)},
             {**champion, "guard": ("dayrng", 8.0)},
             {**champion, "guard": ("daystop", 500.0)},
             {**champion, "guard": ("streak", 4)},
             {**champion, "guard": ("revgate", 0.0)},
             {**champion, "size": ("ladder_tcap", 2.0, 3.0, 6.0)},
             {**champion, "size": ("ladder_fvcap", 2.0, 3.0)},
             {**champion, "dis": 100.0}]
    pop = seeds + [rand_genome() for _ in range(200 - len(seeds))]
    cache = {}; genomes = {}
    ctx = get_context("fork")
    pool = ctx.Pool(4)
    for gen in range(40):
        todo = [g for g in pop if gkey(g) not in cache]
        for g, res in zip(todo, pool.map(eval_genome, todo)):
            cache[gkey(g)] = res; genomes[gkey(g)] = g
        scored = sorted(pop, key=lambda g: -cache[gkey(g)][0])
        fb = cache[gkey(scored[0])]
        print(f"gen {gen:02d}: fit {fb[0]:8.1f} m26 ${fb[1]:5.0f} "
              f"all ${fb[2]:5.0f} pos {fb[3]:3.0f}% ww ${fb[4]:6.0f} "
              f"wd ${fb[5]:6.0f} {fb[6]:5.1f}tr/wk sH ${fb[7]:5.0f} "
              f"wH ${fb[8]:6.0f} | {json.dumps(scored[0], default=str)[:110]}"
              f" ({time.time()-t0:.0f}s)", flush=True)
        elite = scored[:25]
        children = []
        while len(children) < 145:
            a_, b_ = RNG.choice(25, 2, replace=False)
            ch = crossover(elite[a_], elite[b_])
            if RNG.random() < 0.6:
                ch = mutate(ch)
            children.append(ch)
        pop = elite + children + [rand_genome() for _ in range(30)]
    pool.close(); pool.join()

    # ---- finalists: top 12 distinct -> held-out 2025 + fee stress ------
    lb = sorted(cache.items(), key=lambda kv: -kv[1][0])
    print(f"\n=== FINALISTS (of {len(cache)} evaluated) -> "
          f"HELD-OUT 2025 JUDGMENT ===", flush=True)
    champ_fit = cache[gkey(champion)]
    print(f"champion baseline: {champ_fit}")
    wr = DH["wkrev"]
    wr25 = wr[[w for w in wr.index if w >= "2025-01-01"]]
    q1, q3 = wr25.quantile(0.25), wr25.quantile(0.75)
    strong25 = set(wr25[wr25 <= q1].index)
    weak25 = set(wr25[wr25 >= q3].index)
    results = []
    seen_fit = set()
    for k_, v_ in lb:
        if len(results) >= 12 or v_[0] < -4000:
            break
        if (v_[0], v_[2], v_[6]) in seen_fit:   # skip exact clones
            continue
        seen_fit.add((v_[0], v_[2], v_[6]))
        gn = genomes[k_]
        row = {"genome": gn, "fit26": v_}
        if gn["size"][0] != "ladder_fvcap":
            sH = sim(gn, DH)
            s25 = sH[sH.index >= pd.Timestamp("2025-01-01", tz="UTC")]
            wk25 = wk_of(s25)
            row["h25_usd_wk"] = round(float(s25.sum() / max(len(wk25), 1)))
            row["h25_pos"] = round((wk25 > 0).mean() * 100) if len(wk25) else 0
            row["h25_strong"] = round(pool_usd_wk(s25, strong25))
            row["h25_weak"] = round(pool_usd_wk(s25, weak25))
        # fee stress on 2026: full re-sim at $2.50/RT
        global FEES
        FEES = 2.50
        s26s = sim(gn, D26)
        FEES = 1.50
        wk26s = wk_of(s26s)
        row["fee250_usd_wk"] = round(float(s26s.sum() / max(len(wk26s), 1)))
        results.append(row)
        print(json.dumps(row, default=str), flush=True)
    with open("research/round46_results.json", "w") as f:
        json.dump({"champion_baseline": champ_fit, "finalists": results,
                   "evals": len(cache)}, f, default=str, indent=1)
    print(f"\nDONE {len(cache)} genomes ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
