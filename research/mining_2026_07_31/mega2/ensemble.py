"""The 100 survivors as a portfolio: cluster the duplicates, stack the rest.

WHY CLUSTERING COMES FIRST. The survivor table is dominated by one core --
dealer gamma x vol-ratio, both sustained -- wearing different third legs. A
"portfolio of 100" that is really eight ideas rehashed twelve times each is
not diversified, it is one bet at 12x size with extra steps. So rules are
clustered by the OVERLAP OF THEIR ACTUAL TRADES (Jaccard on trade-bar sets
across all quarters), and one representative -- the best out-of-sample $/week
-- survives per cluster. Two rules that trade the same bars are the same rule
whatever their labels say, which was learned the hard way twice today.

WHY EX-HOME ONLY. Each rule's P&L EXCLUDES the quarter it was discovered in.
The home quarter is fitted; including it would smuggle the in-sample money
back into the headline. The cost is that the portfolio has fewer active rules
in quarters where many homes cluster (NQZ4), which is visible in the daily
row counts rather than hidden.

WHAT COMES OUT: the combo2-style spec sheet -- trades/week, $/week, best and
worst day and week, average winning and losing day, max drawdown, longest
losing streak -- for each distinct core alone and for the stacked portfolio,
plus the pairwise correlation matrix of the kept cores.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402
import vsearch as V  # noqa: E402
import fsearch as FS  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "ENSEMBLE.md"))
STATE = os.path.join(fuse.ROOT, "data", "fsearch_state.json")
KBAR = int(os.environ.get("KBAR", "500"))
MAXJ = float(os.environ.get("MAXJ", "0.4"))     # Jaccard above this = same rule
TV, TPX, COST, MAKER = 0.50, 0.25, 1.24, 0.355
ACCOUNT = 4100.0
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def trades_on(cn, cands):
    """Every candidate's trades on one quarter: global bar ids, ts, pnl."""
    B, F = V.cached(cn, KBAR)
    n = len(B["c"])
    ts = B["ts"][:n]
    out, cache, fcache, sigs = {}, {}, {}, {}
    for j, c in enumerate(cands):
        key = (c["stop"], c["tgt"], c["side"])
        if key not in cache:
            kk = np.array(sorted({c["stop"], c["tgt"]}), dtype=np.int64)
            si = int(np.where(kk == c["stop"])[0][0])
            ti = int(np.where(kk == c["tgt"])[0][0])
            u, d = hunt.tau(B, kk, TPX)
            r, hold, _ = hunt.outcomes(B, u, d, si, ti, c["side"], kk,
                                       TPX, TV)[:3]
            del u, d
            cache[key] = (r.astype(np.float32), hold.astype(np.int32))
        r, hold = cache[key]
        sk = (tuple(map(tuple, c["legs"])), c["k"])
        sig = sigs.get(sk)
        if sig is None:
            tot, have = np.zeros(n, dtype=np.int16), 0
            for fn, sd, q in c["legs"]:
                parts = fn.split("|")
                root = parts[0]
                form = parts[1] if len(parts) > 1 else "raw"
                sh = parts[2] if len(parts) > 2 else "state"
                fk = (root, form)
                if fk not in fcache:
                    v0 = F.get(root)
                    fcache[fk] = (None if v0 is None else
                                  FS.forms(np.asarray(v0, np.float64),
                                           n).get(form))
                v = fcache[fk]
                if v is None:
                    continue
                fin = np.isfinite(v)
                if fin.sum() < n * 0.4:
                    continue
                thr = float(np.quantile(v[fin], q))
                bs = ((v >= thr) if sd > 0 else (v <= thr)) & fin
                tot += FS.shape(bs, sh).astype(np.int16)
                have += 1
            sig = (tot >= c["k"]) if have >= c["k"] else False
            sigs[sk] = sig
        if sig is False:
            continue
        idx = FS.nonoverlap(np.flatnonzero(sig), hold)
        if len(idx) < 5:
            continue
        out[j] = (ts[idx], (r[idx] - COST + MAKER).astype(np.float64))
    return cn, out


def daily(frames):
    t = pd.concat(frames)
    d = t.set_index(pd.to_datetime(t.ts)).pnl.resample("D").sum()
    return d[d.index.dayofweek < 5]


def specs(d):
    eq = d.cumsum()
    wk = d.resample("W").sum()
    run = cur = 0
    for v in d:
        cur = cur + 1 if v < 0 else 0
        run = max(run, cur)
    w, ls = d[d > 0], d[d < 0]
    return dict(perweek=float(wk.mean()), bestd=float(d.max()),
                worstd=float(d.min()), bestw=float(wk.max()),
                worstw=float(wk.min()),
                avgwin=float(w.mean()) if len(w) else 0.0,
                avgloss=float(ls.mean()) if len(ls) else 0.0,
                dd=float((eq - eq.cummax()).min()), streak=run,
                green=float((d > 0).mean()), tot=float(d.sum()))


def main():
    winners = json.load(open(STATE))["winners"]
    seen, cands = set(), []
    for c in winners:
        k = (tuple(map(tuple, c["legs"])), c["k"], c["side"],
             c["stop"], c["tgt"])
        if k in seen:
            continue
        seen.add(k)
        cands.append(c)
    print(f"{len(winners)} winners -> {len(cands)} unique parameterisations",
          flush=True)

    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    per = {j: {} for j in range(len(cands))}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for cn, out in ex.map(trades_on, cons,
                              [cands] * len(cons)):
            for j, v in out.items():
                per[j][cn] = v
            print(f"  {cn} done", flush=True)

    # ---- trade-set overlap clustering, ex-home ----
    bars = {}
    for j, c in enumerate(cands):
        s = set()
        for cn, (t, _p) in per[j].items():
            if cn == c["home"]:
                continue
            s |= {(cn, int(x)) for x in t.astype(np.int64) // 10**9}
        bars[j] = s
    order = sorted(range(len(cands)),
                   key=lambda j: -(cands[j]["oos"]["dol"] *
                                   cands[j]["oos"]["tpw"]))
    kept = []
    for j in order:
        if not bars[j]:
            continue
        dup = False
        for k in kept:
            inter = len(bars[j] & bars[k])
            uni = len(bars[j] | bars[k])
            if uni and inter / uni > MAXJ:
                dup = True
                break
        if not dup:
            kept.append(j)
    print(f"{len(cands)} unique -> {len(kept)} distinct cores "
          f"(Jaccard<{MAXJ})", flush=True)
    # CORES env: measure a chosen subset -- e.g. the handful whose individual
    # drawdowns actually fit a $4,100 account -- instead of estimating the
    # subset's numbers by arithmetic on the full-stack table.
    want = os.environ.get("CORES")
    if want:
        pick = {int(x) for x in want.split(",")}
        kept = [j for j in kept if j in pick]
        print(f"subset requested: {sorted(pick)} -> {len(kept)} kept",
              flush=True)

    # ---- per-core and portfolio daily P&L, ex-home ----
    dailies, rows = {}, []
    for j in kept:
        c = cands[j]
        fr = [pd.DataFrame(dict(ts=t, pnl=p))
              for cn, (t, p) in per[j].items() if cn != c["home"]]
        if not fr:
            continue
        d = daily(fr)
        if len(d) < 100:
            continue
        dailies[j] = d
        ntr = sum(len(p) for cn, (t, p) in per[j].items()
                  if cn != c["home"])
        sp = specs(d)
        legs = ",".join(x[0].split("|")[0] for x in c["legs"])[:44]
        rows.append((j, c, sp, ntr, legs))
    if not dailies:
        print("nothing to stack")
        return
    port = pd.concat(dailies.values(), axis=1).fillna(0.0).sum(axis=1)
    psp = specs(port)
    nweeks = len(port) / 5
    tott = sum(r[3] for r in rows)

    log("# The validated survivors, stacked as one portfolio")
    log()
    log(f"`{len(cands)}` unique survivor parameterisations collapsed to "
        f"**{len(rows)} genuinely distinct cores** — rules whose actual "
        f"trades overlap less than {MAXJ:.0%} (Jaccard on trade-bar sets). "
        f"The rest were the same trades wearing different labels. Every "
        f"number below **excludes each rule's home quarter** — only money "
        f"made on data the rule never saw is counted.")
    log()
    log("| core | side | legs | tr/wk | $/tr | **$/wk** | worst wk | max DD "
        "| streak |")
    log("|---|---|---|---|---|---|---|---|---|")
    for j, c, sp, ntr, legs in rows:
        tpw = ntr / nweeks
        log(f"| {j} | {'L' if c['side'] > 0 else 'S'} | `{legs}` | "
            f"{tpw:.0f} | ${sp['tot']/max(ntr,1):+.2f} | "
            f"**${sp['perweek']:+,.0f}** | ${sp['worstw']:+,.0f} | "
            f"${abs(sp['dd']):,.0f} | {sp['streak']}d |")
    log()
    log("## The portfolio — all cores, one contract each")
    log()
    log(f"| | value |")
    log(f"|---|---|")
    log(f"| trades/week | **{tott/nweeks:.0f}** |")
    log(f"| **$/week** | **${psp['perweek']:+,.0f}** |")
    log(f"| best / worst day | ${psp['bestd']:+,.0f} / ${psp['worstd']:+,.0f} |")
    log(f"| best / worst week | ${psp['bestw']:+,.0f} / ${psp['worstw']:+,.0f} |")
    log(f"| avg winning / losing day | ${psp['avgwin']:+,.0f} / "
        f"${psp['avgloss']:+,.0f} |")
    log(f"| % days green | {psp['green']:.0%} |")
    log(f"| **max drawdown** | **${abs(psp['dd']):,.0f}** "
        f"({abs(psp['dd'])/ACCOUNT:.0%} of $4,100) |")
    log(f"| longest losing streak | {psp['streak']} days |")
    log(f"| total over {len(port):,} days | ${psp['tot']:+,.0f} |")
    log()
    if len(dailies) > 1:
        cm = pd.concat(dailies.values(), axis=1).fillna(0.0).corr()
        off = cm.values[np.triu_indices(len(cm), 1)]
        log(f"Pairwise daily correlation between cores: median "
            f"**{np.median(off):+.2f}**, max {off.max():+.2f}. Low is the "
            f"whole point — that is what makes stacking reduce risk instead "
            f"of multiplying it.")
    log()
    log("Caveats that stay attached to these numbers: execution is priced at "
        "the **measured front-of-queue** maker edge (+$0.355), not the flat "
        "two ticks; concurrent cores mean more than one contract at once on "
        "some days — margin needs checking against the account; and the "
        "cores were selected from 66,220 validated draws, so the ensemble "
        "must be re-proven on ES/CL before it is believed.")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
