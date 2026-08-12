"""How many contracts is the 10-core book actually holding at once?

The ensemble's drawdown already CONTAINS the overlap losses -- daily P&L is
summed on one clock, so days when several shorts sank together are in the
worst-day and drawdown numbers. What the backtest never checked is the
POSITION count: margin is charged per open contract, and a backtest that
would have been margin-called is fiction. This measures max and typical
concurrency, and whether any hold spans the 5pm ET halt into overnight
margin territory.
"""
import json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse, hunt, vsearch as V, fsearch as FS

CORES = [55, 1, 74, 15, 99, 77, 14, 66, 54, 94]
w = json.load(open(os.path.join(fuse.ROOT, "data", "fsearch_state.json")))["winners"]
seen, cands = set(), []
for c in w:
    k = (tuple(map(tuple, c["legs"])), c["k"], c["side"], c["stop"], c["tgt"])
    if k in seen: continue
    seen.add(k); cands.append(c)
pick = [cands[j] for j in CORES]

iv = []
for cn in [c for c in fuse.NQ_CONTRACTS if c in fuse.tape_meta()]:
    B, F = V.cached(cn, 500)
    n = len(B["c"]); ts = B["ts"][:n]
    fcache, cache = {}, {}
    for c in pick:
        if c["home"] == cn: continue
        key = (c["stop"], c["tgt"], c["side"])
        if key not in cache:
            kk = np.array(sorted({c["stop"], c["tgt"]}), dtype=np.int64)
            si = int(np.where(kk == c["stop"])[0][0]); ti = int(np.where(kk == c["tgt"])[0][0])
            u, d = hunt.tau(B, kk, 0.25)
            r, hold, _ = hunt.outcomes(B, u, d, si, ti, c["side"], kk, 0.25, 0.50)[:3]
            del u, d
            cache[key] = hold.astype(np.int64)
        hold = cache[key]
        tot, have = np.zeros(n, np.int16), 0
        for fn, sd, q in c["legs"]:
            parts = fn.split("|"); root = parts[0]
            form = parts[1] if len(parts) > 1 else "raw"
            sh = parts[2] if len(parts) > 2 else "state"
            fk = (root, form)
            if fk not in fcache:
                v0 = F.get(root)
                fcache[fk] = None if v0 is None else FS.forms(np.asarray(v0, np.float64), n).get(form)
            v = fcache[fk]
            if v is None: continue
            fin = np.isfinite(v)
            if fin.sum() < n * 0.4: continue
            thr = float(np.quantile(v[fin], q))
            bs = ((v >= thr) if sd > 0 else (v <= thr)) & fin
            tot += FS.shape(bs, sh).astype(np.int16); have += 1
        if have < c["k"]: continue
        idx = FS.nonoverlap(np.flatnonzero(tot >= c["k"]), hold)
        for i in idx:
            j = min(int(i + hold[i]), n - 1)
            iv.append((ts[i], ts[j]))
    print(cn, "done", flush=True)

iv.sort()
ev = []
for a, b in iv:
    ev.append((a, 1)); ev.append((b, -1))
ev.sort()
cur = mx = 0; hist = {}
prev = None; tot_ns = 0; time_at = {}
for t, d in ev:
    if prev is not None and cur > 0:
        time_at[cur] = time_at.get(cur, 0) + (t - prev)
    cur += d; mx = max(mx, cur); prev = t
tt = sum(time_at.values())
halts = sum(1 for a, b in iv
            if (pd.Timestamp(a).tz_localize("UTC").tz_convert("America/New_York").hour < 17
                <= pd.Timestamp(b).tz_localize("UTC").tz_convert("America/New_York").hour)
            or (b - a) > 6 * 3600 * 10**9)
print(f"\n{len(iv):,} trades | max concurrent: {mx}")
for k in sorted(time_at):
    print(f"  {k} open: {time_at[k]/tt*100:5.1f}% of in-position time")
print(f"holds spanning ~5pm halt or >6h: {halts} ({halts/len(iv)*100:.2f}%)")
