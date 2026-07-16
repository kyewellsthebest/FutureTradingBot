"""Round 54: SEARCH ENGINE UPGRADE + THE CLOCK DIMENSION.
User target: as close to $500/day as the tails allow. Breakthrough
avenue never touched in 53 rounds: the SIGNAL CLOCK. All prior rounds
computed the fade on 1-minute closes by convention. This round builds
30s and 15s bar clocks from ticks - same edge, detected and entered
up to 45s earlier, capturing more of the snap-back per trade.

Engine upgrades:
  - tape extended through Jul 15 (27 weeks) - includes the hostile
    week that executed HYBRID-X
  - the hostile week (Jul 7-15) is a HARD fitness constraint: any
    genome bleeding there is penalized to death
  - fitness = maximize $/wk subject to: min fold >= $400/wk,
    MDD >= -2200, pos weeks >= 75%, worst day >= -1400,
    hostile fold >= -$300 total
GA: pop 220, 40 gens, single-process (suspend-proof), checkpoints.
Finalists get the 2.5y history judgment post-hoc.
Fills: tick-walked, 65ms, 1 adverse tick market / trade-through
passive, $1.50/RT, entries 14:00-20:44, flat 20:55.
"""
import glob, hashlib, json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R
from round48_drawdown import maxdd

RNG = np.random.default_rng(54)
ENTRY_LO, ENTRY_HI = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000
D = {}


def clock_bars(ts, px, sec):
    m = ts // (sec * 1_000_000_000)
    st = np.concatenate(([0], np.flatnonzero(np.diff(m)) + 1))
    en = np.concatenate((st[1:], [len(m)]))
    return dict(c=px[en - 1],
                h=np.maximum.reduceat(px, st),
                l=np.minimum.reduceat(px, st),
                bts=(m[st] + 1) * sec * 1_000_000_000)


def build_tape():
    t0 = time.time()
    z = np.load("data/tick/ytd2026sz.npz")
    ts0, px0 = z["ts"], z["px"]
    wf = []
    for f in sorted(glob.glob("/tmp/claude-0/weekticks/MNQU6_202607*.parquet")):
        day = f[-16:-8]
        if day < "20260707" or day >= "20260716":
            continue
        t = pd.read_parquet(f)
        wf.append((np.asarray(t["ts"].to_numpy(), dtype=np.int64),
                   np.asarray(t["price"].to_numpy(), dtype=np.float64)))
    wts = np.concatenate([a for a, _ in wf])
    wpx = np.concatenate([b for _, b in wf])
    o = np.argsort(wts, kind="stable")
    wts, wpx = wts[o], wpx[o]
    cut = np.searchsorted(wts, ts0[-1], "right")
    ts = np.concatenate([ts0, wts[cut:]])
    px = np.concatenate([px0, wpx[cut:]])
    dtx = pd.to_datetime(ts, utc=True)
    keep = np.asarray(dtx.dayofweek) < 5
    ts, px = ts[keep], px[keep]
    D["ts"], D["px"] = ts, px
    for sec in (60, 30, 15):
        cb = clock_bars(ts, px, sec)
        idx = pd.to_datetime(cb["bts"] - sec * 1_000_000_000, utc=True)
        hrs = np.asarray(idx.hour) + np.asarray(idx.minute) / 60.0 \
            + np.asarray(idx.second) / 3600.0
        c, h, l = cb["c"], cb["h"], cb["l"]
        r1 = c - np.roll(c, 1); r1[0] = 0
        tr = np.maximum(h - l, np.abs(r1))
        wtr = max(1, int(20 * 60 / sec))
        atr = pd.Series(tr).rolling(wtr).mean().to_numpy()
        day = idx.normalize()
        rth_open = pd.Series(np.where(hrs >= 14.0, c, np.nan), index=idx) \
            .groupby(day).transform("first")
        rth_open = pd.to_numeric(rth_open, errors="coerce").to_numpy()
        atr1m_eq = atr * np.sqrt(60.0 / sec)
        pos_a = np.where(np.nan_to_num(atr1m_eq) > 0, atr1m_eq, np.inf)
        sdt = np.nan_to_num((c - rth_open) / pos_a)
        moms = {}
        for km in (8, 10, 12):
            kb = int(km * 60 / sec)
            moms[km] = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
        D[sec] = dict(c=c, bts=cb["bts"], nb=len(c), hrs=hrs,
                      days=day.asi8, atr=atr, moms=moms, sdt=sdt)
    print(f"tape built: {len(ts):,} ticks, thru "
          f"{pd.to_datetime(ts[-1], utc=True)} ({time.time()-t0:.0f}s)",
          flush=True)


F26 = [("2026-01-01", "2026-03-01"), ("2026-03-01", "2026-05-01"),
       ("2026-05-01", "2026-06-01"), ("2026-06-01", "2026-07-07")]
HOSTILE = ("2026-07-07", "2026-07-16")


def sim54(g):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    C = D[g["clock"]]
    c, atr, hrs = C["c"], C["atr"], C["hrs"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    sdt = C["sdt"]
    sec = g["clock"]
    scale = np.sqrt(60.0 / sec)
    atr_eq = atr * scale
    ninf = np.nan_to_num(atr_eq, nan=np.inf)
    pos_a = np.where(np.nan_to_num(atr_eq) > 0, atr_eq, np.inf)
    mom = C["moms"][g["k"]]
    thr = g["a"] * ninf
    mag = np.abs(mom) / pos_a
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent & (np.abs(sdt) <= g["guard"]), raw, 0)
    l1, l2 = g["ladder"]
    passive = g["entry"][0]
    wb = g["wb"]; dcap = g["dcap"]; glday = g["glday"]
    dis = g["dis"]; xac = g["xaccel"]
    hold_ns = R.HN(g["hold"])
    sidx = np.flatnonzero(sig)
    out_t = []; out_p = []
    busy = 0
    cur_day = -1; day_pnl = 0.0
    cur_wk = -1; wk_pnl = 0.0
    for i in sidx:
        if bts[i] < busy:
            continue
        if days[i] != cur_day:
            cur_day = days[i]; day_pnl = 0.0
        wk_id = days[i] // 604_800_000_000_000
        if wk_id != cur_wk:
            cur_wk = wk_id; wk_pnl = 0.0
        s = int(sig[i])
        la, lb = l1, l2
        if glday is not None and day_pnl >= glday[0]:
            la -= glday[1]; lb -= 2 * glday[1]
        q = 3 if mag[i] >= lb else (2 if mag[i] >= la else 1)
        if dcap is not None and day_pnl <= -dcap:
            q = 1
        if g.get("dlock") is not None and day_pnl >= g["dlock"]:
            continue
        if g.get("dfloor") is not None and day_pnl <= -g["dfloor"]:
            continue
        if wb is not None and wk_pnl <= -wb:
            q = 1
        if passive:
            off, cxl = g["entry"][1], g["entry"][2]
            L = c[i] - off * s
            a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            a1 = np.searchsorted(ts, bts[i] + int(cxl * 1e9), "left")
            if a0 >= n: break
            seg = px[a0:a1]
            th_ = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
            if not len(th_):
                continue
            fi = a0 + th_[0]
            entry = L
        else:
            fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
            if fi >= n: break
            entry = px[fi] + R.TICK * s
        t_target = min(ts[fi] + hold_ns + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_target, "left")
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        xe = min(xe, day_last)
        if xe <= fi:
            continue
        if xac is not None:
            b0 = np.searchsorted(bts, ts[fi], "left")
            span = int(g["hold"] * 60 / sec)
            for j in range(b0 + 2, min(b0 + span, nb)):
                if abs(sdt[j]) > xac:
                    xe2 = np.searchsorted(ts, bts[j] + R.LAT_NS, "left")
                    if fi < xe2 < xe: xe = xe2
                    break
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
                    fill = raw_ - R.STOP_SLIP * s
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        pnl = ((fill - entry) * s * R.PT - R.FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl; wk_pnl += pnl
        busy = ts[k_exit]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def eval_genome(g):
    s = sim54(g)
    wk = R.wk_of(s)
    if len(s) < 200 or len(wk) < 24:
        return (-99999.0,) + (0,) * 7
    dy = s.resample("D").sum(); dy = dy[dy != 0]
    usd = float(s.sum() / len(wk))
    pos = (wk > 0).mean() * 100
    wd = float(dy.min())
    mdd = float(maxdd(dy))
    folds = []
    for lo, hi in F26:
        f = s[(s.index >= pd.Timestamp(lo, tz="UTC"))
              & (s.index < pd.Timestamp(hi, tz="UTC"))]
        w = R.wk_of(f)
        folds.append(float(f.sum() / max(len(w), 1)) if len(f) else -999.0)
    ho = s[(s.index >= pd.Timestamp(HOSTILE[0], tz="UTC"))
           & (s.index < pd.Timestamp(HOSTILE[1], tz="UTC"))]
    hostile = float(ho.sum())
    m4 = min(folds)
    pen = (3.0 * max(0.0, -300.0 - hostile)
           + 0.6 * max(0.0, -mdd - 2200.0)
           + 15.0 * max(0.0, 75.0 - pos)
           + 0.5 * max(0.0, -wd - 1400.0)
           + 1.0 * max(0.0, 400.0 - m4))
    fit = usd - pen
    return (round(fit, 1), round(usd), round(pos), round(wd), round(mdd),
            round(hostile), round(m4), round(len(s) / len(wk), 1))


def pick(lst):
    return lst[int(RNG.integers(len(lst)))]


def rand_genome():
    return {"clock": pick([60, 60, 30, 15]),
            "k": pick([8, 10, 12]),
            "a": pick([1.0, 1.2, 1.5]),
            "entry": pick([(False,), (True, 0.5, 60), (True, 1.0, 180)]),
            "guard": pick([6.0, 8.0, 10.0]),
            "xaccel": pick([None, 10.0]),
            "dis": pick([60.0, 80.0, 100.0]),
            "ladder": pick([(2.0, 4.0), (2.0, 3.0), (1.5, 4.0), (1.5, 3.0)]),
            "hold": pick([12, 15, 18]),
            "wb": pick([None, 500.0, 700.0, 1000.0]),
            "dcap": pick([None, 400.0]),
            "glday": pick([None, (300.0, 0.5)])}


def mutate(g):
    g2 = dict(g)
    key = pick(list(g2.keys()))
    g2[key] = rand_genome()[key]
    return g2


def crossover(a, b):
    return {k: (a[k] if RNG.random() < 0.5 else b[k]) for k in a}


def gkey(g):
    return hashlib.md5(json.dumps(g, sort_keys=True,
                                  default=str).encode()).hexdigest()


def main():
    t0 = time.time()
    build_tape()
    bp = {"clock": 60, "k": 10, "a": 1.2, "entry": (False,), "guard": 8.0,
          "xaccel": 10.0, "dis": 60.0, "ladder": (2.0, 4.0), "hold": 15,
          "wb": 700.0, "dcap": None, "glday": None}
    seeds = [bp,
             {**bp, "clock": 30}, {**bp, "clock": 15},
             {**bp, "entry": (True, 1.0, 180)},
             {**bp, "clock": 30, "entry": (True, 0.5, 60)}]
    pop = seeds + [rand_genome() for _ in range(220 - len(seeds))]
    cache = {}; genomes = {}
    for gen in range(40):
        todo = [g for g in pop if gkey(g) not in cache]
        for g in todo:
            cache[gkey(g)] = eval_genome(g); genomes[gkey(g)] = g
        if gen == 0:
            print(f"BP+wb 1m-clock benchmark: {cache[gkey(bp)]}", flush=True)
        scored = sorted(pop, key=lambda g: -cache[gkey(g)][0])
        fb = cache[gkey(scored[0])]
        print(f"gen {gen:02d}: fit {fb[0]:8.1f} ${fb[1]:5.0f}/wk "
              f"pos {fb[2]:3.0f}% wd {fb[3]:6.0f} MDD {fb[4]:6.0f} "
              f"hostile {fb[5]:6.0f} m4 {fb[6]:5.0f} {fb[7]:5.1f}tr/wk "
              f"| {json.dumps(scored[0], default=str)[:95]} "
              f"({time.time()-t0:.0f}s)", flush=True)
        elite = scored[:30]
        children = []
        while len(children) < 160:
            a_, b_ = RNG.choice(30, 2, replace=False)
            ch = crossover(elite[a_], elite[b_])
            if RNG.random() < 0.65:
                ch = mutate(ch)
            children.append(ch)
        pop = elite + children + [rand_genome() for _ in range(30)]
        ck = sorted(cache.items(), key=lambda kv: -kv[1][0])[:12]
        with open("research/round54_checkpoint.json", "w") as f:
            json.dump({"gen": gen, "evals": len(cache),
                       "top": [{"fit": v, "genome": genomes[k]}
                               for k, v in ck]}, f, default=str, indent=1)
    lb = sorted(cache.items(), key=lambda kv: -kv[1][0])
    print(f"\n=== TOP 12 of {len(cache)} ===")
    for k_, v_ in lb[:12]:
        print(f"  {v_} {json.dumps(genomes[k_], default=str)}", flush=True)
    with open("research/round54_results.json", "w") as f:
        json.dump({"top": [{"fit": v, "genome": genomes[k]}
                           for k, v in lb[:25]],
                   "evals": len(cache)}, f, default=str, indent=1)
    print(f"\nDONE {len(cache)} genomes ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
