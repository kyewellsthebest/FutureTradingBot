"""Everything at once: every stream, both entry styles, all gates, one search.

WHY THIS FILE EXISTS. Each idea from the brainstorm was tested in its own
script and never together. hunt.py searched NQ price and order flow. edge.py
tested passive entry and sweeps. regime.py tested gamma. Nothing ever combined
them, so a rule that needs "heavy buy flow AND the index complex agreeing AND
a long-gamma session" could not be expressed, let alone found. That combination
is the entire premise -- watching several unrelated streams at once is the one
advantage a bot has that a human cannot copy.

WHAT IS IN THE SEARCH SPACE NOW:

  p_   NQ price path
  f_   NQ order flow -- aggressor side times size
  i_   the index complex, ES/YM/RTY on NQ's clock, wall-clock windows
  m_   the macro complex, CL/GC/HG
  x_   sweeps: one aggressor taking several levels at once
  g_   dealer gamma -- 484 sessions labelled from option prices

  entries        crossing the spread AND resting a limit, scored separately
  exits          brackets on first touch, ties to the stop
  conditions     pairs of the above, so two streams can be required together

FOUR GATES, cheapest first, and the last one is new:

  -1  GEOMETRY    cost/(S+T): the edge over a coin flip the bracket demands,
                  known before any data is read
   0  FREQUENCY   fires often enough for the trades/week target, outcome
                  untouched
   1  WIN RATE    beats the rate the bracket REQUIRES *and* beats what the
                  same bracket earns at random entry
   2  FULL        every bar, exact, non-overlapping

THE RANDOM-ENTRY GATE IS THE ONE THAT MATTERS. NQ rose 8,492 points across this
sample, so a long bracket makes money for no reason whatsoever. Three separate
findings today were exactly that, and each survived until someone thought to
ask what a random entry would have earned. Here it is a gate rather than a
post-mortem: a configuration that cannot beat its own random baseline never
reaches full scoring.

COST is 0.74 commission plus one spread, which is what a taker actually pays.
The 2.5-tick slippage every earlier study charged was an estimate reported as a
measurement -- the account has only traded a simulator, and measuring what
latency costs gave -$0.014 a trade.
"""
import hashlib
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

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "MEGA.md"))
GEX = os.path.join(fuse.ROOT, "data", "gex", "gex_history.parquet")
STATE = os.environ.get("STATE_JSON",
                       os.path.join(fuse.ROOT, "data", "mega_state.json"))
MIN_TPW = float(os.environ.get("MIN_TPW", "500"))
MIN_DOL = float(os.environ.get("MIN_DOL", "2.00"))
MAX_EDGE = float(os.environ.get("MAX_EDGE", "0.06"))
# THE JOINT FILTER. Screening on win rate alone accepts a 92% winner risking
# 554 to make 62, which needs 90.3% just to break even -- one bad run and it is
# gone. Screening on reward:risk alone accepts a 7:1 payoff that wins 7% of the
# time. Neither is a strategy. Both together are: the payoff must be worth
# taking AND the win rate must clear what that payoff demands by a real margin,
# not by a rounding error.
MIN_RR = float(os.environ.get("MIN_RR", "1.0"))      # target / stop
MAX_RR = float(os.environ.get("MAX_RR", "2.5"))
MIN_EDGE_PP = float(os.environ.get("MIN_EDGE_PP", "0.01"))   # over the bar
# HOW FAR ABOVE BREAK-EVEN, as a fraction of the rate the bracket demands.
# The gate above only asked a configuration to beat break-even at all, by a
# single percentage point, which is why the search kept surfacing rules that
# clear the bar and pay nothing. This asks for a MARGIN, and because the
# break-even rate is (S+c)/(S+T) the margin is automatically scaled to the
# R:R -- a wide target needs a lower rate and therefore a lower absolute
# margin, a tight one needs more. One number, correlated to the geometry by
# construction.
#
# At a 52-tick 1:1 bracket break-even is 52.4% and each point above it is
# worth $0.52 a trade, so 0.10 -- ten percent of 52.4%, about 5.2 points --
# is $2.71 a trade, $1,086 a week at 400 trades. That is the target, expressed
# as a property of the strategy rather than a hope about it.
MIN_EDGE_REL = float(os.environ.get("MIN_EDGE_REL", "0.0"))
# SURVIVABILITY, which is a separate question from expectancy and the one that
# actually ends accounts. At 500 trades a week you take 26,000 a year, and the
# longest losing run you should EXPECT is log(n)/log(1/(1-p)). At a 16% win
# rate that is sixty losses back to back -- $966 on a 32-tick stop, a quarter
# of a $4,100 account, gone in one run. At 50% it is fifteen losses and $440.
# Identical expectancy, less than half the damage, and the difference between
# a bot you leave running and one you switch off at the worst moment.
#
# A bracket's required win rate is (S+c)/(S+T), and the achieved rate lands
# within a few points of it, so the band can be enforced at the GEOMETRY gate
# for free -- before any data is touched.
MIN_WIN = float(os.environ.get("MIN_WIN", "0.35"))
MAX_WIN = float(os.environ.get("MAX_WIN", "0.65"))
ACCOUNT = float(os.environ.get("ACCOUNT", "4100"))
MAX_DD_PCT = float(os.environ.get("MAX_DD_PCT", "0.15"))
# a leg firing above this is not a condition, it is the whole tape
MAX_FIRE = float(os.environ.get("MAX_FIRE", "0.90"))
# how far below the gate the cheap crossing screen still bothers looking
PROBE = float(os.environ.get("PROBE", "0.04"))
# come this close to the gate and the sweep stops to dig around the spot
BEEP = float(os.environ.get("BEEP", "0.015"))
DIG_ROUNDS = int(os.environ.get("DIG_ROUNDS", "6"))
HOURS = float(os.environ.get("HOURS", "2"))
KBAR = [int(x) for x in os.environ.get("KBAR", "500").split(",")]
QS = [float(x) for x in os.environ.get("QS", "0.2,0.35,0.5,0.65,0.8").split(",")]
NLEG = int(os.environ.get("NLEG", "34"))
PERTYPE = int(os.environ.get("PERTYPE", "12"))  # legs kept per data type
TRIP = int(os.environ.get("TRIP", "4"))         # legs per type in triples
ARITY = int(os.environ.get("ARITY", "6"))       # widest set of data types
WAIT = 2
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def gamma_features(ts):
    """Dealer gamma as two columns on the bar grid: which regime, and how
    extreme. Rebuilt from option prices, so it costs nothing to keep."""
    if not os.path.exists(GEX):
        return {}
    g = pd.read_parquet(GEX)
    g = g[g.fam == "NDX"].copy()
    g["date"] = pd.to_datetime(g.day).dt.strftime("%Y-%m-%d")
    sign = dict(zip(g.date, np.where(g.gex_vol > 0, 1.0, -1.0)))
    z = (g.gex_vol - g.gex_vol.mean()) / max(g.gex_vol.std(), 1e-9)
    mag = dict(zip(g.date, z))
    d = pd.to_datetime(ts).strftime("%Y-%m-%d")
    return {"g_regime": np.array([sign.get(x, 0.0) for x in d]),
            "g_gex": np.array([mag.get(x, np.nan) for x in d])}


def features(cn, K):
    """Every stream on one clock. fuse.build carries the cross-market layer
    with wall-clock windows; hunt.build carries the bar-based price path and
    order flow. Both, plus sweeps and gamma."""
    B, F, cov = fuse.build(cn, K, verbose=False)
    Bh, Fh = hunt.build(cn, K, fuse.tape_meta()[cn]["path"])
    n = min(len(B["c"]), len(Bh["c"]))
    for k in B:
        B[k] = B[k][:n]
    F = {k: np.asarray(v)[:n] for k, v in F.items()}
    for k, v in Fh.items():
        F.setdefault(k, np.asarray(v)[:n])
    rng = np.maximum(B["h"] - B["l"], 1e-9)
    F["x_sweep"] = (B["c"] - B["o"]) / rng
    F.update({k: v[:n] for k, v in gamma_features(B["ts"]).items()})
    return B, F


def entries(B, idx, side, tpx, passive):
    """Crossing pays the offer. Resting waits for a trade-through, which only
    happens when price kept moving against you -- adverse selection, taken off
    the tape rather than assumed."""
    if not passive:
        return idx, B["c"][idx] + side * tpx
    lo, hi, n = B["l"], B["h"], len(B["c"])
    at, px = [], []
    for i in idx:
        want = B["c"][i] - side * tpx
        thru = want - side * tpx
        for j in range(i + 1, min(i + WAIT, n - 1) + 1):
            if (side > 0 and lo[j] <= thru) or (side < 0 and hi[j] >= thru):
                at.append(j)
                px.append(want)
                break
    return np.array(at, dtype=np.int64), np.array(px)


def combine(cb):
    """AND IS NOT THE ONLY WAY TO COMBINE STREAMS, and treating it as the only
    way is what put the search in a corner. Every added AND condition cuts how
    often the rule fires -- which is exactly why the first pass scored 952
    configurations and not one of them reached 500 trades a week, topping out
    at 241. Demanding more confirmation and demanding more trades pull in
    opposite directions, so stacking to four- and five-way ANDs alone would
    make the frequency problem worse, not better.

    The other combiners do not have that property:

      AND    all legs agree           rarest, most confirmed
      OR     any leg fires            MORE frequent than any single leg, so it
                                      raises trade count instead of cutting it
      k-of-n at least k of n agree    the dial between them -- 2-of-5 fires
                                      often, 4-of-5 rarely, and both use all
                                      five streams at once

    k-of-n is the one that actually resolves the conflict. It reads every data
    type simultaneously, which is the premise, while k tunes frequency to the
    target instead of letting it collapse. "Four of these six streams agree" is
    a genuine six-stream rule that can still trade 500 times a week.
    """
    out = []
    n = len(cb)
    a = cb[0][1].copy()
    for x in cb[1:]:
        a &= x[1]
    out.append(("AND", a))
    o = cb[0][1].copy()
    for x in cb[1:]:
        o |= x[1]
    out.append(("OR", o))
    if n >= 3:
        tot = np.zeros(len(cb[0][1]), dtype=np.int16)
        for x in cb:
            tot += x[1].astype(np.int16)
        for k in range(2, n):            # k=1 is OR, k=n is AND, both above
            out.append((str(k), tot >= k))
    return out


def main():
    t0 = time.time()
    deadline = t0 + HOURS * 3600
    meta = fuse.tape_meta()
    rows, hits, near = [], [], []
    stat = dict(geo=0, freq=0, degen=0, prune=0, drift=0, win=0,
            full=0, dig=0, beeps=0)
    print(f"gates: >={MIN_TPW:.0f} trades/wk AND >=${MIN_DOL:.2f}/trade net, "
          f"beating random entry. budget {HOURS:g}h", flush=True)

    # CLOCK OUTER, CONTRACT INNER. The scan stops on a wall clock, and running
    # every clock for one contract before touching the next means a timeout
    # leaves whole quarters unsearched -- and a result that appears in one
    # quarter is worth nothing, since only 2.4% of families survive into three.
    # This way each bar size gets a complete pass over all eight quarters
    # before the next one starts, so whatever finishes is testable for
    # persistence rather than being a single-quarter curiosity.
    for K in KBAR:
        for cn in fuse.NQ_CONTRACTS:
            if time.time() > deadline:
                break
            try:
                B, F = features(cn, K)
            except Exception as e:                               # noqa: BLE001
                print(f"{cn} K{K}: {type(e).__name__}: {e}", flush=True)
                continue
            n = len(B["c"])
            days = len(np.unique(B["ts"] // fuse.DAY_NS))
            if n < 8000 or days < 20:
                continue
            bpd = n / days
            tv, tpx = hunt.MKT["NQ"]["tickval"], hunt.MKT["NQ"]["tickpx"]
            cost = hunt.MKT["NQ"]["cost"]
            need = MIN_TPW / 5.0 / bpd
            ct = cost / tv
            unit = max(float(np.median(B["h"] - B["l"])) / tpx, 1.0)
            ks = np.unique(np.rint(unit * np.array([.5, 1, 1.5, 2, 3, 4.5, 7]))
                           ).astype(int)
            ks = ks[ks >= 1]
            def keep_bracket(i, j):
                S, T = ks[i], ks[j]
                if ct / (S + T) > MAX_EDGE:
                    return False
                if not (MIN_RR <= T / S <= MAX_RR):
                    return False
                need = (S + ct) / (S + T)
                if not (MIN_WIN <= need <= MAX_WIN):
                    return False
                # expected worst losing run over a year at this frequency,
                # priced against the account
                n = MIN_TPW * 52
                run = math.log(n) / math.log(1 / max(1 - need, 1e-9))
                return run * S * tv <= MAX_DD_PCT * ACCOUNT
            pairs = [(i, j) for i in range(len(ks)) for j in range(len(ks))
                     if keep_bracket(i, j)]
            stat["geo"] += len(ks) ** 2 - len(pairs)
            if not pairs:
                continue
            up, dn = hunt.tau(B, ks, tpx)
            OC, PALL = {}, {}
            for (si, ti) in pairs:
                for side in (1, -1):
                    o = hunt.outcomes(B, up, dn, si, ti, side, ks, tpx, tv)[:3]
                    OC[(si, ti, side)] = o
                    PALL[(si, ti, side)] = float(o[2].mean())
            del up, dn

            legs, nf = [], 0
            names = sorted(F)

            FV = {}

            def mkleg(fn, q, side):
                """A leg at an arbitrary quantile, so the dig can step off the
                coarse grid the sweep uses."""
                if not (0.02 <= q <= 0.98):
                    return None
                v = FV.get(fn)
                if v is None:
                    v = np.asarray(F[fn], dtype=np.float64)
                    FV[fn] = v
                fin = np.isfinite(v)
                if fin.sum() < len(v) * 0.5:
                    return None
                thr = float(np.quantile(v[fin], q))
                sig = ((v >= thr) if side > 0 else (v <= thr)) & fin
                m = sig.mean()
                if m < need or m > MAX_FIRE:
                    return None
                return (0.0, sig, fn, round(q, 3), side)

            def score(idx0, label, side, q):
                """Cheap screen first, full work only where the screen beeps.

                THE OLD LOOP RECOMPUTED THE SAME THING FORTY TIMES. entries()
                depends on the signal, the side and the entry style -- and NOT
                on the bracket -- but it was called inside the bracket loop, so
                its Python for-loop over every signal bar ran once per bracket
                per entry style. That was most of the runtime, spent
                recalculating an identical answer.

                It is now hoisted out. And before any of it runs, every bracket
                is screened with crossing only, which is pure numpy: for a
                crossing entry `entries` returns the signal indices unchanged,
                so wt[idx0].mean() is the exact win rate, not an approximation.
                If no bracket comes within PROBE of the gate on that screen,
                the whole configuration is dropped without a single Python
                loop. Dead ground gets walked over, not dug."""
                nonlocal nf
                best = -9.9
                live = []
                for (si, ti) in pairs:
                    wt = OC[(si, ti, side)][2]
                    pstar = (ks[si] + ct) / (ks[si] + ks[ti])
                    pall = PALL[(si, ti, side)]
                    bar = max(pstar * (1.0 + MIN_EDGE_REL), pall + MIN_EDGE_PP)
                    e = float(wt[idx0].mean()) - bar
                    if e > best:
                        best = e
                    if e >= -PROBE:
                        live.append((si, ti))
                if not live:
                    stat["prune"] += len(pairs) * 2
                    return best

                AT = {pv: entries(B, idx0, side, tpx, pv)
                      for pv in (False, True)}
                for (si, ti) in live:
                    r, hold, wt = OC[(si, ti, side)]
                    pstar = (ks[si] + ct) / (ks[si] + ks[ti])
                    pall = PALL[(si, ti, side)]
                    bar = max(pstar * (1.0 + MIN_EDGE_REL), pall + MIN_EDGE_PP)
                    for passive in (False, True):
                        at, epx = AT[passive]
                        if len(at) < 200:
                            continue
                        pf = float(wt[at].mean())
                        best = max(best, pf - bar)
                        if pf < pstar * (1.0 + MIN_EDGE_REL):
                            stat["win"] += 1
                            continue
                        if pf < pall + MIN_EDGE_PP:
                            stat["drift"] += 1
                            near.append((pf - pall, label, "drift"))
                            continue
                        keep = hunt.nonoverlap(at, hold)
                        if len(keep) < 100:
                            continue
                        sel = np.isin(at, keep)
                        kk = at[sel]
                        gain = 2.0 * tv if passive else 0.0
                        pnl = r[kk] + gain - cost
                        mu = float(pnl.mean())
                        pf2 = float(wt[kk].mean())
                        tpw = len(kk) / days * 5
                        nf += 1
                        stat["full"] += 1
                        sew = math.sqrt(max(pall * (1 - pall), 1e-9) / len(kk))
                        rec = dict(con=cn, K=K, feat=label, q=q, side=side,
                                   passive=passive, stop=int(ks[si]),
                                   tgt=int(ks[ti]), n=len(kk), tpw=tpw,
                                   dol=mu, wk=mu * tpw, win=pf2, pstar=pstar,
                                   pall=pall, zd=(pf2 - pall) / sew,
                                   rr=ks[ti] / ks[si],
                                   dd=(math.log(max(tpw, 1) * 52) /
                                       math.log(1 / max(1 - pf2, 1e-9))
                                       * ks[si] * tv))
                        rows.append(rec)
                        if tpw >= MIN_TPW and mu >= MIN_DOL:
                            hits.append(rec)
                            print(f"  *** HIT {label[:40]} {tpw:.0f}/wk "
                                  f"${mu:+.2f} ${mu*tpw:+,.0f}/wk "
                                  f"{rec['zd']:+.1f}s", flush=True)
                return best

            def dig(cb0, e0):
                """The detector beeped -- stop sweeping and work this spot.

                A uniform sweep gives the same effort to barren ground and to
                the one patch that reads hot, which is the wrong allocation
                when the grid is coarse. The quantiles the sweep uses are five
                fixed values; the real boundary of anything worth having will
                sit between them. So when a configuration comes within BEEP of
                the gate, hill-climb around it: nudge each leg's threshold off
                the grid, flip a leg's direction, drop a leg, add one from a
                type not yet present -- score every neighbour under every
                combiner, take the best, and repeat while it keeps improving.

                Bounded by DIG_ROUNDS and by the same wall clock as everything
                else, so a hot spot cannot eat the run."""
                cur, cure = list(cb0), e0
                for _ in range(DIG_ROUNDS):
                    cands = []
                    for i in range(len(cur)):
                        fn, qq, sd = cur[i][2], cur[i][3], cur[i][4]
                        for dq in (-0.10, -0.05, -0.02, 0.02, 0.05, 0.10):
                            lg = mkleg(fn, qq + dq, sd)
                            if lg:
                                nb = list(cur); nb[i] = lg; cands.append(nb)
                        lg = mkleg(fn, qq, -sd)
                        if lg:
                            nb = list(cur); nb[i] = lg; cands.append(nb)
                        if len(cur) > 2:
                            cands.append([x for j, x in enumerate(cur)
                                          if j != i])
                    have = {x[2].split("_")[0] + "_" for x in cur}
                    for t in types:
                        if t in have:
                            continue
                        for a in byt[t][:2]:
                            cands.append(list(cur) + [a])

                    bestnb, beste = None, cure
                    for nb in cands:
                        if time.time() > deadline:
                            return cure
                        fs = tuple(x[2] for x in nb)
                        if len(set(fs)) < len(fs):
                            continue
                        for m2, sg in combine(nb):
                            fr = sg.mean()
                            if fr < need or fr > MAX_FIRE:
                                continue
                            h = hashlib.blake2b(np.packbits(sg).tobytes(),
                                                digest_size=16).digest()
                            if h in seen:
                                continue
                            seen.add(h)
                            stat["dig"] += 1
                            body = ",".join(
                                f"{x[2]}{'>' if x[4] > 0 else '<'}{x[3]:g}"
                                for x in nb)
                            lab = (body.replace(",", "&") if m2 == "AND" else
                                   body.replace(",", "|") if m2 == "OR" else
                                   f"{m2}of({body})")
                            e = score(np.flatnonzero(sg), "DIG " + lab,
                                      nb[0][4], nb[0][3])
                            if e > beste:
                                bestnb, beste = nb, e
                    if bestnb is None:
                        break
                    cur, cure = bestnb, beste
                    print(f"    dig -> edge {cure:+.4f} "
                          f"({len(cur)} legs)", flush=True)
                return cure

            for fn in names:
                v = np.asarray(F[fn], dtype=np.float64)
                fin = np.isfinite(v)
                if fin.sum() < n * 0.5:
                    continue
                # A CONDITION THAT IS ALWAYS TRUE IS NOT A CONDITION, and the
                # first pass was full of them. g_regime is a binary +-1 label,
                # so thresholding it at five quantiles gives the same all-true
                # mask five times over -- which is why
                # "f_wcofi120<0.2 & g_regime<0.35 & x_sweep<0.8" scored to the
                # cent identically to the same rule at <0.5, <0.65 and <0.8,
                # and identically to the plain pair without gamma at all. Four
                # duplicate "triples" that added no constraint, ate the
                # deadline, and each counted as another draw against the
                # selection ceiling.
                #
                # Legs are now dropped when they fire almost always, and
                # deduplicated on the SIGNAL itself rather than on the
                # (feature, quantile, direction) label -- two labels that
                # select the same bars are one leg however different they look.
                seen_sig = set()
                for q, thr in zip(QS, np.quantile(v[fin], QS)):
                    for side in (1, -1):
                        sig = ((v >= thr) if side > 0 else (v <= thr)) & fin
                        if sig.mean() < need:
                            stat["freq"] += len(pairs) * 2
                            continue
                        if sig.mean() > MAX_FIRE:
                            stat["degen"] += 1
                            continue
                        h = hashlib.blake2b(np.packbits(sig).tobytes(),
                                            digest_size=16).digest()
                        if h in seen_sig:
                            stat["degen"] += 1
                            continue
                        seen_sig.add(h)
                        i0 = np.flatnonzero(sig)
                        legs.append((score(i0, fn, side, q), sig, fn, q, side))

            # COMBINATIONS, STRATIFIED BY DATA TYPE.
            #
            # The previous version ranked every leg together and paired the top
            # thirty. Those were nearly all price features, so the "pairs" were
            # price x price -- p_chop55 & p_pos55, f_wcofi600 & f_ofi21 -- and
            # the cross-type combinations that are the entire point of carrying
            # six data streams were never tested.
            #
            # So legs are bucketed by type and combinations are generated
            # ACROSS buckets by construction: every type against every other
            # type, then triples spanning three distinct types. A price
            # condition AND an index-complex condition AND a long-gamma session
            # is now expressible, which is the claim being tested.
            import itertools
            byt = {}
            for lg in legs:
                t = lg[2].split("_")[0] + "_"
                byt.setdefault(t, []).append(lg)
            for t in byt:
                byt[t].sort(key=lambda z: -z[0])
                byt[t] = byt[t][:PERTYPE]
            types = sorted(byt)
            print(f"    legs by type: "
                  + ", ".join(f"{t}{len(byt[t])}" for t in types), flush=True)

            # ARITY, and it goes past pairs and triples. For an AND the ORDER
            # of the legs is meaningless -- C+B+D and B+C+D select the same
            # bars -- so what adds coverage is not permuting the letters, it is
            # taking MORE of them at once: every 2-, 3-, 4-, 5- and 6-way set
            # of distinct data types, up to ARITY. WIDE[m] is how many legs per
            # type feed an m-way set, and it has to shrink as m grows or the
            # count explodes (6 types choose 4, at 12 legs each, is 311,040).
            WIDE = {2: PERTYPE, 3: 6, 4: 4, 5: 3, 6: 3}
            groups, seen = [], set()
            for t in types:                                      # A+A within
                groups.append(list(itertools.combinations(byt[t][:8], 2)))
            for m in range(2, min(ARITY, len(types)) + 1):
                w = WIDE.get(m, 2)
                for ts in itertools.combinations(types, m):
                    groups.append([tuple(c) for c in itertools.product(
                        *[byt[t][:w] for t in ts])])
            # ROUND-ROBIN, not group-by-group. The scan stops on a wall clock,
            # and walking the groups in order means a timeout leaves the last
            # type pairs entirely untested while the alphabetically-first ones
            # are exhausted. Interleaving makes the cut uniform: whatever the
            # deadline allows is a fair sample of every cross-type pairing
            # rather than all of some and none of others.
            combos = [c for tier in itertools.zip_longest(*groups)
                      for c in tier if c is not None]
            print(f"    {len(combos):,} combinations across {len(groups)} "
                  f"type-groups ({len(types)} types)", flush=True)

            for cb in combos:
                if time.time() > deadline:
                    break
                fs = tuple(x[2] for x in cb)
                if len(set(fs)) < len(fs):
                    continue
                # Dedup on the FULL leg identity. Keying on feature names alone
                # would collapse "chop above its 20th pct AND NDX below its
                # 80th" into "chop above its 80th AND NDX above its 20th" --
                # opposite conditions, one surviving arbitrarily. The threshold
                # and the direction are the condition; the name is only where
                # it came from.
                key = tuple(sorted((x[2], x[3], x[4]) for x in cb))
                if key in seen:
                    continue
                seen.add(key)
                for mode, sig in combine(cb):
                    if time.time() > deadline:
                        break
                    fire = sig.mean()
                    if fire < need:
                        stat["freq"] += len(pairs) * 2
                        continue
                    # AND the other end, which only became reachable once OR
                    # and low-k joined the search. "Any one of six streams
                    # fires" is true on almost every bar -- that is not a
                    # signal, it is a description of the tape wearing six
                    # labels. Without this bound the OR modes would flood the
                    # expensive scorer with rules that trade constantly and
                    # select nothing.
                    if fire > MAX_FIRE:
                        stat["degen"] += 1
                        continue
                    # and again at the combination level: if adding a third leg
                    # selects exactly the bars the pair already selected, it is
                    # the pair. Scoring it a second time would be one more draw
                    # against the ceiling in exchange for nothing.
                    hc = hashlib.blake2b(np.packbits(sig).tobytes(),
                                         digest_size=16).digest()
                    if hc in seen:
                        stat["degen"] += 1
                        continue
                    seen.add(hc)
                    body = ",".join(f"{x[2]}{'>' if x[4] > 0 else '<'}{x[3]:g}"
                                    for x in cb)
                    lab = (body.replace(",", "&") if mode == "AND" else
                           body.replace(",", "|") if mode == "OR" else
                           f"{mode}of({body})")
                    e = score(np.flatnonzero(sig), lab, cb[0][4], cb[0][3])
                    # THE BEEP. Everything above walks the ground quickly and
                    # throws away whatever cannot clear the gate. This is the
                    # other half: when something reads hot, stop sweeping and
                    # work the spot properly before moving on.
                    if e >= -BEEP:
                        stat["beeps"] += 1
                        print(f"  beep {e:+.4f}  {lab[:60]}", flush=True)
                        dig(cb, e)

            json.dump({"rows": rows[-200000:]}, open(STATE, "w"))
            print(f"{cn} K{K}: {bpd:.0f} bars/day, need {need*100:.0f}% firing, "
                  f"{len(legs)} legs, {nf} scored, {len(hits)} hits "
                  f"({(time.time()-t0)/60:.0f}m)", flush=True)

    # ---------------------------------------------------------------- report
    d = pd.DataFrame(rows)
    ceil = math.sqrt(2 * math.log(max(len(d), 2)))
    log("# Every stream, both entry styles, one search")
    log()
    log("Each idea was previously tested in its own script and never together. "
        "`hunt.py` searched NQ price and flow, `edge.py` tested passive entry "
        "and sweeps, `regime.py` tested gamma. So a rule needing *heavy buy "
        "flow AND the index complex agreeing AND a long-gamma session* could "
        "not be expressed, let alone found — which is the entire premise, "
        "since watching several unrelated streams at once is the one advantage "
        "a bot has that a human cannot copy.")
    log()
    log(f"Streams: NQ price, NQ order flow, the index complex (ES/YM/RTY), the "
        f"macro complex (CL/GC/HG), sweeps, and dealer gamma over 484 labelled "
        f"sessions. Entries scored **both** crossing and resting a limit. "
        f"Cost **${hunt.MKT['NQ']['cost']:.2f}** — commission plus one spread, "
        f"which is what a taker actually pays.")
    log()
    log("| gate | rejected |")
    log("|---|---|")
    log(f"| −1 geometry, before any data | {stat['geo']:,} |")
    log(f"| 0 frequency, outcome untouched | {stat['freq']:,} |")
    log(f"| 0b **degenerate — always true, or a duplicate mask** | {stat['degen']:,} |")
    log(f"| 0c dropped by the cheap crossing screen | {stat['prune']:,} |")
    log(f"| 1 win rate below break-even × {1+MIN_EDGE_REL:.2f} "
        f"| {stat['win']:,} |")
    log(f"| 1b **below what RANDOM ENTRY earns** | {stat['drift']:,} |")
    log(f"| 2 fully scored | {stat['full']:,} |")
    log()
    log(f"**{stat['beeps']:,} beeps, {stat['dig']:,} neighbours dug.** The "
        f"sweep drops anything the cheap screen says cannot clear the gate — "
        f"no Python loop, no bracket scan — and spends what it saves "
        f"hill-climbing around whatever reads hot: thresholds nudged off the "
        f"coarse grid, legs flipped, dropped and added, every combiner "
        f"retried, repeating while it improves.")
    log()
    log("**Gate 1b is the one that matters.** NQ rose 8,492 points across this "
        "sample, so a long bracket makes money for no reason at all. Three "
        "separate findings today were exactly that, each surviving until "
        "someone asked what a random entry would have earned. Here it is a "
        "gate rather than a post-mortem.")
    log()
    if len(d) == 0:
        log("Nothing reached full scoring.")
    else:
        log(f"`{len(d):,}` scored. `{int((d.tpw >= MIN_TPW).sum()):,}` frequent "
            f"enough, `{int((d.dol >= MIN_DOL).sum()):,}` paid enough, "
            f"**`{len(hits)}` did both.** Selection ceiling "
            f"**{ceil:.1f}σ**.")
        log()
        for title, sel in ((f"Cleared both gates", d[(d.tpw >= MIN_TPW) &
                                                     (d.dol >= MIN_DOL)]),
                           (f"Best $/week among {MIN_TPW:.0f}+ trades/week",
                            d[d.tpw >= MIN_TPW].nlargest(12, "wk")),
                           ("Highest sigma over random entry, any frequency",
                            d.nlargest(12, "zd"))):
            if not len(sel):
                continue
            log(f"### {title}")
            log()
            log("| trigger | entry | R:R | win% | random | **σ vs random** | "
                "tr/wk | $/trade | **$/week** | worst run $ |")
            log("|---|---|---|---|---|---|---|---|---|---|")
            for _, r in sel.iterrows():
                log(f"| {r.feat[:32]} q{r.q:g} | "
                    f"{'post' if r.passive else 'cross'} | "
                    f"{r.get('rr', 0):.1f}:1 | {r.win*100:.1f}% | "
                    f"{r.pall*100:.1f}% | **{r.zd:+.1f}σ** | {r.tpw:.0f} | "
                    f"${r.dol:+.2f} | **${r.wk:+,.0f}** | "
                    f"${r.get('dd', 0):,.0f} |")
            log()
    log(f"_Ran {(time.time()-t0)/3600:.2f} h._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
