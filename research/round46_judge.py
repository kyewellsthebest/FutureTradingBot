"""Round 46 judge: exhaustive validation of finalist genomes vs champion.
Usage: python3 research/round46_judge.py '<genome-json>' ['<genome-json>' ...]
Runs: 2026 weekly table + fold table; 2023/2024/2025 yearly; strong/weak
regime pools per year; fee stress $2.50/RT; latency stress 200ms.
"""
import json, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research")
import round46_bulletproof_ga as R


def detuple(g):
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in g.items()}


def table(nm, gn):
    print(f"\n######## {nm} ########")
    print(json.dumps(gn, default=str))
    s26 = R.sim(gn, R.D26)
    wk = R.wk_of(s26)
    dy = s26.resample("D").sum(); dy = dy[dy != 0]
    print(f"2026: $/wk {s26.sum()/max(len(wk),1):7.0f}  pos {(wk>0).mean()*100:3.0f}%  "
          f"ww {wk.min():6.0f}  wd {dy.min():6.0f}  p5d {np.percentile(dy,5):6.0f}  "
          f"tr/wk {len(s26)/max(len(wk),1):5.1f}")
    for lo, hi, fn in (("2026-01-01","2026-03-01","JanFeb"),
                       ("2026-03-01","2026-05-01","MarApr"),
                       ("2026-05-01","2026-06-01","May   "),
                       ("2026-06-01","2026-07-07","JunJul")):
        f = s26[(s26.index >= pd.Timestamp(lo, tz="UTC"))
                & (s26.index < pd.Timestamp(hi, tz="UTC"))]
        w = R.wk_of(f)
        print(f"  {fn}: $/wk {f.sum()/max(len(w),1):7.0f}  pos {(w>0).mean()*100:3.0f}%  n={len(f)}")
    print("  weekly:", [round(v) for v in wk.values])
    # fee stress
    R.FEES = 2.50
    s26f = R.sim(gn, R.D26); R.FEES = 1.50
    wkf = R.wk_of(s26f)
    print(f"  fee $2.50/RT: $/wk {s26f.sum()/max(len(wkf),1):.0f}  pos {(wkf>0).mean()*100:.0f}%")
    # latency stress
    lat0 = R.LAT_NS
    R.LAT_NS = 200_000_000
    s26l = R.sim(gn, R.D26); R.LAT_NS = lat0
    wkl = R.wk_of(s26l)
    print(f"  latency 200ms: $/wk {s26l.sum()/max(len(wkl),1):.0f}  pos {(wkl>0).mean()*100:.0f}%")
    if gn["size"][0] == "ladder_fvcap":
        print("  (flow-gated: history not evaluable)")
        return
    sH = R.sim(gn, R.DH)
    wr = R.DH["wkrev"]
    for yr in (2023, 2024, 2025):
        sy = sH[sH.index.year == yr]
        if not len(sy):
            continue
        w = R.wk_of(sy)
        d = sy.resample("D").sum(); d = d[d != 0]
        wy = wr[[x for x in wr.index if x.startswith(str(yr))
                 or (yr == 2023 and x < "2024-01-01")]]
        wy = wr[[x for x in wr.index if str(yr) in x[:4]]]
        q1, q3 = wy.quantile(0.25), wy.quantile(0.75)
        st_ = set(wy[wy <= q1].index); wk_ = set(wy[wy >= q3].index)
        print(f"  {yr}: $/wk {sy.sum()/max(len(w),1):6.0f}  pos {(w>0).mean()*100:3.0f}%  "
              f"ww {w.min():6.0f}  wd {d.min():6.0f}  "
              f"strongrev ${R.pool_usd_wk(sy, st_):6.0f}/wk  "
              f"weakrev ${R.pool_usd_wk(sy, wk_):6.0f}/wk")


def main():
    t0 = time.time()
    R.init_globals()
    champ = {"sig": ("MOMR", 10, 1.2), "guard": None,
             "size": ("ladder", 2.0, 3.0),
             "entry": (True, 1.0, 180), "hold": 15, "dis": None}
    table("CHAMPION (deployed FADESZ+P)", champ)
    for arg in sys.argv[1:]:
        gn = detuple(json.loads(arg))
        table("CANDIDATE", gn)
    print(f"\n({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
