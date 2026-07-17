"""Round 61: THE TRUE DOUBLING. ~2,400 bracket configs with the one
lever that mechanically improves realized win/loss ratio: DEEP passive
entry offsets (1.5-3pt beyond signal). Dual fee models (worst $1.50 /
real-broker $0.78). Dream detector (verified by self-test) on both.
Ratio-frontier tracker: best realized ratio per win-rate bucket ->
the empirical feasibility boundary of this market.
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round54_clock as K
import round46_bulletproof_ga as R
from round58_frontier import prep_clock
from round60_dream import bracket_exit, metrics
from round48_drawdown import maxdd

ENTRY_LO, ENTRY_HI, GUARD = 14.0, 20.73, 8.0
EOD_NS = (20 * 60 + 55) * 60_000_000_000


def sim_deep_bracket(g, ts, px, C, sec):
    n = len(ts)
    c, hrs, sdt = C["c"], C["hrs"], C["sdt"]
    bts, days, nb = C["bts"], C["days"], C["nb"]
    atr_eq = C["atr"] * np.sqrt(60.0 / sec)
    ninf = np.nan_to_num(atr_eq, nan=np.inf)
    kb = max(1, int(g["km"] * 60 / sec))
    mom = np.concatenate(([0.0] * kb, c[kb:] - c[:-kb]))
    thr = g["a"] * ninf
    ent = (hrs >= ENTRY_LO) & (hrs < ENTRY_HI) & (np.abs(sdt) <= GUARD)
    raw = np.where(mom < -thr, 1, np.where(mom > thr, -1, 0))
    sig = np.where(ent, raw, 0)
    out_t, out_p = [], []
    busy = 0
    cxl_ns = int(g.get("cxl", 90) * 1e9)
    for i in np.flatnonzero(sig):
        if bts[i] < busy:
            continue
        s = int(sig[i])
        L = c[i] - g["off"] * s
        a0 = np.searchsorted(ts, bts[i] + R.LAT_NS, "left")
        a1 = np.searchsorted(ts, bts[i] + cxl_ns, "left")
        if a0 >= n: break
        seg = px[a0:a1]
        th = np.flatnonzero(seg * s < (L - R.TICK * s) * s + 1e-9)
        if not len(th):
            continue
        fi = a0 + int(th[0])
        t_max = min(ts[fi] + R.HN(30), days[i] + EOD_NS)
        fill, k = bracket_exit(ts, px, fi, L, s, g["tgt"], g["stop"],
                               t_max, C["day_last_i"][i])
        if fill is None:
            continue
        out_p.append((fill - L) * s * R.PT - R.FEES)
        out_t.append(ts[k])
        busy = ts[k]
    s_ = pd.Series(out_p, index=pd.to_datetime(
        np.array(out_t, dtype="int64"), utc=True))
    return s_[s_.index.dayofweek < 5]


def main():
    t0 = time.time()
    K.build_tape()
    for sec in (60, 30, 15):
        prep_clock(K.D[sec], K.D["ts"])
    ts26, px26 = K.D["ts"], K.D["px"]
    n_run = 0
    dream = []
    frontier = {}       # wr_bucket -> (best_ratio, name, m)
    best_usd = []
    TGT_STOP = [(3, 5), (3, 8), (5, 5), (5, 8), (5, 12), (7, 7), (7, 12),
                (10, 8), (10, 15), (15, 10), (15, 25), (12, 12)]
    for sec in (60, 30, 15):
        C = K.D[sec]
        for km in (1, 2, 3, 5, 8):
            for a in (0.6, 0.8, 1.0, 1.2, 1.5):
                for off in (1.5, 2.0, 3.0):
                    for tgt, stop in TGT_STOP:
                        g = {"km": km, "a": a, "off": off,
                             "tgt": float(tgt), "stop": float(stop)}
                        n_run += 1
                        s = sim_deep_bracket(g, ts26, px26, C, sec)
                        for fee_tag, shift in (("F150", 0.0),
                                               ("F078", 0.72)):
                            m = metrics(s + shift if shift else s)
                            if m is None:
                                continue
                            nm = (f"c{sec} m{km} a{a} o{off} t{tgt} "
                                  f"s{stop} {fee_tag}")
                            if (45 <= m["wr"] <= 55 and m["ratio"] >= 1.5
                                    and m["tr_wk"] >= 150):
                                dream.append((nm, m))
                                print(f"DREAM-FLAG {nm}: {m}", flush=True)
                            if m["tr_wk"] >= 150:
                                b = int(m["wr"] // 5) * 5
                                cur = frontier.get(b)
                                if cur is None or m["ratio"] > cur[0]:
                                    frontier[b] = (m["ratio"], nm, m)
                            if fee_tag == "F150":
                                best_usd.append((m["usd_wk"], nm, m))
            print(f"  c{sec} km{km} done: {n_run} evals x2 fees "
                  f"({time.time()-t0:.0f}s)", flush=True)
    best_usd.sort(key=lambda z: -z[0])
    print(f"\n=== TOP 10 by $/wk at worst-case fees "
          f"(of {n_run} configs x 2 fee models) ===")
    for usd, nm, m in best_usd[:10]:
        print(f"  {nm}: {m}", flush=True)
    print(f"\n=== RATIO FRONTIER (best realized ratio per WR bucket, "
          f"tr/wk>=150, either fee model) ===")
    for b in sorted(frontier):
        r, nm, m = frontier[b]
        print(f"  WR {b:2d}-{b+4}%: best ratio {r:.2f}  "
              f"({nm}; $/wk {m['usd_wk']})", flush=True)
    print(f"\ndream flags: {len(dream)}")
    with open("research/round61_results.json", "w") as f:
        json.dump({"n_run": n_run, "dream": dream,
                   "frontier": {str(k): (v[0], v[1], v[2])
                                for k, v in frontier.items()},
                   "top": [(nm, m) for _, nm, m in best_usd[:20]]},
                  f, indent=1, default=str)
    print(f"\nDONE {n_run} configs x 2 fee models = {n_run*2} "
          f"evaluations ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
