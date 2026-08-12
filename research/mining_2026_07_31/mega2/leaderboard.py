"""Per-strategy leaderboard with trade-level and day-level stats, ex-home."""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse, ensemble as E

CORES = [55, 1, 74, 15, 99, 77, 14, 66, 54, 94]
w = json.load(open(os.path.join(fuse.ROOT, "data", "fsearch_state.json")))["winners"]
seen, cands = set(), []
for c in w:
    k = (tuple(map(tuple, c["legs"])), c["k"], c["side"], c["stop"], c["tgt"])
    if k in seen: continue
    seen.add(k); cands.append(c)
pick = [cands[j] for j in CORES]

cons = [c for c in fuse.NQ_CONTRACTS if c in fuse.tape_meta()]
per = {i: [] for i in range(len(pick))}
with ProcessPoolExecutor(max_workers=4) as ex:
    for cn, out in ex.map(E.trades_on, cons, [pick]*len(cons)):
        for i, (t, p) in out.items():
            if cn != pick[i]["home"]:
                per[i].append(pd.DataFrame(dict(ts=t, pnl=p)))
        print(cn, "done", flush=True)

def runs(x):
    lw = ll = cw = cl = 0
    for v in x:
        if v > 0: cw += 1; cl = 0
        else: cl += 1; cw = 0
        lw = max(lw, cw); ll = max(ll, cl)
    return lw, ll

L = ["# Strategy leaderboard — every number ex-home (quarters the rule never saw)", "",
     "| # | core | tr/wk | win% | avg win/tr | avg loss/tr | run W/L (trades) | "
     "avg win day | avg loss day | best day | worst day | max DD | $/wk |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
rows = []
for i, c in enumerate(pick):
    if not per[i]: continue
    t = pd.concat(per[i]).sort_values("ts")
    d = t.set_index(pd.to_datetime(t.ts)).pnl.resample("D").sum()
    d = d[d.index.dayofweek < 5]
    nw = len(d)/5
    wins, losses = t.pnl[t.pnl > 0], t.pnl[t.pnl <= 0]
    lw, ll = runs(t.pnl.to_numpy())
    eq = d.cumsum(); dd = float((eq - eq.cummax()).min())
    wd, ld = d[d > 0], d[d < 0]
    rows.append(dict(core=CORES[i], tpw=len(t)/nw, win=len(wins)/len(t),
        aw=wins.mean(), al=losses.mean(), lw=lw, ll=ll,
        awd=wd.mean(), ald=ld.mean(), bd=d.max(), wo=d.min(),
        dd=dd, wk=float(d.resample("W").sum().mean()), d=d, t=t))
rows.sort(key=lambda r: -r["wk"])
for n, r in enumerate(rows, 1):
    L.append(f"| {n} | {r['core']} | {r['tpw']:.0f} | {r['win']*100:.0f}% | "
             f"${r['aw']:+.0f} | ${r['al']:+.0f} | {r['lw']}/{r['ll']} | "
             f"${r['awd']:+.0f} | ${r['ald']:+.0f} | ${r['bd']:+.0f} | "
             f"${r['wo']:+.0f} | ${abs(r['dd']):,.0f} | **${r['wk']:+.0f}** |")

best = rows[0]
book = pd.concat([r["d"] for r in rows], axis=1).fillna(0).sum(axis=1)
for name, d in ((f"BEST SINGLE (core {best['core']})", best["d"]),
                ("10-CORE BOOK", book)):
    wk = d.resample("W").sum()
    L += ["", f"## Top 10 best / worst — {name}", "",
          "| best days | worst days | best weeks | worst weeks |", "|---|---|---|---|"]
    bd = d.nlargest(10).round(0); wd_ = d.nsmallest(10).round(0)
    bw = wk.nlargest(10).round(0); ww = wk.nsmallest(10).round(0)
    for k in range(10):
        L.append(f"| {bd.index[k].date()} ${bd.iloc[k]:+,.0f} "
                 f"| {wd_.index[k].date()} ${wd_.iloc[k]:+,.0f} "
                 f"| {bw.index[k].date()} ${bw.iloc[k]:+,.0f} "
                 f"| {ww.index[k].date()} ${ww.iloc[k]:+,.0f} |")
out = os.path.join(fuse.ROOT, "research", "LEADERBOARD.md")
open(out, "w").write("\n".join(L) + "\n")
print("\n".join(L[:20])); print("wrote", out)
