"""Round 44: EVOLUTIONARY STRATEGY SYNTHESIS — the search-power upgrade.
Instead of testing hand-named strategies, BREED them:
  genome = { signal: one of {MOMR(k,a), FLOW(W,M), HYBRID(momr AND flow),
                             BWX(k), MOMF(k,a)},
             gate:   optional context gate {none, fvol_cap, fvol_skip,
                     hour window, atr regime},
             entry:  {market | passive(offset 0.5-2.0, cancel 60-300s)},
             hold:   8-30 min,
             ladder: thresholds (l1,l2) for 2x/3x or flat,
             dstop:  {none, -250..-500} }
Fitness = the most brutal criterion yet: min weekly-$ across THREE
disjoint sub-periods (Mar-Apr / May / Jun-Jul6) minus a worst-day
penalty — a candidate must work in every regime slice, not on average.
Population 150, 25 generations, tournament selection, tick-walked fills,
$1.50/RT. Benchmark: FADESZ+P (its genome is seeded into gen 0 — the
population must EARN the crown from it).
"""
import hashlib, json, os, time
import numpy as np, pandas as pd
from multiprocessing import Pool

PT = 2.0
FEES = 1.50
TICK = 0.25
LAT_NS = 65_000_000
HN = lambda m: int(m * 60_000_000_000)
PJ = pd.Timestamp("2026-01-01", tz="UTC")
P0 = pd.Timestamp("2026-03-01", tz="UTC")
P1 = pd.Timestamp("2026-05-01", tz="UTC")
P2 = pd.Timestamp("2026-06-01", tz="UTC")
P3 = pd.Timestamp("2026-07-07", tz="UTC")
RNG = np.random.default_rng(42)

G = {}  # globals per worker


def init_worker():
    z = np.load("data/tick/ytd2026sz.npz")
    ts, px, sz = z["ts"], z["px"], z["sz"]
    d = np.sign(np.diff(px, prepend=px[0]))
    m = (ts // 60_000_000_000) * 60_000_000_000
    g_ = pd.DataFrame({"m": m, "px": px, "iv": d * sz})
    b = g_.groupby("m").agg(open=("px", "first"), high=("px", "max"),
                            low=("px", "min"), close=("px", "last"),
                            iv=("iv", "sum"))
    b.index = pd.to_datetime(b.index, utc=True)
    G["ts"], G["px"] = ts, px
    G["o"], G["h"], G["l"], G["c"] = (b[k].to_numpy() for k in
                                      ("open", "high", "low", "close"))
    G["iv"] = b["iv"].to_numpy()
    G["idx"] = b.index
    G["bts"] = b.index.asi8 + 60_000_000_000
    G["nb"] = len(G["c"])
    hrs = np.asarray(b.index.hour) + np.asarray(b.index.minute) / 60.0
    G["hrs"] = hrs
    G["days"] = b.index.normalize().asi8
    G["rth"] = (hrs >= 14.0) & (hrs < 20.9)
    c = G["c"]
    r1 = c - np.roll(c, 1); r1[0] = 0
    tr = np.maximum(G["h"] - G["l"], np.abs(r1))
    G["atr"] = pd.Series(tr).rolling(20).mean().to_numpy()
    G["ias"] = pd.Series(np.abs(G["iv"])).rolling(30).mean().to_numpy()
    fvol = pd.Series(np.abs(G["iv"])).rolling(120).std().to_numpy()
    G["fvol_hi"] = fvol > np.nanquantile(fvol[G["rth"]], 0.9)
    G["moms"] = {k: np.concatenate(([0] * k, c[k:] - c[:-k]))
                 for k in (5, 8, 10, 12, 15, 20, 30)}
    G["flows"] = {W: pd.Series(G["iv"]).rolling(W).sum().to_numpy()
                  for W in (5, 10, 20)}
    cs = pd.Series(c)
    sd20 = cs.rolling(20).std().to_numpy()
    G["bw"] = 4 * sd20


def eval_genome(gn):
    ts, px = G["ts"], G["px"]
    n = len(ts)
    c, atr, hrs, rth = G["c"], G["atr"], G["hrs"], G["rth"]
    bts, nb, days = G["bts"], G["nb"], G["days"]
    # ---- signal ----
    st = gn["sig"]
    if st[0] == "MOMR" or st[0] == "MOMF":
        k, a = st[1], st[2]
        mom = G["moms"][k]
        thr = a * np.nan_to_num(atr, nan=np.inf)
        if st[0] == "MOMR":
            raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
        else:
            raw = np.where(mom > thr, 1, np.where(mom < -thr, -1, 0))
        mag = np.abs(mom) / np.where(np.nan_to_num(atr) > 0, atr, np.inf) / a
    elif st[0] == "FLOW":
        W, M = st[1], st[2]
        fl = G["flows"][W]
        thr = M * np.nan_to_num(G["ias"], nan=np.inf)
        raw = np.where(fl > thr, 1, np.where(fl < -thr, -1, 0))
        mag = np.abs(np.nan_to_num(fl)) / np.where(
            np.nan_to_num(G["ias"]) > 0, G["ias"], np.inf) / M
    elif st[0] == "HYBRID":
        k, a, W, M = st[1], st[2], st[3], st[4]
        mom = G["moms"][k]
        thr = a * np.nan_to_num(atr, nan=np.inf)
        fl = G["flows"][W]
        fthr = M * np.nan_to_num(G["ias"], nan=np.inf)
        fade = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
        conf = np.where(fl > fthr, 1, np.where(fl < -fthr, -1, 0))
        raw = np.where((fade != 0) & (conf == fade), fade, 0)
        mag = np.abs(mom) / np.where(np.nan_to_num(atr) > 0, atr, np.inf) / a
    else:  # BWX band-width expansion follow
        kk = st[1]
        bw = G["bw"]
        exp_ = bw > kk * np.roll(bw, 10)
        up = c > G["o"]
        raw = np.where(exp_ & up, 1, np.where(exp_ & ~up, -1, 0))
        mag = np.where(np.roll(bw, 10) > 0, bw / np.roll(bw, 10), 1) / kk
    sig = np.where(rth, raw, 0)
    # ---- gate ----
    gt = gn["gate"]
    if gt == "fvol_skip":
        sig = np.where(G["fvol_hi"], 0, sig)
    elif isinstance(gt, tuple) and gt[0] == "hour":
        sig = np.where((hrs >= gt[1]) & (hrs < gt[2]), sig, 0)
    elif gt == "atr_hi":
        sig = np.where(atr > np.nanmedian(atr[rth]), sig, 0)
    elif gt == "atr_lo":
        sig = np.where(atr <= np.nanmedian(atr[rth]), sig, 0)
    # ---- run ----
    hold = gn["hold"]
    l1, l2 = gn["ladder"]
    dstop = gn["dstop"]
    passive, off, cxl = gn["entry"]
    out_t = []; out_p = []
    busy = 0; i = 0; cur_day = -1; day_pnl = 0.0
    while i < nb - 2:
        s = sig[i]
        if s == 0 or bts[i] < busy:
            i += 1; continue
        if days[i] != cur_day:
            cur_day = days[i]; day_pnl = 0.0
        if dstop is not None and day_pnl <= dstop:
            i += 1; continue
        q = 1
        if l1 is not None:
            q = 3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1)
            if gn["gate"] == "fvol_cap" and G["fvol_hi"][i]:
                q = 1
        if passive:
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(cxl * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - TICK * s) * s + 1e-9)
            if not len(th_):
                i += 1; continue
            fi = a0 + th_[0]
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + TICK * s
        xe = np.searchsorted(ts, ts[fi] + HN(hold) + LAT_NS, "left")
        if xe >= n: break
        fill = px[xe] - TICK * s
        pnl = ((fill - entry) * s * PT - FEES) * q
        out_t.append(ts[xe]); out_p.append(pnl)
        day_pnl += pnl
        busy = ts[xe]
        i += 1
    if len(out_p) < 120:
        return (-9999.0, 0, 0, 0, 0, 0, 0)
    s_ = pd.Series(out_p, index=pd.to_datetime(np.array(out_t), utc=True))
    folds = []
    for lo, hi in ((PJ, P0), (P0, P1), (P1, P2), (P2, P3)):
        f = s_[(s_.index >= lo) & (s_.index < hi)]
        wk = f.resample("W").sum(); wk = wk[wk != 0]
        folds.append(f.sum() / max(len(wk), 1) if len(f) else -9999.0)
    dy = s_.resample("D").sum(); dy = dy[dy != 0]
    worst_day = dy.min() if len(dy) else 0.0
    wk_all = s_.resample("W").sum(); wk_all = wk_all[wk_all != 0]
    pos_pct = (wk_all > 0).mean() * 100 if len(wk_all) else 0.0
    worst_wk = wk_all.min() if len(wk_all) else 0.0
    fitness = (min(folds)
               - 0.15 * max(0.0, -worst_day - 800)
               - 15.0 * max(0.0, 75.0 - pos_pct)
               - 0.30 * max(0.0, -worst_wk - 1200))
    return (round(float(fitness), 1), round(float(min(folds)), 0),
            round(float(s_.sum() / max(len(wk_all), 1)), 0),
            round(float(worst_day), 0), round(len(s_) / max(len(wk_all), 1), 1),
            round(float(pos_pct)), round(float(worst_wk), 0))


def pick(lst):
    return lst[int(RNG.integers(len(lst)))]


def rand_genome():
    st = pick(["MOMR", "MOMR", "FLOW", "HYBRID", "MOMF", "BWX"])
    if st in ("MOMR", "MOMF"):
        sig = (st, pick([5, 8, 10, 12, 15, 20, 30]),
               pick([1.0, 1.2, 1.5, 2.0, 2.5]))
    elif st == "FLOW":
        sig = (st, pick([5, 10, 20]), pick([2.0, 3.0, 4.0, 6.0]))
    elif st == "HYBRID":
        sig = (st, pick([8, 10, 12]), pick([1.0, 1.2, 1.5]),
               pick([5, 10]), pick([1.0, 2.0, 3.0]))
    else:
        sig = (st, pick([1.3, 1.5, 1.8]))
    gate = pick([None, None, None, "fvol_cap", "fvol_skip",
                 "atr_hi", "atr_lo", ("hour", 14.0, 18.0),
                 ("hour", 16.0, 20.9)])
    entry = (bool(RNG.random() < 0.7),
             pick([0.5, 1.0, 1.5, 2.0]),
             pick([60, 120, 180, 300]))
    ladder = (None, None) if RNG.random() < 0.25 else \
        (pick([1.5, 2.0, 2.5]), pick([3.0, 4.0]))
    return {"sig": sig,
            "gate": gate,
            "entry": entry,
            "hold": pick([8, 10, 12, 15, 18, 22, 30]),
            "ladder": ladder,
            "dstop": None if RNG.random() < 0.6 else
                     pick([-250.0, -350.0, -500.0])}


def mutate(gn):
    g2 = json.loads(json.dumps(gn, default=list))
    g2 = {k: (tuple(v) if isinstance(v, list) else v) for k, v in g2.items()}
    fresh = rand_genome()
    key = pick(["sig", "gate", "entry", "hold", "ladder", "dstop"])
    g2[key] = fresh[key]
    return g2


def crossover(a, b):
    child = {}
    for k in a:
        child[k] = a[k] if RNG.random() < 0.5 else b[k]
    return child


def gkey(gn):
    return hashlib.md5(json.dumps(gn, sort_keys=True,
                                  default=str).encode()).hexdigest()


def main():
    t0 = time.time()
    champion = {"sig": ("MOMR", 10, 1.2), "gate": None,
                "entry": (True, 1.0, 180), "hold": 15,
                "ladder": (2.0, 3.0), "dstop": None}
    pop = [champion] + [rand_genome() for _ in range(149)]
    cache = {}
    genomes = {}
    pool = Pool(6, initializer=init_worker)
    hist = []
    for gen in range(40):
        todo = [g_ for g_ in pop if gkey(g_) not in cache]
        res = pool.map(eval_genome, todo)
        for g_, r_ in zip(todo, res):
            cache[gkey(g_)] = r_
            genomes[gkey(g_)] = g_
        scored = sorted(pop, key=lambda g_: -cache[gkey(g_)][0])
        best = scored[0]
        fb = cache[gkey(best)]
        hist.append((gen, fb))
        print(f"gen {gen:02d}: fit {fb[0]:8.1f} minfold ${fb[1]:6.0f}/wk "
              f"all ${fb[2]:6.0f}/wk wd ${fb[3]:6.0f} {fb[4]:5.1f}tr/wk "
              f"pos {fb[5]:3.0f}% ww ${fb[6]:6.0f} "
              f"| {json.dumps(best, default=str)[:120]} "
              f"({time.time()-t0:.0f}s)", flush=True)
        elite = scored[:20]
        children = []
        while len(children) < 110:
            a_, b_ = RNG.choice(20, 2, replace=False)
            ch = crossover(elite[a_], elite[b_])
            if RNG.random() < 0.6:
                ch = mutate(ch)
            children.append(ch)
        pop = elite + children + [rand_genome() for _ in range(20)]
    pool.close()
    # final leaderboard
    lb = sorted(cache.items(), key=lambda kv: -kv[1][0])[:15]
    print("\n=== FINAL LEADERBOARD (fitness = min sub-period $/wk - tail pen) ===")
    champ_fit = cache[gkey(champion)]
    print(f"FADESZ+P benchmark: {champ_fit}")
    for k_, v_ in lb:
        print(f"  fit={v_} genome={json.dumps(genomes[k_], default=str)}")
    with open("research/round44_evolve_results.json", "w") as f:
        json.dump({"benchmark": champ_fit,
                   "leaderboard": [{"fit": v_, "genome": genomes[k_]}
                                   for k_, v_ in lb],
                   "evals": len(cache)}, f, default=str, indent=1)
    print(f"\ntotal unique strategies evaluated: {len(cache)} "
          f"({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
