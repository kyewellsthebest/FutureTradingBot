"""Round 50: THE DELUSIONAL MEGA-GA. Target: strict dominance over
BP+brake — usd_wk > $702 AND max starting hole > -$1,876, with >=85%
positive weeks, on faithful session rules, history-validated.

Never-touched avenues in the genome:
  HYBRID SWITCH: fade core, but when the trend-day line trips, flip
    and RIDE the trend to EOD (1 lot) instead of going quiet. One
    regime variable, two states - regime-complete single strategy.
  PARTIAL EXIT: multi-lot fade trades bank 1 lot at +P points and
    ride the rest to the timer (half-cap never tested; full caps are
    proven fatal).
  Competing cores in one population: FADE / ORB / RIDE, each with the
    full governor gene pool (week brake, next-day, equity tiers, day
    soft-cap) and guard/exit-accel/ladder/hold genes.

All genomes are price-only -> every eval includes 2023-24 regime
folds (strong-rev must be >= 0 for fade cores; trending-week bleed
penalized). 2025 fully held out for the finalists.
Fills: market +1 adverse tick / passive trade-through, 65ms, $1.50/RT,
entries 14:00-20:44 UTC, flat by 20:55, stop trade-through +0.25 slip.
"""
import hashlib, json, sys, time
import numpy as np, pandas as pd
from multiprocessing import get_context
sys.path.insert(0, "research")
import round46_bulletproof_ga as R
import round47_frontier as F
from round48_drawdown import maxdd

RNG = np.random.default_rng(50)
ENTRY_LO, ENTRY_HI = 14.0, 20.73
EOD_NS = (20 * 60 + 55) * 60_000_000_000
CLOSE_NS = (21 * 60) * 60_000_000_000
STRONG_2324 = set()
WEAK_2324 = set()


def prep50(D):
    b = R.bars_of(D["ts"], D["px"])
    D["h"], D["l"] = b["h"], b["l"]
    idx = D["idx"]; hrs = D["hrs"]
    day = idx.normalize()
    inor = (hrs >= 14.0) & (hrs < 14.5)
    D["orh"] = pd.Series(np.where(inor, D["h"], np.nan), index=idx) \
        .groupby(day).transform("max").to_numpy()
    D["orl"] = pd.Series(np.where(inor, D["l"], np.nan), index=idx) \
        .groupby(day).transform("min").to_numpy()
    # first bar each day where |sdt| crosses a level (for RIDE/HYBRID)
    D["hybfirst"] = {}
    sdt = D["sdt"]
    for Dx in (4.0, 5.0, 6.0, 8.0):
        trig = (np.abs(sdt) > Dx) & (hrs >= 14.0) & (hrs < 19.5)
        s_ = pd.Series(trig, index=idx)
        first = s_.groupby(day).cumsum()
        D["hybfirst"][Dx] = (trig & (first.to_numpy() == 1))


def walk_exit(D, fi, xe, entry, s, dis):
    """Disaster-stop scan; returns (fill, k_exit, fired)."""
    ts, px = D["ts"], D["px"]
    if dis is not None:
        stop_lvl = entry - dis * s
        seg2 = px[fi + 1:xe]
        if len(seg2):
            sh = np.flatnonzero(seg2 * s <= stop_lvl * s + 1e-9)
            if len(sh):
                k = fi + 1 + int(sh[0])
                raw_ = min(px[k], stop_lvl) if s > 0 else max(px[k], stop_lvl)
                return raw_ - R.STOP_SLIP * s, k, True
    return None, xe, False


def sim50(g, D):
    ts, px = D["ts"], D["px"]
    n = len(ts)
    c, atr, hrs = D["c"], D["atr"], D["hrs"]
    bts, days, nb = D["bts"], D["days"], D["nb"]
    pos_atr = np.where(np.nan_to_num(atr) > 0, atr, np.inf)
    ninf = np.nan_to_num(atr, nan=np.inf)
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI)
    sdt = D["sdt"]
    core = g["core"]
    hyb = None
    if core[0] == "FADE":
        _, k, a = core
        mom = D["moms"][k]
        thr = a * ninf
        mag = np.abs(mom) / pos_atr
        raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
        sig = np.where(ent, raw, 0)
        gD = g["guard"]
        sig = np.where(np.abs(sdt) > gD, 0, sig)
        if g["hybrid"]:
            hyb = D["hybfirst"][gD] if gD in D["hybfirst"] else None
    elif core[0] == "ORB":
        _, rstop = core
        after = hrs >= 14.5
        sig = np.where(ent & after & (c > np.nan_to_num(D["orh"], nan=np.inf)), 1,
                       np.where(ent & after & (c < np.nan_to_num(D["orl"], nan=-np.inf)), -1, 0))
        mag = np.zeros(nb)
    else:  # RIDE
        _, Dx = core
        tr_ = D["hybfirst"].get(Dx)
        sig = np.where(tr_ & ent, np.sign(sdt).astype(int), 0) \
            if tr_ is not None else np.zeros(nb, dtype=int)
        mag = np.zeros(nb)
    idxs = np.flatnonzero(sig)
    if hyb is not None:
        idxs = np.union1d(idxs, np.flatnonzero(hyb & ent))
    out_t = []; out_p = []
    busy = 0
    cur_day = -1; day_pnl = 0.0; prev_day = 0.0
    cur_wk = -1; wk_pnl = 0.0
    equity = 0.0; eq_hi = 0.0
    last_special_day = -1
    l1, l2 = g["ladder"]
    wb = g["wb"]; nd = g["nd"]; eq_g = g["eqg"]; dcap = g["dcap"]
    pex = g["pex"]; xac = g["xaccel"]; dis = g["dis"]; hold = g["hold"]
    qbase = g.get("qty", 1)
    for i in idxs:
        if bts[i] < busy:
            continue
        if days[i] != cur_day:
            prev_day = day_pnl if cur_day != -1 else 0.0
            cur_day = days[i]; day_pnl = 0.0
        wk_id = days[i] // 604_800_000_000_000
        if wk_id != cur_wk:
            cur_wk = wk_id; wk_pnl = 0.0
        is_hyb = hyb is not None and hyb[i] and sig[i] == 0
        if core[0] in ("ORB", "RIDE") or is_hyb:
            if days[i] == last_special_day:
                continue
        s = int(np.sign(sdt[i])) if is_hyb else int(sig[i])
        if s == 0:
            continue
        if core[0] == "FADE" and not is_hyb:
            q = 3 if mag[i] >= l2 else (2 if mag[i] >= l1 else 1)
        else:
            q = 1 if is_hyb else qbase
        if dcap is not None and day_pnl <= -dcap:
            q = 1
        if nd is not None and prev_day <= -nd:
            q = 1
        if eq_g is not None:
            dd = eq_hi - equity
            if dd > eq_g[1]: q = 1
            elif dd > eq_g[0]: q = min(q, 2)
        if wb is not None and wk_pnl <= -wb:
            q = 1
        fi = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        if fi >= n: break
        entry = px[fi] + R.TICK * s
        if is_hyb or core[0] in ("ORB", "RIDE"):
            hold_eff = 600
            dis_eff = 100.0 if is_hyb else dis
        else:
            hold_eff = hold; dis_eff = dis
        t_target = min(ts[fi] + R.HN(hold_eff) + R.LAT_NS, days[i] + EOD_NS)
        xe = np.searchsorted(ts, t_target, "left")
        day_last = np.searchsorted(ts, days[i] + CLOSE_NS, "left") - 1
        xe = min(xe, day_last)
        if xe <= fi:
            continue
        if xac is not None and core[0] == "FADE" and not is_hyb:
            b0 = np.searchsorted(bts, ts[fi], "left")
            for j in range(b0 + 3, min(b0 + hold_eff, nb)):
                if abs(sdt[j]) > xac:
                    xe2 = np.searchsorted(ts, bts[j] + R.LAT_NS, "left")
                    if fi < xe2 < xe: xe = xe2
                    break
        fill, k_exit, fired = walk_exit(D, fi, xe, entry, s, dis_eff)
        if fill is None:
            fill = px[xe] - R.TICK * s
            k_exit = xe
        pnl = 0.0
        if (pex is not None and q >= 2 and core[0] == "FADE"
                and not is_hyb and not fired):
            tgt = entry + pex * s
            seg = px[fi + 1:k_exit]
            hit = np.flatnonzero(seg * s > (tgt + R.TICK * s) * s - 1e-9) \
                if len(seg) else []
            if len(hit):
                pnl += (tgt - entry) * s * R.PT - R.FEES
                q -= 1
        pnl += ((fill - entry) * s * R.PT - R.FEES) * q
        out_t.append(ts[k_exit]); out_p.append(pnl)
        day_pnl += pnl; wk_pnl += pnl
        equity += pnl; eq_hi = max(eq_hi, equity)
        busy = ts[k_exit]
        if is_hyb or core[0] in ("ORB", "RIDE"):
            last_special_day = days[i]
    s_ = pd.Series(out_p,
                   index=pd.to_datetime(np.array(out_t, dtype="int64"),
                                        utc=True))
    return s_[s_.index.dayofweek < 5]


def eval_genome(g):
    s26 = sim50(g, R.D26)
    wk = R.wk_of(s26)
    if len(s26) < 70 or len(wk) < 20:
        return (-99999.0,) + (0,) * 8
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    usd = float(s26.sum() / len(wk))
    pos = (wk > 0).mean() * 100
    ww = float(wk.min()); wd = float(dy.min())
    mdd = float(maxdd(dy))
    sH_ = sim50(g, R.DH)
    sH_ = sH_[sH_.index < pd.Timestamp("2025-01-01", tz="UTC")]
    strongH = R.pool_usd_wk(sH_, STRONG_2324)
    weakH = R.pool_usd_wk(sH_, WEAK_2324)
    fit = ((usd - 700.0)
           - 0.8 * max(0.0, -mdd - 1850.0)
           - 12.0 * max(0.0, 85.0 - pos)
           - 0.4 * max(0.0, -ww - 1500.0)
           - 0.3 * max(0.0, -wd - 1300.0)
           - 0.5 * max(0.0, -weakH))
    if core_is_fade(g) and strongH <= 0:
        fit -= 800.0
    return (round(fit, 1), round(usd), round(pos), round(ww), round(wd),
            round(mdd), round(len(s26) / len(wk), 1), round(strongH),
            round(weakH))


def core_is_fade(g):
    return g["core"][0] == "FADE"


def pick(lst):
    return lst[int(RNG.integers(len(lst)))]


def rand_genome():
    r = RNG.random()
    if r < 0.6:
        core = ("FADE", pick([8, 10, 12]), pick([1.0, 1.2, 1.5]))
    elif r < 0.8:
        core = ("ORB", pick([40.0, 60.0, 80.0]))
    else:
        core = ("RIDE", pick([4.0, 5.0, 6.0]))
    return {"core": core,
            "guard": pick([6.0, 8.0, 10.0, 99.0]),
            "hybrid": bool(RNG.random() < 0.35),
            "xaccel": pick([None, 8.0, 10.0]),
            "dis": pick([None, 60.0, 80.0, 100.0]),
            "ladder": pick([(2.0, 4.0), (2.0, 3.0), (1.5, 4.0),
                            (99.0, 99.0)]),
            "qty": pick([1, 2, 3]),
            "hold": pick([12, 15, 18]),
            "pex": pick([None, None, 10.0, 20.0]),
            "wb": pick([None, 500.0, 700.0, 1000.0]),
            "nd": pick([None, 600.0]),
            "eqg": pick([None, None, (800.0, 1600.0), (1000.0, 2000.0)]),
            "dcap": pick([None, None, 400.0])}


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


def init_all():
    global STRONG_2324, WEAK_2324
    R.init_globals()
    F.prep(R.D26); F.prep(R.DH)
    prep50(R.D26); prep50(R.DH)
    STRONG_2324 = R.STRONG_2324
    WEAK_2324 = R.WEAK_2324


def main():
    t0 = time.time()
    init_all()
    bp_brake = {"core": ("FADE", 10, 1.2), "guard": 8.0, "hybrid": False,
                "xaccel": 10.0, "dis": 60.0, "ladder": (2.0, 4.0),
                "qty": 1, "hold": 15, "pex": None, "wb": 700.0,
                "nd": None, "eqg": None, "dcap": None}
    seeds = [bp_brake,
             {**bp_brake, "hybrid": True},
             {**bp_brake, "pex": 20.0},
             {**bp_brake, "hybrid": True, "pex": 20.0},
             {**bp_brake, "wb": None},
             {"core": ("ORB", 60.0), "guard": 99.0, "hybrid": False,
              "xaccel": None, "dis": None, "ladder": (99.0, 99.0),
              "qty": 3, "hold": 15, "pex": None, "wb": 700.0,
              "nd": None, "eqg": None, "dcap": None},
             {"core": ("RIDE", 5.0), "guard": 99.0, "hybrid": False,
              "xaccel": None, "dis": 100.0, "ladder": (99.0, 99.0),
              "qty": 2, "hold": 15, "pex": None, "wb": None,
              "nd": None, "eqg": None, "dcap": None}]
    pop = seeds + [rand_genome() for _ in range(300 - len(seeds))]
    cache = {}; genomes = {}
    bench = None
    for gen in range(60):
        todo = [g for g in pop if gkey(g) not in cache]
        for g in todo:
            cache[gkey(g)] = eval_genome(g); genomes[gkey(g)] = g
        if bench is None:
            bench = cache[gkey(bp_brake)]
            print(f"BP+brake benchmark: {bench}", flush=True)
        scored = sorted(pop, key=lambda g: -cache[gkey(g)][0])
        fb = cache[gkey(scored[0])]
        print(f"gen {gen:02d}: fit {fb[0]:8.1f} ${fb[1]:5.0f}/wk "
              f"pos {fb[2]:3.0f}% ww {fb[3]:6.0f} wd {fb[4]:6.0f} "
              f"MDD {fb[5]:6.0f} {fb[6]:5.1f}tr/wk sH {fb[7]:5.0f} "
              f"wH {fb[8]:6.0f} | {json.dumps(scored[0], default=str)[:100]}"
              f" ({time.time()-t0:.0f}s)", flush=True)
        elite = scored[:35]
        children = []
        while len(children) < 220:
            a_, b_ = RNG.choice(35, 2, replace=False)
            ch = crossover(elite[a_], elite[b_])
            if RNG.random() < 0.65:
                ch = mutate(ch)
            children.append(ch)
        pop = elite + children + [rand_genome() for _ in range(45)]
        ck = sorted(cache.items(), key=lambda kv: -kv[1][0])[:15]
        with open("research/round50_checkpoint.json", "w") as f:
            json.dump({"gen": gen, "evals": len(cache),
                       "top": [{"fit": v, "genome": genomes[k]}
                               for k, v in ck]}, f, default=str, indent=1)
    lb = sorted(cache.items(), key=lambda kv: -kv[1][0])
    print(f"\n=== TOP 15 of {len(cache)} (dominance target: "
          f">$702/wk AND MDD >-1876) ===")
    dom = 0
    out = []
    for k_, v_ in lb[:60]:
        g = genomes[k_]
        row = {"fit": v_, "genome": g}
        if v_[1] > 702 and v_[5] > -1876 and v_[2] >= 85:
            row["DOMINATES"] = True
            dom += 1
        out.append(row)
        if len(out) <= 15:
            print(f"  {v_} {'<<< DOMINATES' if row.get('DOMINATES') else ''}"
                  f" {json.dumps(g, default=str)[:110]}", flush=True)
    print(f"\ndominating genomes in top-60: {dom}")
    with open("research/round50_results.json", "w") as f:
        json.dump({"benchmark": bench, "top": out, "evals": len(cache)},
                  f, default=str, indent=1)
    print(f"\nDONE {len(cache)} genomes ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
