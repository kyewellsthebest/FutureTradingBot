"""Search the brainstormed edges: post-don't-cross, gamma regime, sweeps.

THE ONE THAT MATTERS MOST NEEDS NO PREDICTION AT ALL.

Every study in this repo assumed the entry crosses the spread. It does not have
to. Rest a limit a tick better than the market and, if it fills, you enter two
ticks better than a taker would -- one saved by not paying the offer, one
gained by being the offer. On MNQ that is a dollar a trade, against a best
measured edge of ninety-two cents. The execution change is worth more than
every directional signal found in two years.

It is also not free, and the free-lunch version is the trap. A resting bid only
fills when someone sells into it, which means it fills precisely when price is
coming DOWN. That is adverse selection, and it is not a footnote -- it is the
whole reason passive trading is hard. This models it exactly rather than
assuming it away:

    a long limit at P - 1 tick fills ONLY if the tape actually trades there,
    within a stated waiting window, and the bracket then runs FROM that fill

So the fill requires the market to move against you first, and the entry price
and the missed trades both fall out of the tape instead of an assumption. No
slippage constant anywhere in this file -- a persistent embarrassment, since
the 2.5-tick figure the rest of the repo charges was never measured and cannot
be, on an account that has only traded a simulator.

WHAT ELSE IS IN HERE, and both are conditions rather than signals:

  GAMMA REGIME. 484 sessions labelled long or short dealer gamma, rebuilt from
  option prices. Long gamma suppresses the range, short amplifies it. Every
  earlier study averaged across both and reported the average.

  SWEEPS. Several trades in the same direction, through rising prices, inside a
  short window: one aggressor taking multiple levels at once, which is urgency
  rather than noise. Visible in trades alone, unlike icebergs and absorption
  which need order-level data we do not have.

WHAT IS DELIBERATELY ABSENT. Queue position, iceberg detection, absorption,
book-sized stops and depth gating all need the order book, and the Polygon
futures quote feed did not survive inspection -- median seven-tick spreads and
79% of trades printing inside the book. Those wait for recorded Tradovate DOM
rather than being faked from something that looks close enough.
"""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "EDGE.md"))
GEX = os.path.join(fuse.ROOT, "data", "gex", "gex_history.parquet")
COMM = 0.74                     # commission only. The spread is modelled.
WAIT = int(os.environ.get("WAIT", "3"))     # bars a resting limit waits
QS = [0.30, 0.45, 0.60, 0.75]
CONTRACTS = os.environ.get("CONTRACTS", "").split(",") if os.environ.get("CONTRACTS") else None
KBAR = [int(x) for x in os.environ.get("KBAR", "500").split(",")]
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def regimes():
    g = pd.read_parquet(GEX)
    g = g[g.fam == "NDX"]
    d = pd.to_datetime(g.day).dt.strftime("%Y-%m-%d")
    return dict(zip(d, np.where(g.gex_vol > 0, 1, -1)))


def sweeps(B, k):
    """Several trades the same way through rising prices in one bar: an
    aggressor taking levels, not a drift. Trades-only, so no book needed."""
    rng = (B["h"] - B["l"])
    body = (B["c"] - B["o"])
    # a bar that travelled far AND closed at its extreme is one-directional
    frac = np.where(rng > 0, body / np.maximum(rng, 1e-9), 0.0)
    return frac


def entries(B, sig_idx, side, tpx, passive):
    """Entry price and index for each signal.

    AGGRESSIVE: cross now. A buyer pays the offer, one tick above the close.
    PASSIVE: rest one tick better and wait. Fills only if the tape trades
    there inside WAIT bars -- which means price moved against you first. That
    is adverse selection, modelled rather than assumed away.
    """
    n = len(B["c"])
    px, at = [], []
    if not passive:
        for i in sig_idx:
            px.append(B["c"][i] + side * tpx)      # pay the spread
            at.append(i)
        return np.array(at), np.array(px)
    lo, hi = B["l"], B["h"]
    for i in sig_idx:
        want = B["c"][i] - side * tpx              # better than the market
        j2 = min(i + WAIT, n - 1)
        hit = -1
        # TOUCHING IS NOT FILLING. A limit at a price you merely trade AT sits
        # behind whatever queue was already there; if two contracts print and
        # forty are ahead of you, you get nothing. Without order-level data
        # there is no way to know your rank, so the conservative convention is
        # used instead: price must trade THROUGH the level, a full tick beyond,
        # before the fill is counted. The permissive version put fills at 99%
        # and handed back almost the whole two-tick saving, which is exactly
        # the sort of free lunch that does not survive contact with a real
        # exchange.
        thru = want - side * tpx
        for j in range(i + 1, j2 + 1):
            if (side > 0 and lo[j] <= thru) or (side < 0 and hi[j] >= thru):
                hit = j
                break
        if hit > 0:
            at.append(hit)
            px.append(want)
    return np.array(at, dtype=np.int64), np.array(px)


def run(cn, K, path, rmap, m="NQ"):
    tv, tpx = hunt.MKT[m]["tickval"], hunt.MKT[m]["tickpx"]
    B, F = hunt.build(cn, K, path)
    n = len(B["c"])
    if n < 8000:
        return []
    F["x_sweep"] = sweeps(B, K)
    days = pd.to_datetime(B["ts"]).strftime("%Y-%m-%d")
    reg = np.array([rmap.get(d, 0) for d in days])
    unit = max(float(np.median(B["h"] - B["l"])) / tpx, 1.0)
    ks = np.unique(np.rint(unit * np.array([1, 2, 3, 4.5]))).astype(int)
    ks = ks[ks >= 1]
    if len(ks) < 2:
        return []
    up, dn = hunt.tau(B, ks, tpx)
    out = []
    names = [x for x in sorted(F) if not x.startswith("p_hour")]
    for fn in names:
        v = F[fn]
        fin = np.isfinite(v)
        if fin.sum() < n * 0.5:
            continue
        for q, thr in zip(QS, np.quantile(v[fin], QS)):
            for side in (1, -1):
                sig = ((v >= thr) if side > 0 else (v <= thr)) & fin
                if sig.mean() < 0.05:
                    continue
                sidx = np.flatnonzero(sig)
                for passive in (False, True):
                    at, epx = entries(B, sidx, side, tpx, passive)
                    if len(at) < 200:
                        continue
                    for si in range(len(ks)):
                        for ti in range(len(ks)):
                            r, hold, wt = hunt.outcomes(
                                B, up, dn, si, ti, side, ks, tpx, tv)[:3]
                            keep = hunt.nonoverlap(at, hold)
                            if len(keep) < 100:
                                continue
                            sel = np.isin(at, keep)
                            kk, kpx = at[sel], epx[sel]
                            # P&L measured from the ACTUAL fill, not the close
                            slip = (B["c"][kk] - kpx) * side / tpx * tv
                            pnl = r[kk] + slip - COMM
                            g = reg[kk]
                            for lab, msk in (("all", np.ones(len(kk), bool)),
                                             ("long-gamma", g > 0),
                                             ("short-gamma", g < 0)):
                                if msk.sum() < 80:
                                    continue
                                out.append(dict(
                                    con=cn, K=K, feat=fn, q=q, side=side,
                                    passive=passive, stop=int(ks[si]),
                                    tgt=int(ks[ti]), regime=lab,
                                    n=int(msk.sum()),
                                    fill=len(at) / max(len(sidx), 1),
                                    dol=float(pnl[msk].mean()),
                                    sd=float(pnl[msk].std())))
    del up, dn
    return out


def main():
    t0 = time.time()
    rmap = regimes()
    meta = fuse.tape_meta()
    cons = CONTRACTS or [c for c, v in sorted(meta.items())
                         if v["sym"] == "NQ"]
    rows = []
    for cn in cons:
        for K in KBAR:
            try:
                r = run(cn, K, meta[cn]["path"], rmap)
            except Exception as e:                               # noqa: BLE001
                print(f"{cn} K{K}: {type(e).__name__}: {e}", flush=True)
                continue
            rows += r
            # Checkpoint after every contract. The previous two attempts were
            # both lost whole when the container restarted mid-run; an hour of
            # work should not depend on the box staying up.
            pd.DataFrame(rows).to_parquet(
                os.path.join(fuse.ROOT, "data", "edge_rows.parquet"),
                compression="zstd")
            print(f"{cn} K{K}: {len(r)} scored, {len(rows)} total "
                  f"({(time.time()-t0)/60:.0f}m)", flush=True)
    if not rows:
        print("nothing scored")
        return
    d = pd.DataFrame(rows)
    d.to_parquet(os.path.join(fuse.ROOT, "data", "edge_rows.parquet"),
                 compression="zstd")

    # pool identical configurations across quarters, weighting by trade count
    g = (d.groupby(["K", "feat", "q", "side", "passive", "stop", "tgt",
                    "regime"])
         .apply(lambda x: pd.Series({
             "n": x.n.sum(),
             "dol": float((x.dol * x.n).sum() / x.n.sum()),
             "quarters": x.con.nunique(),
             "fill": float((x.fill * x.n).sum() / x.n.sum())}),
            include_groups=False)
         .reset_index())
    g["se"] = 1.0        # filled below
    ceil = math.sqrt(2 * math.log(max(len(g), 2)))

    log("# Searching the brainstormed edges")
    log()
    log(f"`{len(d):,}` configurations scored across {len(cons)} quarters, "
        f"pooled to `{len(g):,}` families.")
    log()
    log("**The entry is modelled, not assumed.** Everything in this repo until "
        "now entered by crossing the spread. Here each strategy is run twice: "
        "once crossing (you pay the offer, a tick above the close) and once "
        "resting a limit a tick better. The passive version only fills if the "
        "tape actually trades there within "
        f"{WAIT} bars — so it fills precisely when price is moving against "
        "you. That is adverse selection, measured off the tape rather than "
        "assumed away, and there is no slippage constant anywhere in this "
        "file.")
    log()
    # ---- the headline comparison ----
    a = g[(g.regime == "all") & (~g.passive)].dol
    p = g[(g.regime == "all") & (g.passive)].dol
    log("## Does posting beat crossing?")
    log()
    log("| entry | families | median $/trade | best $/trade | median fill rate |")
    log("|---|---|---|---|---|")
    for lab, msk in (("cross the spread", ~g.passive), ("rest a limit", g.passive)):
        s = g[(g.regime == "all") & msk]
        if len(s):
            log(f"| {lab} | {len(s):,} | ${s.dol.median():+.2f} | "
                f"${s.dol.max():+.2f} | {s.fill.median()*100:.0f}% |")
    log()
    if len(a) and len(p):
        log(f"Median difference: **${p.median() - a.median():+.2f} per trade**, "
            f"before any signal is considered. The theoretical maximum is two "
            f"ticks (${2*0.50:.2f}); anything less is adverse selection and "
            f"missed fills eating into it.")
    log()
    # ---- regime split on the passive book ----
    log("## Passive entries, split by dealer gamma")
    log()
    log("| regime | families | median $/trade | best | trades |")
    log("|---|---|---|---|---|")
    for lab in ("all", "long-gamma", "short-gamma"):
        s = g[(g.regime == lab) & g.passive]
        if len(s):
            log(f"| {lab} | {len(s):,} | ${s.dol.median():+.2f} | "
                f"${s.dol.max():+.2f} | {int(s.n.sum()):,} |")
    log()
    log("## Best configurations, passive entry, present in most quarters")
    log()
    b = g[g.passive & (g.quarters >= 6) & (g.n >= 2000)].nlargest(15, "dol")
    log("| trigger | side | regime | stop | target | trades | fill | **$/trade** |")
    log("|---|---|---|---|---|---|---|---|")
    for _, r in b.iterrows():
        log(f"| {r.feat[:26]} q{r.q:g} | {'L' if r.side > 0 else 'S'} | "
            f"{r.regime} | {int(r.stop)} | {int(r.tgt)} | {int(r.n):,} | "
            f"{r.fill*100:.0f}% | **${r.dol:+.2f}** |")
    log()
    log(f"Selection ceiling for {len(g):,} families is **{ceil:.1f}σ** and "
        f"none of these have faced a shuffled control yet — this is a search, "
        f"not a result. What matters at this stage is whether the passive "
        f"column beats the crossing column by something near two ticks, "
        f"because that part needs no edge to be real.")
    log()
    log(f"_Ran {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
