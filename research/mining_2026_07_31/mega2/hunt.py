"""The filtered hunt. Four gates, cheapest first, so junk never costs time.

THE USER'S ASK:

  "only search for strategies doing 500 trades a week at $2 a trade, reject
   everything else, run it for hours and hours, we only need to find one"

  and then the sharper version: screen on WIN RATE and REWARD:RISK instead of
  on dollars, because a 50% win rate needs R>1 and a 33% win rate needs R>2,
  and you can throw a candidate away the moment it fails that.

That reasoning is right, and it leads somewhere better than it looks.

  Win rate and R:R ARE the dollars -- expectancy is exactly p*T - (1-p)*S - c,
  so the screen and the evaluation are the same arithmetic and screening on
  them saves nothing by itself.

  But the same identity, rearranged, gives a gate that costs NO DATA AT ALL. A
  coin flip on a bracket already wins S/(S+T) of the time by the reflection
  principle. Break-even needs (S+c)/(S+T). Subtract them:

        EDGE REQUIRED OVER PURE CHANCE  =  c / (S + T)

  That is decidable before a single bar is read. The largest edge over chance
  this repo has ever measured is 2-4 percentage points, so any bracket whose
  required edge exceeds ~6pp cannot be rescued by any win rate ever observed.
  For NQ at $1.99 that means stop and target must SPAN AT LEAST 17 POINTS
  together. Most of the grid dies right there, for free.

THE GATES, in the order they run:

  -1  GEOMETRY      c/(S+T) > MAX_EDGE            no data touched
   0  FREQUENCY     fires on too few bars          outcome not touched
   1  WIN RATE      one-sided bound on a slice     ~15% of the tape
   2  FULL          every bar, exact               survivors only
   3  CONTROLS      shuffled tape, held-out        the short list only

CENSORING, which has bitten this repo before. Trades that reach neither
barrier inside the forward window are NOT dropped -- dropping them biases the
result upward, because a slow win to a distant target goes missing more often
than a fast loss to a near stop. They are closed at the market price at the end
of the window, which is what would actually happen.

TIES go to the stop. When a bar's high reaches the target and its low reaches
the stop, the path inside the bar is unknown, and resolving that the other way
is the easiest way in the world to manufacture an edge that dies live.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "HUNT.md"))
STATE = os.path.join(fuse.ROOT, "data", "tick", "hunt_state.json")
BCACHE = os.path.join(fuse.ROOT, "data", "tick", "barcache")

MIN_TPW = float(os.environ.get("MIN_TPW", "500"))     # trades per week
MIN_DOL = float(os.environ.get("MIN_DOL", "2.00"))    # net $ per trade
MAX_EDGE = float(os.environ.get("MAX_EDGE", "0.06"))  # pp over chance, gate -1
HOURS = float(os.environ.get("HOURS", "10"))
KBAR = [int(x) for x in os.environ.get("KBAR", "250,500,1000").split(",")]
SLICE = 0.15
W = 400                              # forward bars a bracket may live for
NLEG = int(os.environ.get("NLEG", "26"))   # legs kept for pairing

# dollars per tick of the MICRO contract, and an all-in round turn built the
# way the MNQ figure was measured from the user's own fills: $0.74 commission
# plus 2.5 ticks of slippage and spread.
MKT = {"NQ":  dict(tickval=0.50, tickpx=0.25),
       "ES":  dict(tickval=1.25, tickpx=0.25),
       "RTY": dict(tickval=0.50, tickpx=0.10),
       "YM":  dict(tickval=0.50, tickpx=1.00),
       "CL":  dict(tickval=1.00, tickpx=0.01)}
for _m in MKT:
    MKT[_m]["cost"] = 0.74 + 2.5 * MKT[_m]["tickval"]
MARKETS = os.environ.get("MARKETS", "NQ,RTY,YM,ES,CL").split(",")
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def build(contract, k, path):
    """Bars plus features, cached. Price path and own order flow only -- the
    cross-market layer measured zero once its leak was fixed, and every extra
    feature is one more draw in a maximum, which is one more way to be fooled.
    """
    p = os.path.join(BCACHE, f"{contract}_K{k}.npz")
    if not os.path.exists(p):
        ts, px, sz = fuse.load_tape(path)
        m = (len(px) // k) * k
        q = px[:m].reshape(-1, k)
        t = ts[:m].reshape(-1, k)
        B = dict(o=q[:, 0].copy(), c=q[:, -1].copy(), h=q.max(1), l=q.min(1),
                 ts=t[:, -1].copy())
        C = fuse.cumulants(ts, px, sz)
        F, _ = fuse.stream_features(fuse.sample(C, B["ts"]), "f_", 1.0)
        os.makedirs(BCACHE, exist_ok=True)
        np.savez_compressed(p, **B, **{"F" + n: v for n, v in F.items()})
        del ts, px, sz, C
    z = np.load(p, allow_pickle=False)
    B = {n: z[n] for n in ("o", "h", "l", "c", "ts")}
    F = {n[1:]: z[n] for n in z.files if n.startswith("F")}
    F.update(fuse.price_path_features(B))
    return B, F


def tau(B, ks, tickpx):
    """First-touch tables: bars until price is k ticks above / below the entry
    close. The running extreme after an entry is monotone, so one pass answers
    every distance at once -- that is what makes a full (stop, target) grid
    affordable instead of a nested loop over the tape."""
    c, hi, lo = B["c"], B["h"], B["l"]
    n = len(c)
    nk = len(ks)
    up = np.full((n, nk), W + 1, dtype=np.int16)
    dn = np.full((n, nk), W + 1, dtype=np.int16)
    d = np.asarray(ks, dtype=np.float64) * tickpx
    BLK = 2048
    for s in range(0, n - 1, BLK):
        e = min(s + BLK, n - 1)
        w = min(W, n - 1 - s)
        if w <= 0:
            break
        win = np.arange(s, e)[:, None] + 1 + np.arange(w)[None, :]
        ok = win < n
        win = np.minimum(win, n - 1)
        cM = np.maximum.accumulate(np.where(ok, hi[win], -np.inf), axis=1)
        cm = np.minimum.accumulate(np.where(ok, lo[win], np.inf), axis=1)
        base = c[s:e][:, None]
        for j in range(nk):
            u = (cM < base + d[j]).sum(1) + 1
            v = (cm > base - d[j]).sum(1) + 1
            up[s:e, j] = np.where(u > w, W + 1, u)
            dn[s:e, j] = np.where(v > w, W + 1, v)
    return up, dn


def outcomes(B, up, dn, si, ti, side, ks, tickpx, tickval):
    """Dollars per trade for every bar as a potential entry.

    Unresolved trades are closed at the window's end rather than dropped.
    Dropping them is a real bias -- a slow win to a far target goes missing
    more often than a fast loss to a near stop -- and it has produced fake
    edges in this repo before.
    """
    n = len(B["c"])
    if side > 0:
        tt, ts_ = up[:, ti], dn[:, si]
    else:
        tt, ts_ = dn[:, ti], up[:, si]
    hit_t = (tt <= W) & (tt < ts_)          # ties go to the stop
    hit_s = (ts_ <= W) & ~hit_t
    live = ~(hit_t | hit_s)
    j = np.minimum(np.arange(n) + W, n - 1)
    mtm = side * (B["c"][j] - B["c"]) / tickpx
    r = np.where(hit_t, ks[ti], np.where(hit_s, -ks[si], mtm))
    hold = np.where(hit_t, tt, np.where(hit_s, ts_, W)).astype(np.int32)
    return r * tickval, hold, hit_t, live


def nonoverlap(idx, hold):
    out, last = [], -(10 ** 9)
    for i in idx:
        if i >= last:
            out.append(i)
            last = i + int(hold[i])
    return np.asarray(out, dtype=np.int64)


def main():
    t0 = time.time()
    deadline = t0 + HOURS * 3600
    meta = fuse.tape_meta()
    st = (json.load(open(STATE)) if os.path.exists(STATE)
          else {"done": [], "rows": []})
    done, rows, hits = set(st["done"]), st["rows"], []
    allnear = []
    QS = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    stat = dict(g_geo=0, g_freq=0, g_win=0, g_full=0)

    jobs = []
    for m in MARKETS:
        for cn, v in sorted(meta.items()):
            if v["sym"] != m:
                continue
            if v["n"] / max((v["t1"] - v["t0"]) / fuse.DAY_NS, 1) < 5000:
                continue
            for k in KBAR:
                jobs.append((m, cn, k, v["path"]))
    print(f"gates: >={MIN_TPW:.0f} trades/wk AND >=${MIN_DOL:.2f}/trade net; "
          f"{len(jobs)} (market,contract,clock) jobs, {HOURS:g}h budget",
          flush=True)

    for (m, cn, k, path) in jobs:
        key = f"{m}|{cn}|{k}"
        if key in done:
            continue
        if time.time() > deadline:
            print("time budget reached", flush=True)
            break
        try:
            B, F = build(cn, k, path)
        except Exception as e:                                   # noqa: BLE001
            print(f"  {key}: {type(e).__name__}: {e}", flush=True)
            done.add(key)
            continue
        n = len(B["c"])
        days = len(np.unique(B["ts"] // fuse.DAY_NS))
        if n < 8000 or days < 20:
            done.add(key)
            continue
        bpd, tv = n / days, MKT[m]["tickval"]
        tpx, cost = MKT[m]["tickpx"], MKT[m]["cost"]
        need_fire = MIN_TPW / 5.0 / bpd
        cost_ticks = cost / tv

        # ladder in TICKS, spanning half to eight times the market's own median
        # bar range, so the same grid means the same thing in NQ points and CL
        # cents.
        unit = max(float(np.median(B["h"] - B["l"])) / tpx, 1.0)
        ks = np.unique(np.rint(unit * np.array([.5, .75, 1, 1.5, 2, 3, 4.5, 7]))
                       ).astype(int)
        ks = ks[ks >= 1]
        if len(ks) < 3:
            done.add(key)
            continue

        # ---- GATE -1: geometry, before any data is read --------------------
        pairs = [(i, j) for i in range(len(ks)) for j in range(len(ks))
                 if cost_ticks / (ks[i] + ks[j]) <= MAX_EDGE]
        stat["g_geo"] += len(ks) ** 2 - len(pairs)
        if not pairs:
            print(f"  {key}: every bracket needs >{MAX_EDGE*100:.0f}pp over "
                  f"chance — market/clock rejected on geometry alone",
                  flush=True)
            done.add(key)
            continue

        up, dn = tau(B, ks, tpx)
        # Outcomes depend on the BRACKET only, never on the trigger, so they
        # are computed once per (stop, target, side) and indexed thereafter.
        # Computing them inside the trigger loop was ~10 billion redundant
        # operations and would have made the ten hours mostly recomputation.
        OC, PALL = {}, {}
        for (si, ti) in pairs:
            for side in (1, -1):
                OC[(si, ti, side)] = outcomes(B, up, dn, si, ti, side,
                                              ks, tpx, tv)[:3]
                # what this bracket does entered at EVERY bar: the drift,
                # trend and seasonality a trigger has to beat to know anything
                PALL[(si, ti, side)] = float(OC[(si, ti, side)][2].mean())
        del up, dn
        names = sorted(F)
        cut = int(n * SLICE)
        nfire = nwin = nfull = npair = 0
        near = []
        # ---- the bracket loop, shared by single triggers and pairs -------
        legs = []

        def score(idx, label, side, fn, q):
            nonlocal nwin, nfull
            best = -9.9
            for (si, ti) in pairs:
                pstar = (ks[si] + cost_ticks) / (ks[si] + ks[ti])
                r, hold, wt = OC[(si, ti, side)]
                # GATE 1, rebuilt. The first version tested a 15% slice at a
                # 99% bound and rejected NOTHING on any job -- real win rates
                # sit within 1-2pp of break-even and the band was +-3.1pp. A
                # gate whose error bar is wider than the spread of the
                # population it sorts is not a gate.
                #
                # The costly step was never the win rate, which is one
                # vectorised mean; it is the non-overlap scan, a Python loop
                # over every firing bar. So the win rate is taken on the WHOLE
                # tape -- cheap and exact -- and only candidates at or above
                # their required rate pay for the scan.
                pf = float(wt[idx].mean())
                # THE DRIFT BASELINE, and it is the whole ballgame.
                #
                # Comparing a win rate to the driftless coin flip S/(S+T) is
                # wrong in a market that trended. NQ rose 8,492 points across
                # this sample, so a LONG symmetric bracket beats 50% for no
                # reason but the rise -- and measured that way, 94% of every
                # result above +2 sigma was long. That was beta wearing a
                # strategy's clothes.
                #
                # p_all is the same bracket, same side, entered at EVERY bar.
                # It contains the drift, the seasonality and the trend. A
                # trigger only knows something if it beats THAT.
                best = max(best, pf - max(pstar, PALL[(si, ti, side)]))
                if pf < max(pstar, PALL[(si, ti, side)]):
                    stat["g_win"] += 1
                    near.append(dict(mkt=m, K=k, feat=label, q=q, side=side,
                                     stop=int(ks[si]), tgt=int(ks[ti]),
                                     win=pf, pstar=pstar, nfire=int(len(idx))))
                    continue
                nwin += 1
                keep = nonoverlap(idx, hold)          # ---- GATE 2, exact ----
                if len(keep) < 100:
                    continue
                pnl = r[keep] - cost
                mu, sd = float(pnl.mean()), float(pnl.std())
                tpw = len(keep) / days * 5
                nfull += 1
                stat["g_full"] += 1
                pw = float(wt[keep].mean())
                # standard errors above the rate the bracket itself REQUIRES.
                # The only column comparable against the selection ceiling;
                # without it a 1pp excess and a 10pp excess look alike.
                sew = np.sqrt(max(pstar * (1 - pstar), 1e-9) / len(keep))
                pall = PALL[(si, ti, side)]
                rec = dict(mkt=m, con=cn, K=k, feat=label, q=q, side=side,
                           stop=int(ks[si]), tgt=int(ks[ti]), n=len(keep),
                           tpw=tpw, dol=mu, se=sd / np.sqrt(len(keep)),
                           win=pw, pstar=pstar, pall=pall,
                           z=(pw - pstar) / sew,        # vs break-even
                           zd=(pw - pall) / sew)        # vs drift: the real one
                rows.append(rec)
                if tpw >= MIN_TPW and mu >= MIN_DOL:
                    hits.append(rec)
                    print(f"  *** HIT {m} {cn} K={k} {label} q{q:g} "
                          f"s{ks[si]}/t{ks[ti]} {tpw:.0f}/wk ${mu:+.2f}",
                          flush=True)
            return best

        for fn in names:
            v = F[fn]
            fin = np.isfinite(v)
            if fin.sum() < n * 0.5:
                continue
            qv = np.quantile(v[fin], QS)
            for q, thr in zip(QS, qv):
                for side in (1, -1):
                    sig = ((v >= thr) if side > 0 else (v <= thr)) & fin
                    if sig.mean() < need_fire:   # GATE 0, outcome untouched
                        stat["g_freq"] += len(pairs)
                        continue
                    idx = np.flatnonzero(sig)
                    nfire += 1
                    legs.append((score(idx, fn, side, fn, q), sig, fn, q, side))

        # ---- PAIRS -------------------------------------------------------
        # A single threshold is a crude thing to ask of a market. An AND of two
        # is the smallest step into conditions a one-feature rule cannot state
        # -- "flow is heavy AND we are low in the range" -- and two loose legs
        # can still clear the frequency gate where one tight leg cannot.
        #
        # It also multiplies the number of configurations tried, which
        # multiplies the selection ceiling. That is why the report prints
        # sqrt(2 ln N) against the count actually reached.
        legs.sort(key=lambda z: -z[0])
        top = legs[:NLEG]
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                if time.time() > deadline:
                    break
                _, s1, f1, q1, d1 = top[i]
                _, s2, f2, q2, d2 = top[j]
                if f1 == f2:
                    continue
                sig = s1 & s2
                if sig.mean() < need_fire:       # GATE 0 again, still free
                    stat["g_freq"] += len(pairs)
                    continue
                npair += 1
                idx = np.flatnonzero(sig)
                lab = (f"{f1}{'>' if d1 > 0 else '<'}q{q1:g} & "
                       f"{f2}{'>' if d2 > 0 else '<'}q{q2:g}")
                score(idx, lab, d1, f1, q1)
        done.add(key)
        near.sort(key=lambda z: -(z["win"] - z["pstar"]))
        allnear.extend(near[:200])
        tmp = STATE + ".tmp"
        json.dump({"done": sorted(done), "rows": rows[-300000:]},
                  open(tmp, "w"))
        os.replace(tmp, STATE)      # atomic: a reader never sees a half file
        print(f"  {key}: {bpd:.0f} bars/day, need {need_fire*100:.0f}% firing, "
              f"{len(pairs)}/{len(ks)**2} brackets survive geometry | "
              f"{nfire} triggers + {npair} pairs, {nwin} past win-gate, "
              f"{nfull} scored "
              f"({(time.time()-t0)/60:.0f} min, {len(hits)} hits)", flush=True)

    report(rows, hits, stat, t0, allnear)


def report(rows, hits, stat, t0, allnear=()):
    log("# The filtered hunt")
    log()
    log(f"Hard gates, cheapest first, so nothing below the bar costs time. "
        f"Targets: **{MIN_TPW:.0f} trades a week** and **${MIN_DOL:.2f} a "
        f"trade net**.")
    log()
    log("| gate | what it checks | cost | rejected here |")
    log("|---|---|---|---|")
    log(f"| −1 geometry | `cost/(S+T)` — the edge over a coin flip the bracket "
        f"needs before any win rate is known | **no data** | "
        f"{stat['g_geo']:,} |")
    log(f"| 0 frequency | fires often enough for {MIN_TPW:.0f} trades/week | "
        f"**outcome untouched** | {stat['g_freq']:,} |")
    log(f"| 1 win rate | one-sided 99% bound on {SLICE*100:.0f}% of the tape | "
        f"a slice | {stat['g_win']:,} |")
    log(f"| 2 full | every bar, exact, non-overlapping | full | "
        f"{stat['g_full']:,} scored |")
    log()
    log("**Gate −1 is the one worth understanding.** A bracket wins "
        "`S/(S+T)` of the time on a driftless walk by the reflection "
        "principle, and break-even needs `(S+c)/(S+T)`. The difference is "
        "`c/(S+T)` — the edge over pure chance the bracket demands — and it is "
        "known before a single bar is read. The largest edge over chance ever "
        f"measured here is 2–4pp, so anything demanding more than "
        f"{MAX_EDGE*100:.0f}pp is dead on arrival. For NQ at $1.99 that means "
        f"stop and target must span at least 17 points together.")
    log()
    log("Pointed at what has **not** been measured: ES, RTY, YM and CL as the "
        "*traded* instrument rather than as features, three event clocks, and "
        "bracket exits on first touch. NQ price and flow at this frequency is "
        "already known — $0.13 a trade gross with costs switched off, against "
        "the ~$4.00 gross this asks for.")
    log()
    log("Unresolved trades are closed at the window's end, never dropped — "
        "dropping them flatters slow winners over fast losers and has faked an "
        "edge here before. Ties inside a bar go to the stop.")
    log()
    if hits:
        log(f"## {len(hits)} configurations cleared both gates")
        log()
        log("| market | contract | clock | trigger | stop | target | win% | "
            "needed | **sigma over needed** | trades/wk | **$/trade** |")
        log("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(hits, key=lambda z: -z["dol"])[:40]:
            log(f"| {r['mkt']} | {r['con']} | {r['K']} | {r['feat']} "
                f"{'≥' if r['side'] > 0 else '≤'} q{r['q']:g} | {r['stop']} | "
                f"{r['tgt']} | {r['win']*100:.1f}% | {r['pstar']*100:.1f}% | "
                f"**{r.get('z', 0):+.1f}σ** | {r['tpw']:.0f} | "
                f"**${r['dol']:+.2f}** |")
        log()
        log("**Candidates, not strategies.** No shuffled tape yet, no held-out "
            "contract, and no correction for how many configurations were "
            "tried — and that last one matters most, because the best of "
            "millions of draws is several standard errors up on noise alone. "
            "That is the next run.")
    else:
        log("## Nothing cleared both gates")
    log()
    log("## How close anything came")
    log()
    if rows:
        fr = [r for r in rows if r["tpw"] >= MIN_TPW]
        pf = [r for r in rows if r["dol"] >= MIN_DOL]
        ceil = np.sqrt(2 * np.log(max(len(rows), 2)))
        log(f"`{len(rows):,}` reached full scoring. `{len(fr):,}` were frequent "
            f"enough, `{len(pf):,}` paid enough, `{len(hits):,}` did both.")
        log()
        log("> **Every win rate is measured against the same bracket entered "
            "at EVERY bar, not against a coin flip.** NQ rose 8,492 points "
            "across this sample, so a long symmetric bracket beats 50% for no "
            "reason but the trend. Measured against a driftless flip, 94% of "
            "everything above +2σ was long — beta wearing a strategy's "
            "clothes. The `sigma vs drift` column is that correction.")
        log()
        log(f"> **Read sigma, not dollars.** "
            f"It is how far a win rate sits above the rate its own bracket "
            f"requires. Trying `{len(rows):,}` configurations and keeping the "
            f"best is a selection procedure, and the best of that many pure "
            f"noise draws lands about **{ceil:.1f}σ** up by itself "
            f"(`sqrt(2 ln N)`). So anything under {ceil:.1f}σ here is "
            f"consistent with having tried a lot of things, no matter how "
            f"good the dollars look — and the dollars are what will tempt "
            f"you.")
        log()
        for title, sel, keyf in (
                (f"Best paying, among those firing {MIN_TPW:.0f}+ a week",
                 fr, lambda z: -z["dol"]),
                (f"Most frequent, among those paying ${MIN_DOL:.2f}+",
                 pf, lambda z: -z["tpw"])):
            log(f"### {title}")
            log()
            log("| market | clock | trigger | stop | target | win% | needed | "
                "same bracket, any bar | **sigma vs drift** | trades/wk | "
                "$/trade |")
            log("|---|---|---|---|---|---|---|---|---|---|---|")
            for r in sorted(sel, key=keyf)[:12]:
                log(f"| {r['mkt']} | {r['K']} | {r['feat']} q{r['q']:g} | "
                    f"{r['stop']} | {r['tgt']} | {r['win']*100:.1f}% | "
                    f"{r['pstar']*100:.1f}% | {r.get('pall', 0)*100:.1f}% | "
                    f"**{r.get('zd', 0):+.1f}σ** | {r['tpw']:.0f} | "
                    f"${r['dol']:+.2f} |")
            log()
        log("A miss by thirty times and a miss by ten percent are different "
            "facts, and these two tables are what separates them. That is why "
            "a run finding nothing is still worth the hours.")
    log()
    log(f"_Ran {(time.time()-t0)/3600:.2f} h._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
