"""Are prior swing highs/lows ATTRACTORS? Variable structural targets, judged per trade.

Every bracket tested so far used a fixed +T/-S. The user's objection is correct
and it exposes a real gap: a real method does not use a fixed target. It aims
at a LEVEL -- the previous swing high, an unfilled gap, whatever structure is
overhead -- so the distance varies every single trade, and the risk:reward is
an OUTPUT of the geometry rather than an input.

That is not a cosmetic difference, and here is exactly why it matters. On a
random walk, a bracket wins S/(S+T) of the time NO MATTER how T and S were
chosen, as long as they were chosen without seeing the future. So a structural
target beats a fixed one only if LEVELS ARE ATTRACTORS -- if price genuinely
gravitates to prior highs and lows more often than geometry alone predicts.
That is a real, falsifiable claim and it has never been tested here.

THE SETUP (deliberately general, not any one method's rules):
  * a swing confirms, so a new leg is underway in a known direction
  * ENTRY at confirmation
  * STOP at the swing extreme just made -- the classic "recent low" for a long
  * TARGET at the nearest PRIOR swing high above entry that price has not yet
    traded through. Distance varies every trade; R:R varies with it.

THE TEST THAT MAKES IT HONEST. Each trade is compared to ITS OWN geometry, not
to a fixed rate:

    coin-flip rate for this trade = S / (S + T)

Averaged over thousands of trades, `observed hit rate - geometry rate` is the
attraction effect, in percentage points. Zero means levels are just distances
and the structure is decoration. Positive means price really does seek them,
and then the dollars follow.

Also answered, because they are the right questions to ask:
  * what does the R:R distribution actually look like when structure sets it?
  * what fraction of trades are better than 1:1?
  * does dropping the sub-1:1 setups improve the result, or is that just
    dropping the trades that were paying for the others?
  * for the trades that fail, is the failure visible early -- do they break a
    prior level on the way down?

First touch on the real tick path. Held-out contracts only.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DELAY", "1")
import grammar  # noqa: E402

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "LEVELS.md")
PT = 4
USD_PT = 2.00
COST = 1.99
W = int(os.environ.get("W", "20000"))       # forward horizon, price changes
CHUNK = int(os.environ.get("CHUNK", "1500"))
RS = [int(x) for x in os.environ.get("RS", "8,12,20").split(",")]
NTH = [1, 2, 3]                              # 1st, 2nd, 3rd level overhead
TRAIN = set("NQU4,NQZ4,NQH5,NQM5,NQU5".split(","))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


_ZZ = {}


def zigzag(pc, R, key):
    """decompose is a Python loop over millions of prints -- cache per tape."""
    k = (key, R)
    if k not in _ZZ:
        _ZZ[k] = grammar.decompose(pc, R * PT)
    return _ZZ[k]


def build_trades(pc, R, nth, key=""):
    """Entry at confirmation, stop at the swing just made, target the nth
    prior swing extreme in the trade's direction that price is not yet past."""
    piv, conf, dirs = zigzag(pc, R, key)
    if len(piv) < 200:
        return None
    ent_i, stop_p, tgt_p, side = [], [], [], []
    for i in range(len(piv)):
        s = -int(dirs[i])                       # new leg direction: +1 long
        e_i = int(conf[i])
        e_p = float(pc[e_i])
        sp = float(pc[piv[i]])                  # the extreme just made
        if s > 0 and sp >= e_p:
            continue
        if s < 0 and sp <= e_p:
            continue
        # prior extremes of the SAME sign as the trade direction, most recent
        # first: for a long, prior swing HIGHS (completed up-legs, dirs=+1)
        found = []
        for j in range(i - 1, max(-1, i - 120), -1):
            if int(dirs[j]) != s:               # dirs=+1 marks a peak
                continue
            lv = float(pc[piv[j]])
            if s > 0 and lv > e_p:
                found.append(lv)
            elif s < 0 and lv < e_p:
                found.append(lv)
            if len(found) >= nth:
                break
        if len(found) < nth:
            continue
        ent_i.append(e_i); stop_p.append(sp); tgt_p.append(found[nth - 1])
        side.append(s)
    if not ent_i:
        return None
    return (np.array(ent_i, np.int64), np.array(stop_p), np.array(tgt_p),
            np.array(side, np.int64))


def resolve(pc, ent_i, stop_p, tgt_p, side):
    """First touch of target vs stop on the real path."""
    n = len(pc)
    keep = ent_i < n - W - 2
    ent_i, stop_p, tgt_p, side = (ent_i[keep], stop_p[keep], tgt_p[keep],
                                  side[keep])
    win = np.zeros(len(ent_i), bool)
    unres = np.zeros(len(ent_i), bool)
    for c0 in range(0, len(ent_i), CHUNK):
        sl = slice(c0, c0 + CHUNK)
        ii = ent_i[sl]
        fwd = np.lib.stride_tricks.sliding_window_view(pc, W + 1)[ii][:, 1:]
        cmax = np.maximum.accumulate(fwd, axis=1)
        cmin = np.minimum.accumulate(fwd, axis=1)
        s = side[sl]
        up = np.where(s > 0, tgt_p[sl], stop_p[sl])
        dn = np.where(s > 0, stop_p[sl], tgt_p[sl])
        hu = cmax >= up[:, None]
        hd = cmin <= dn[:, None]
        au = np.where(hu.any(1), hu.argmax(1), W + 1)
        ad = np.where(hd.any(1), hd.argmax(1), W + 1)
        first_up = au < ad
        win[sl] = np.where(s > 0, first_up, ~first_up & (ad < W + 1))
        unres[sl] = (au > W) & (ad > W)
        del fwd, cmax, cmin, hu, hd
    return ent_i, stop_p, tgt_p, side, win, unres


tapes = {}
for p in sorted(glob.glob(os.path.join(CACHE, "NQ*_R4.npz"))):
    c = os.path.basename(p).split("_")[0]
    if c in TRAIN:
        continue
    tapes[c] = np.load(p, allow_pickle=False)["pc"].astype(np.int64)

log("# Are prior swing highs and lows actually attractors?")
log()
log("Every bracket tested before this used a fixed target and stop. This does "
    "not: the stop sits at the swing extreme just made and the target sits at "
    "a prior swing high overhead, so the distance — and the risk:reward — is "
    "different on every trade, set by structure rather than chosen.")
log()
log("**Each trade is judged against its own geometry.** On a random walk a "
    "trade wins `S/(S+T)` of the time however T and S were picked, so long as "
    "the future was not consulted. The column `above geometry` is the observed "
    "hit rate minus that per-trade rate, averaged. Zero means levels are just "
    "distances. Positive means price genuinely seeks them.")
log()
log(f"First touch on the real tick path across {len(tapes)} held-out NQ "
    f"contracts, {sum(len(t) for t in tapes.values()):,} price changes.")
log()

for R in RS:
    log(f"## Swing structure at {R} points")
    log()
    log("| target | trades | median R:R | % better than 1:1 | hit rate | "
        "geometry rate | **above geometry** | $/trade gross | net of $1.99 |")
    log("|---|---|---|---|---|---|---|---|---|")
    store = {}
    for nth in NTH:
        W_, Lp, Tp, Sp, Wn, Un = [], [], [], [], [], []
        for c, pc in tapes.items():
            b = build_trades(pc, R, nth, key=c)
            if b is None:
                continue
            e, sp, tp, sd, win, un = resolve(pc, *b)
            risk = np.abs(np.asarray(sp, float) - pc[e]) / PT
            rew = np.abs(np.asarray(tp, float) - pc[e]) / PT
            Lp.append(risk); Tp.append(rew); Wn.append(win); Un.append(un)
        if not Lp:
            continue
        risk = np.concatenate(Lp); rew = np.concatenate(Tp)
        win = np.concatenate(Wn); un = np.concatenate(Un)
        good = (risk > 0) & (rew > 0) & ~un
        risk, rew, win = risk[good], rew[good], win[good]
        if len(risk) < 500:
            continue
        rr = rew / risk
        geo = risk / (risk + rew)
        pnl = np.where(win, rew, -risk) * USD_PT
        store[nth] = (rr, geo, win, pnl, risk, rew)
        log(f"| {nth}{'st' if nth==1 else 'nd' if nth==2 else 'rd'} level | "
            f"{len(rr):,} | {np.median(rr):.2f}:1 | "
            f"{(rr > 1).mean()*100:.0f}% | {win.mean()*100:.2f}% | "
            f"{geo.mean()*100:.2f}% | **{(win.mean()-geo.mean())*100:+.2f} pp** "
            f"| ${pnl.mean():+.3f} | ${pnl.mean()-COST:+.2f} |")
    log()
    if 1 in store:
        rr, geo, win, pnl, risk, rew = store[1]
        log(f"### Filtering by risk:reward — 1st level, {R}-point structure")
        log()
        log("| keep trades with R:R at least | trades kept | hit rate | "
            "geometry rate | above geometry | $/trade | net |")
        log("|---|---|---|---|---|---|---|")
        for thr in (0.0, 0.75, 1.0, 1.5, 2.0, 3.0):
            m = rr >= thr
            if m.sum() < 300:
                continue
            log(f"| {thr:.2f}:1 | {int(m.sum()):,} | {win[m].mean()*100:.2f}% "
                f"| {geo[m].mean()*100:.2f}% | "
                f"**{(win[m].mean()-geo[m].mean())*100:+.2f} pp** | "
                f"${pnl[m].mean():+.3f} | ${pnl[m].mean()-COST:+.2f} |")
        log()
        log("If `above geometry` stays near zero as the filter tightens, then "
            "dropping the low-R:R setups is not improving selection — it is "
            "just changing the shape of the bet, and the hit rate falls to "
            "match exactly as geometry says it must.")
        log()

log("---")
log("Entry at confirmation, stop at the swing extreme just made, target at a "
    "prior swing extreme overhead. First touch resolved on the real tick "
    "sequence. Trades unresolved inside the forward horizon are dropped rather "
    "than guessed. Held-out contracts only.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
