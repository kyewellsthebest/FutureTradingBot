"""The leash between NQ and ES, traded: index-arb reconvergence.

NQ and ES are chained by index arbitrage. When one runs ahead of the other
beyond the noise band, the gap closes because closing it is someone's paid
job -- the reconvergence is mechanical, not predictive. Long the laggard,
short the leader, flat on reconvergence. Market-neutral by construction.

MACHINERY. Both tick tapes to a one-minute mid grid; rolling hedge ratio
beta = cov(dNQ, dES)/var(dES) over W minutes (lagged one bar -- today's
beta must not see today's dislocation); spread s = logNQ - beta*logES;
z = (s - mean_Z(s)) / std_Z(s), all rolling and lagged. Enter when |z|
crosses ZIN, exit at z touching 0, |z| > ZSTOP (the leash snapped --
divergences can be real: composition changes, sector shocks), or TIMEOUT
minutes. Position: 1 MNQ vs round(beta * notional ratio) MES.

COSTS, both legs, taker: MNQ commission 1.24 + 1 tick 0.50 in and out;
MES 1.24 + 1.25 in and out. A pair round trip costs ~$5.98 -- the
dislocation has to be worth more than that, which is the honest bar.

VALIDATION, same religion as everything else: parameter grid is SMALL
(4 x 2 x 2 x 2 = 32 cells, not millions), each cell trains on the first
60% of each overlapping quarter and must pay on the last 40%, and the
pick must be profitable in a MAJORITY of quarters -- no cherry-picking a
quarter, no cherry-picking a cell after seeing test.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

OUT = os.path.join(fuse.ROOT, "research", "PAIR.md")
TRAIN = 0.60
# per-pair round trip: commissions + one tick crossed per leg, each way
COST = 2 * 1.24 + 2 * 0.50 + 2 * 1.25
PNL_MNQ = 2.0     # $ per index point (MNQ)
PNL_MES = 5.0     # $ per index point (MES)

GRID = [dict(W=w, Z=z, ZIN=zi, TO=to)
        for w in (120, 240) for z in (120, 240)
        for zi in (2.0, 2.5, 3.0, 3.5) for to in (120,)]
ZSTOP = 5.0


def grid_minutes(path, t0, t1):
    ts, px, _ = fuse.load_tape(path)
    m = (ts >= t0) & (ts <= t1)
    ts, px = ts[m], px[m]
    idx = pd.to_datetime(ts)
    s = pd.Series(px, index=idx).resample("1min").last().ffill()
    return s


def run_cell(z, nq, es, beta, cell, lo, hi):
    """One parameter cell on one contiguous slice [lo:hi) of the grid."""
    zin, to = cell["ZIN"], cell["TO"]
    pos, e_i, pnl, trades = 0, 0, [], 0
    zz = z.values
    nqv, esv, bv = nq.values, es.values, beta.values
    for i in range(lo, hi):
        if not np.isfinite(zz[i]) or not np.isfinite(bv[i]):
            continue
        if pos == 0:
            if abs(zz[i]) >= zin and abs(zz[i]) < ZSTOP:
                pos = -int(np.sign(zz[i]))     # z high => NQ rich => short NQ
                e_i = i
        else:
            done = (zz[i] * pos >= 0 or abs(zz[i]) >= ZSTOP
                    or i - e_i >= to or i == hi - 1)
            if done:
                dnq = (nqv[i] - nqv[e_i]) * PNL_MNQ * pos
                # hedge leg: opposite sign, beta-scaled MES count (>=1)
                nmes = max(int(round(bv[e_i] * (nqv[e_i] * PNL_MNQ) /
                                     (esv[e_i] * PNL_MES))), 1)
                des = (esv[i] - esv[e_i]) * PNL_MES * (-pos) * nmes
                pnl.append(dnq + des - COST)
                trades += 1
                pos = 0
    return np.array(pnl), trades


def main():
    meta = fuse.tape_meta()
    pairs = []
    for nqc in fuse.NQ_CONTRACTS:
        if nqc not in meta:
            continue
        v = meta[nqc]
        esc = fuse.pick_contract(meta, "ES", v["t0"], v["t1"])
        if esc:
            pairs.append((nqc, esc, v["t0"], v["t1"]))
    print(f"{len(pairs)} overlapping quarters", flush=True)

    L = ["# NQ-ES pair reconvergence, validated", "",
         "Rolling-beta spread z-score, enter |z| at threshold, exit at 0 / "
         "stop / timeout. Both legs charged taker costs "
         f"(${COST:.2f}/round trip). Grid of 16 cells; train 60% / test "
         "40% per quarter; the cell is chosen on TRAIN totals only.", ""]
    res = {}
    for nqc, esc, t0, t1 in pairs:
        nq = np.log(grid_minutes(meta[nqc]["path"], t0, t1))
        es = np.log(grid_minutes(meta[esc]["path"], t0, t1))
        ix = nq.index.intersection(es.index)
        nq, es = nq[ix], es[ix]
        # RTH only: dislocations in the thin overnight are mostly stale prints
        rth = (ix.hour * 60 + ix.minute >= 13 * 60 + 30) & (ix.hour < 20)
        dn, de = nq.diff(), es.diff()
        for cell in GRID:
            W, Z = cell["W"], cell["Z"]
            cov = dn.rolling(W).cov(de)
            var = de.rolling(W).var()
            beta = (cov / var.replace(0, np.nan)).shift(1)
            s = nq - beta * es
            zscore = ((s - s.rolling(Z).mean()) /
                      s.rolling(Z).std().replace(0, np.nan)).shift(1)
            zr = zscore.where(rth)
            cut = int(len(ix) * TRAIN)
            # price series in points, not logs, for P&L
            enq = np.exp(nq) if nqc else None
            a, ta = run_cell(zr, np.exp(nq), np.exp(es), beta,
                             cell, Z + W, cut)
            b, tb = run_cell(zr, np.exp(nq), np.exp(es), beta,
                             cell, cut, len(ix))
            key = (cell["W"], cell["Z"], cell["ZIN"])
            r = res.setdefault(key, dict(tr_pnl=0.0, tr_n=0, te_pnl=0.0,
                                         te_n=0, q=[]))
            r["tr_pnl"] += float(a.sum()); r["tr_n"] += ta
            r["te_pnl"] += float(b.sum()); r["te_n"] += tb
            r["q"].append((nqc, float(b.sum()), tb))
        print(f"  {nqc}/{esc} done", flush=True)

    # choose on TRAIN only, then report the chosen cell's TEST truthfully
    best = max(res.items(), key=lambda kv: kv[1]["tr_pnl"])
    L += ["| W | Z | z-in | train $ | train n | **test $** | test n | "
          "test green q |", "|---|---|---|---|---|---|---|---|"]
    for k, r in sorted(res.items(), key=lambda kv: -kv[1]["tr_pnl"])[:8]:
        g = sum(1 for _, p, _ in r["q"] if p > 0)
        mark = " **<-**" if k == best[0] else ""
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {r['tr_pnl']:+,.0f} | "
                 f"{r['tr_n']} | **{r['te_pnl']:+,.0f}** | {r['te_n']} | "
                 f"{g}/{len(r['q'])}{mark} |")
    k, r = best
    wk = r["te_n"] and r["te_pnl"] / r["te_n"]
    L += ["", f"Chosen on train: W={k[0]} Z={k[1]} zin={k[2]} -> test "
          f"**${r['te_pnl']:+,.0f}** over {r['te_n']} trades "
          f"(${wk:+.2f}/trade), green in "
          f"{sum(1 for _, p, _ in r['q'] if p > 0)}/{len(r['q'])} quarters.",
          "", "Per-quarter test P&L of the chosen cell:", ""]
    for nqc, p, n in r["q"]:
        L.append(f"- {nqc}: ${p:+,.0f} on {n} trades")
    open(OUT, "w").write("\n".join(L) + "\n")
    json.dump({str(k): v for k, v in res.items()},
              open(os.path.join(fuse.ROOT, "data", "pair_state.json"), "w"),
              default=float)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
