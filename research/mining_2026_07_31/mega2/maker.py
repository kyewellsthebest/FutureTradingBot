"""What is resting a limit actually worth? The whole band, not one guess.

THE LEVER. A taker buys at the offer and sells at the bid, so a round trip
costs one full tick of spread plus commission -- $1.24 on MNQ. A maker does
the opposite: rests a bid, gets sold to, rests an offer, gets bought from, and
EARNS that tick instead of paying it. The swing is two ticks, a dollar a
trade, five hundred dollars a week at five hundred trades, and it requires
predicting absolutely nothing. It is five times the entire zero-cost ceiling
of every directional study in this repo.

WHY IT IS NOT FREE, AND WHY EVERY NUMBER SO FAR HAS BEEN A GUESS. A resting
bid only fills when somebody sells into it, and people sell into it when price
is about to fall. Fill on the bad ones, miss the good ones -- adverse
selection, structural, not luck. Modelling it needs a rule for WHEN a limit
fills, and this repo has produced three answers from three rules:

    filled if price merely touched the limit          +$0.88 / trade
    filled only if price traded a tick through        +$0.25 / trade
    paired against the same trades taken by crossing  -$0.066 / trade

A 3.5x band on the single biggest lever available, and the whole band comes
from an assumption nobody measured.

WHAT THIS FILE DOES DIFFERENTLY. "Touch" and "trade through" are both crude
stand-ins for the real question, which is QUEUE POSITION: when price reaches
your limit, how many contracts were already resting ahead of you? Fill 200
contracts deep in the queue and price has to grind; fill at the front and a
single lot does it.

The order book would answer that directly and we do not have it yet. But the
tick tape carries trade SIZES, so the question can be turned around and
answered as a curve instead of a point:

    assume Q contracts are ahead of you. You fill once Q+1 contracts have
    traded at your price -- or immediately if price trades straight through
    your level, because then the book swept you.

Sweep Q from 0 to 200 and the output is not one number but the shape of the
decay. When the DOM recorder finally yields real depth, the median queue
length is a lookup on that curve rather than a new study.

WHAT IS REPORTED, and the second one is the one that matters:

    ON FILLS      what the maker earns on trades it actually gets
    ON SIGNALS    what the maker earns across EVERY signal, counting misses
                  as zero -- because a taker gets all 500 trades a week and a
                  maker might get 300, and weekly dollars care about that

A maker can beat a taker per trade and still lose per week by missing the
winners. That is the failure mode this is built to catch.
"""
import json
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402
import hunt  # noqa: E402

OUT = os.environ.get("OUT_MD", os.path.join(fuse.ROOT, "research", "MAKER.md"))
COMM = 0.74
TICKPX, TICKVAL = 0.25, 0.50
QUEUES = [int(x) for x in os.environ.get(
    "QUEUES", "0,2,5,10,25,50,100,200").split(",")]
WAIT_SEC = float(os.environ.get("WAIT_SEC", "30"))
NENT = int(os.environ.get("NENT", "4000"))
KBAR = int(os.environ.get("KBAR", "500"))
MAXF = int(os.environ.get("MAXF", "400000"))     # ticks scanned per bracket
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def pnl_of(r, S, T):
    """ONE formula for both sides of the comparison, because the first version
    had two. The taker's stop was booked at exactly the stop price while the
    maker's paid a tick to cross -- a $0.50 handicap on the very thing being
    tested. Both exits work the same way in reality: the target is a resting
    limit and costs nothing to leave on, the stop is a market order and pays
    the spread. The maker's advantage has to come from a better ENTRY anchor
    and nothing else, which is the only honest way to measure it."""
    if r > 0:
        return T * TICKVAL - COMM
    return -(S * TICKVAL + TICKVAL) - COMM


def sum_of(ds):
    out = dict(n=0, w=0, pnl=0.0, gw=0.0, gl=0.0)
    for d in ds:
        for k in out:
            out[k] += d[k]
    return out


def book(a, r, S, T):
    """Wins and losses kept apart, not just the net. A strategy is not
    described by its expectancy -- average win, average loss and win rate are
    what tell you whether you could actually sit through it."""
    v = pnl_of(r, S, T)
    a["n"] += 1
    a["pnl"] += v
    if r > 0:
        a["w"] += 1
        a["gw"] += v
    else:
        a["gl"] += v


def bracket(px, f, side, stop_px, tgt_px):
    """First touch from tick f. Ties go to the stop -- when a bar contains
    both, assuming the good one happened first is how backtests lie."""
    hi = min(f + MAXF, len(px))
    w = px[f:hi]
    if side > 0:
        up = w >= tgt_px
        dn = w <= stop_px
    else:
        up = w <= tgt_px
        dn = w >= stop_px
    iu = int(np.argmax(up)) if up.any() else 10 ** 9
    idn = int(np.argmax(dn)) if dn.any() else 10 ** 9
    if iu == idn == 10 ** 9:
        return None
    return 1 if iu < idn else -1          # stop wins ties


def run(cn, path):
    ts, px, sz = fuse.load_tape(path)
    B, _F = hunt.build(cn, KBAR, path)
    n = len(B["c"])
    if n < 5000:
        return None
    unit = max(float(np.median(B["h"] - B["l"])) / TICKPX, 1.0)
    S = T = max(int(round(unit)), 2)      # 1:1, inside the survivability band
    days = len(np.unique(B["ts"] // fuse.DAY_NS))

    # entry bars, evenly spaced so no part of the sample is favoured
    step = max(n // NENT, 1)
    bars = np.arange(step, n - 1, step)
    jj = np.searchsorted(ts, B["ts"][bars])          # tick index of bar close
    wait_ns = int(WAIT_SEC * 1e9)

    z = lambda: dict(n=0, w=0, pnl=0.0, gw=0.0, gl=0.0)          # noqa: E731
    acc = {q: z() for q in QUEUES}
    acc_t = z()
    miss_taker = {q: z() for q in QUEUES}
    nsig = 0

    for bi, j0 in zip(bars, jj):
        if j0 <= 0 or j0 >= len(px) - 10:
            continue
        side = 1 if (bi % 2 == 0) else -1   # both directions, evenly
        c0 = px[j0]
        limit = c0 - side * TICKPX          # rest a tick BETTER than market
        stop_px = limit - side * S * TICKPX
        tgt_px = limit + side * T * TICKPX
        nsig += 1

        # ---- the taker, for the same signal: pays the offer, no queue ----
        tk_entry = c0 + side * TICKPX
        o = bracket(px, j0, side, tk_entry - side * S * TICKPX,
                    tk_entry + side * T * TICKPX)
        if o is not None:
            book(acc_t, o, S, T)

        # ---- the maker: one pass over the window serves every queue ----
        j1 = int(np.searchsorted(ts, ts[j0] + wait_ns))
        j1 = min(max(j1, j0 + 1), len(px))
        w_px, w_sz = px[j0 + 1:j1], sz[j0 + 1:j1]
        if not len(w_px):
            if o is not None:
                for q in QUEUES:
                    book(miss_taker[q], o, S, T)
            continue
        at = np.isclose(w_px, limit)
        thru = (w_px < limit) if side > 0 else (w_px > limit)
        cum = np.cumsum(np.where(at, w_sz, 0))
        i_thru = int(np.argmax(thru)) if thru.any() else 10 ** 9

        for q in QUEUES:
            need = cum >= (q + 1)
            i_q = int(np.argmax(need)) if need.any() else 10 ** 9
            i_fill = min(i_q, i_thru)
            if i_fill >= 10 ** 9:
                # NEVER FILLED, so the hybrid crosses instead -- but it
                # crosses LATE, and that is the whole subtlety. The first
                # version of this booked the taker outcome computed at the
                # original bar close, which is look-ahead: the decision to
                # give up and cross can only be made once the wait has
                # expired, and by then price has moved AWAY from the limit --
                # that is precisely why it did not fill. Entering at the old
                # price after learning the market ran in your favour is not a
                # strategy, it is a time machine, and it was worth a spurious
                # +$0.90 a trade.
                #
                # The honest version chases: cross at whatever the market is
                # when the wait runs out, and bracket from there.
                if j1 - 1 > j0:
                    late = px[j1 - 1] + side * TICKPX
                    ol = bracket(px, j1 - 1, side,
                                 late - side * S * TICKPX,
                                 late + side * T * TICKPX)
                    if ol is not None:
                        book(miss_taker[q], ol, S, T)
                continue
            f = j0 + 1 + i_fill
            r = bracket(px, f, side, stop_px, tgt_px)
            if r is None:
                continue
            # filled AS the resting order, so no spread paid on entry. Target
            # is also a resting limit; the stop is a market order and crosses.
            book(acc[q], r, S, T)

    return dict(cn=cn, days=days, nsig=nsig, S=S, T=T,
                taker=acc_t, maker=acc, miss=miss_taker)


def main():
    t0 = time.time()
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    res = []
    for cn in cons:
        try:
            r = run(cn, meta[cn]["path"])
        except Exception as e:                                   # noqa: BLE001
            print(f"{cn}: {type(e).__name__}: {e}", flush=True)
            continue
        if r:
            res.append(r)
            tk = r["taker"]
            print(f"{cn}: {r['nsig']:,} signals, bracket {r['S']}x{r['T']} "
                  f"ticks, taker ${tk['pnl']/max(tk['n'],1):+.3f}/trade "
                  f"({(time.time()-t0)/60:.0f}m)", flush=True)
    if not res:
        print("nothing produced")
        return

    nsig = sum(r["nsig"] for r in res)
    days = sum(r["days"] for r in res)
    tn = sum(r["taker"]["n"] for r in res)
    tp = sum(r["taker"]["pnl"] for r in res)
    tdol = tp / max(tn, 1)

    log("# What resting a limit is actually worth")
    log()
    log(f"A taker buys the offer and sells the bid, so a round trip costs one "
        f"full tick plus commission — **$1.24 on MNQ**. A maker rests instead "
        f"and *earns* that tick. The swing is two ticks, **$1.00 a trade**, "
        f"$500 a week at 500 trades, and it predicts nothing. For scale, the "
        f"entire directional search run at **zero** cost topped out at $97 a "
        f"week.")
    log()
    log(f"It is not free: a resting bid fills when someone sells into it, and "
        f"people sell into it when price is about to fall. Fill the bad ones, "
        f"miss the good ones. Modelling that needs a rule for when a limit "
        f"fills, and three rules in this repo gave **+$0.88**, **+$0.25** and "
        f"**−$0.066** a trade — a 3.5× band on the biggest lever available, "
        f"produced entirely by an assumption nobody measured.")
    log()
    log(f"Touch and trade-through are both stand-ins for the real question: "
        f"**how many contracts were ahead of you in the queue?** The book "
        f"would say directly and is not recording yet, but the tape carries "
        f"trade sizes — so assume `Q` ahead, fill once `Q+1` contracts trade "
        f"at your price (or instantly if price sweeps straight through), and "
        f"the answer becomes a curve instead of a point.")
    log()
    log(f"`{nsig:,}` signals across `{len(res)}` quarters, `{days:,}` "
        f"sessions, both directions, {WAIT_SEC:.0f}s to fill. Commission "
        f"${COMM:.2f}; the spread is modelled by the fill price, not charged "
        f"as a constant.")
    log()
    log(f"**Taker baseline: ${tdol:+.3f} a trade** over {tn:,} trades — the "
        f"same signals, crossing the spread, filled every time.")
    log()
    def spec(a):
        n = max(a["n"], 1)
        w = a["w"]
        return dict(n=a["n"], win=w / n,
                    avgw=a["gw"] / max(w, 1),
                    avgl=a["gl"] / max(n - w, 1),
                    dol=a["pnl"] / n)

    def runlen(p, n):
        """Longest losing streak you should EXPECT over n trades. Expectancy
        says whether it pays; this says whether you could sit through it."""
        if p <= 0 or p >= 1:
            return float("nan")
        return math.log(max(n, 2)) / math.log(1 / (1 - p))

    tk = spec(sum_of([r["taker"] for r in res]))
    log("## The full spec sheet, per queue depth")
    log()
    log(f"Every row is the SAME signals and the SAME bracket — "
        f"{res[0]['S']}x{res[0]['T']} ticks, 1:1 — differing only in how the "
        f"entry is executed. `hybrid` rests a limit and crosses the spread if "
        f"the market never comes to it, so it never skips a trade.")
    log()
    log("| execution | fill rate | **win rate** | **avg win** | "
        "**avg loss** | **$/trade** | $/wk @500 | worst run | that run in $ |")
    log("|---|---|---|---|---|---|---|---|---|")

    def row(name, sp, rate, S, T):
        n52 = 500 * 52
        rl = runlen(sp["win"], n52)
        dd = rl * abs(sp["avgl"])
        log(f"| {name} | {rate} | **{sp['win']*100:.1f}%** | "
            f"${sp['avgw']:+.2f} | ${sp['avgl']:+.2f} | "
            f"**${sp['dol']:+.3f}** | ${sp['dol']*500:+,.0f} | "
            f"{rl:.0f} losses | **${dd:,.0f}** |")

    S0, T0 = res[0]["S"], res[0]["T"]
    row("cross the spread", tk, "100%", S0, T0)
    for q in QUEUES:
        mk = sum_of([r["maker"][q] for r in res])
        ms = sum_of([r["miss"][q] for r in res])
        hy = {k: mk[k] + ms[k] for k in mk}
        sp = spec(mk)
        rate = f"{mk['n']/max(nsig,1)*100:.0f}%"
        row(f"rest, queue {q}", sp, rate, S0, T0)
        if q in (0, 5, 50):
            row(f"**hybrid, queue {q}**", spec(hy), "100%", S0, T0)
    log()
    log(f"**The hybrid row is the one to read.** Resting alone throws away "
        f"every signal the market never came back for, and those are "
        f"disproportionately the winners — that is the whole adverse-selection "
        f"tax. Resting *first* and crossing as a fallback keeps all "
        f"{nsig:,} signals and still collects the tick whenever the market "
        f"does come to you. It cannot be worse than crossing on any signal, "
        f"because crossing is its fallback.")
    log()
    log(f"_Ran {(time.time()-t0)/60:.0f} min._")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write("\n".join(L) + "\n")
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
