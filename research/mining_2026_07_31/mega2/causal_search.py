"""Exhaustive CAUSAL search of the pullback-after-impulse family.

Every executable variation, under the audited causal engine:
  - archetype: WITH-impulse resting limit / AGAINST-impulse stop-entry
  - impulse 3/5/8/12 pts over 3/6/10 bars (close-to-close)
  - retracement 0.382/0.5/0.618/0.786/1.0
  - stop 5/10/15/20 x target 5/10/20/30/40
  - window 5/10/20 minutes
  - resting policy: first-cross-wins / deepest-level-only

14,400 cells. Discipline: cell chosen on TRAIN (first 60% of each
quarter) totals ONLY; the held-out 40% is reported, never selected on.
Multiple-testing honesty: the report includes the full held-out
distribution across all cells -- a train-winner whose held-out sits
inside that null spread is NOISE, not edge. Survivor bar: train-top
cell held-out positive with >=6/8 green quarters AND >= p99 of the
all-cell held-out distribution AND its 30-min-stale placebo loses.

Checkpoint per quarter: data/causal_search_ck.pkl.
Output: research/CAUSAL_SEARCH.md.
"""
import os
import pickle
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse            # noqa: E402
import causal_engine as ce  # noqa: E402

TRAIN = 0.60
GRID = [dict(arch=a, imp=float(i), w=w, retr=r, S=float(S), T=float(T),
             hold_s=h, policy=p, tick=0.25, tv=2.0)
        for a in ("limit", "stop")
        for i in (3, 5, 8, 12)
        for w in (3, 6, 10)
        for r in (0.382, 0.5, 0.618, 0.786, 1.0)
        for S in (5, 10, 15, 20)
        for T in (5, 10, 20, 30, 40)
        for h in (300, 600, 1200)
        for p in ("first", "deep")]

_G = {}


def _init_quarter(path):
    ts, px, _ = fuse.load_tape(path)
    o = np.argsort(ts, kind="stable")
    ts, px = ts[o], px[o]
    bt, bc, rth = ce.bars_of(ts, px)
    _G.update(ts=ts, px=px, bt=bt, bc=bc, rth=rth,
              mi=ce.MinuteIndex(ts, px, bt),
              cut=int(len(bc) * TRAIN), n=len(bc))


def _one(cell):
    a = ce.run_cell(_G["ts"], _G["px"], _G["bt"], _G["bc"], _G["rth"],
                    0, _G["cut"], cell, mindex=_G["mi"])
    b = ce.run_cell(_G["ts"], _G["px"], _G["bt"], _G["bc"], _G["rth"],
                    _G["cut"], _G["n"], cell, mindex=_G["mi"])
    key = tuple(sorted((k, v) for k, v in cell.items()
                       if k not in ("tick", "tv")))
    return (key, sum(t[4] for t in a), len(a),
            sum(t[4] for t in b), len(b))


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    ckp = os.path.join(fuse.ROOT, "data", "causal_search_ck.pkl")
    per, done = {}, set()
    if os.path.exists(ckp):
        try:
            per, done = pickle.load(open(ckp, "rb"))
            print(f"resume: {sorted(done)}", flush=True)
        except Exception:
            per, done = {}, set()
    for cn in cons:
        if cn in done:
            continue
        _init_quarter(meta[cn]["path"])
        with Pool(6) as pool:
            for key, tra, na, tea, nb in pool.imap_unordered(
                    _one, GRID, chunksize=64):
                r = per.setdefault(key, dict(tra=0.0, trn=0, tea=0.0,
                                             ten=0, q=[]))
                r["tra"] += tra
                r["trn"] += na
                r["tea"] += tea
                r["ten"] += nb
                r["q"].append((cn, tea, nb))
        done.add(cn)
        pickle.dump((per, done), open(ckp + ".tmp", "wb"))
        os.replace(ckp + ".tmp", ckp)
        print(f"{cn} done ({len(per)} cells)", flush=True)

    rows = sorted(per.items(), key=lambda kv: -kv[1]["tra"])
    ho_all = np.array([v["tea"] for _, v in per.items()])
    wk = 215 / 5
    L = ["# Exhaustive causal family search "
         f"({len(GRID):,} cells, NQ, train-pick discipline)", "",
         "Both archetypes, every parameter variation, audited causal "
         "engine (research/VALIDATOR_AUDIT.md). Held-out = last 40% of "
         "each quarter, never used for selection.", "",
         f"**Null context**: across ALL {len(per):,} cells the held-out "
         f"distribution is mean ${ho_all.mean():+,.0f}, p95 "
         f"${np.percentile(ho_all, 95):+,.0f}, p99 "
         f"${np.percentile(ho_all, 99):+,.0f}, max "
         f"${ho_all.max():+,.0f}. A train-winner inside this spread is "
         "selection noise, not edge.", "",
         "| arch | imp | w | retr | S | T | hold | pol | train $ | "
         "**held-out $** | ho n | ho/wk | green q |", "|" + "---|" * 13]
    for key, v in rows[:20]:
        c = dict(key)
        g = sum(1 for _, p_, _ in v["q"] if p_ > 0)
        L.append(f"| {c['arch']} | {c['imp']:.0f} | {c['w']} | "
                 f"{c['retr']} | {c['S']:.0f} | {c['T']:.0f} | "
                 f"{c['hold_s']//60}m | {c['policy'][:4]} | "
                 f"{v['tra']:+,.0f} | **{v['tea']:+,.0f}** | {v['ten']} "
                 f"| {v['ten']/wk/0.4*0.4:.0f} | {g}/{len(v['q'])} |")
    top = rows[0][1]
    tg = sum(1 for _, p_, _ in top["q"] if p_ > 0)
    p99 = float(np.percentile(ho_all, 99))
    survives = (top["tea"] > 0 and tg >= 6
                and top["tea"] >= p99)
    L += ["", f"## Verdict: train-winner held-out "
          f"**${top['tea']:+,.0f}** ({tg}/{len(top['q'])} green) vs "
          f"all-cell p99 ${p99:+,.0f} -> "
          f"{'**SURVIVOR — run placebo + cross-market**' if survives else '**NOISE — no causal edge in this family on NQ**'}",
          ""]
    out = os.path.join(fuse.ROOT, "research", "CAUSAL_SEARCH.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
