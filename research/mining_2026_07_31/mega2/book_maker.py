"""Can we be a MAKER on NQ, and what does it actually earn?

This is the question the cost arithmetic keeps pointing at. A taker round
trip on MNQ is 0.87pt; paying commission only, as a maker in and out, is
0.62pt. That gap decides the HFT lane:

    hold     sigma    IC needed as TAKER   as MAKER
    1 min    2.2 pt         0.40             0.28
    5 min    5.0 pt         0.174            0.124
    30 min   12.0 pt        0.073            0.052

0.40 is impossible for anything. 0.124 is not -- it is inside the range
real book signals have been measured at. So whether we can rest an order
and get filled is not a detail, it is the whole difference between a
sub-minute system being arithmetically dead and merely hard.

`research/DEPTH.md` already put a number on this: **6.6% passive fill
rate**, measured on one week of MNQ order-by-order data. If that holds,
maker strategies are unbuildable regardless of signal quality, because
93% of intended entries never happen. This re-measures it on four weeks
of NQ from the A1 tape, and adds the part DEPTH.md could not: the
ADVERSE SELECTION. A fill you get is disproportionately a fill you did
not want -- the queue trades through you precisely when the price is
about to leave. P(fill) alone is only half the number.

METHOD. At sampled seconds, assume we join the BACK of the best bid
queue at that second's price:

    queue ahead   the resting bid size at join
    we advance    only when volume TRADES against the bid (tv_sell).
                  Cancels ahead of us would also advance us, but the
                  tape cannot say whether a cancel was in front of or
                  behind our position, so counting none of them is the
                  conservative choice and understates P(fill).
    filled        cumulative tv_sell exceeds the queue ahead
    broken        the best bid drops below our price first -- the level
                  left without us
    open          neither within the horizon

Within a single second the tape cannot order a fill against a break, so
a second containing both is counted as BROKEN. That is the conservative
reading and it understates the maker's case, which is the direction an
honest error should point.

VALUE. When filled we are long at our price. The mark N seconds later
against the mid is the adverse selection, in ticks. The maker edge per
ATTEMPT is then P(fill) x value-when-filled, and it has to cover the
commission that a maker still pays.

Output: research/BOOK_MAKER.md
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
DEPTH = os.path.join(ROOT, "data", "depth")
OUT = os.path.join(ROOT, "research", "BOOK_MAKER.md")
TICK = 0.25
TV = 2.0                       # MNQ $/pt
COMM_RT = 1.24                 # commission-only round trip, in dollars
HORIZ = [30, 60, 120]          # seconds allowed to fill
MARKS = [10, 30, 60]           # seconds after fill to mark the position
SAMPLE = 10                    # join attempt every N seconds
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def run(path, sym):
    A = pd.read_parquet(path).sort_values("sec").reset_index(drop=True)
    full = np.arange(int(A["sec"].iloc[0]), int(A["sec"].iloc[-1]) + 1)
    A = A.set_index("sec").reindex(full)
    present = A["bid_px"].notna().values
    A[["bid_px", "ask_px", "bid_sz", "ask_sz"]] = \
        A[["bid_px", "ask_px", "bid_sz", "ask_sz"]].ffill()
    A["tv_sell"] = A["tv_sell"].fillna(0.0)
    bp = A["bid_px"].values.astype(np.float64)
    ap = A["ask_px"].values.astype(np.float64)
    bs = A["bid_sz"].values.astype(np.float64)
    tvs = A["tv_sell"].values.astype(np.float64)
    mid = (bp + ap) / 2.0
    n = len(bp)
    ok = np.isfinite(bp) & present

    cum = np.concatenate([[0.0], np.cumsum(tvs)])
    res = {h: {"fill": 0, "break": 0, "open": 0,
               "ticks": {m: [] for m in MARKS}, "wait": []}
           for h in HORIZ}
    HMAX = max(HORIZ)
    for i in range(0, n - HMAX - max(MARKS), SAMPLE):
        if not ok[i]:
            continue
        p = bp[i]
        ahead = bs[i]
        if not np.isfinite(ahead) or ahead <= 0:
            continue
        end = i + HMAX
        # first second at which the best bid has dropped below our price
        seg_bp = bp[i + 1:end + 1]
        brk = np.flatnonzero(seg_bp < p)
        t_break = int(brk[0]) + 1 if len(brk) else 10 ** 9
        # first second at which trades through the bid cover the queue
        need = cum[i + 1] + ahead
        rel = np.searchsorted(cum[i + 2:end + 2], need) + 1
        t_fill = int(rel) if rel <= HMAX else 10 ** 9
        for h in HORIZ:
            r = res[h]
            f_ok = t_fill <= h
            b_ok = t_break <= h
            # a second containing both is read as a break: the tape
            # cannot order them inside one second, and this is the
            # reading that does NOT flatter the maker.
            if f_ok and (not b_ok or t_fill < t_break):
                r["fill"] += 1
                r["wait"].append(t_fill)
                j = i + t_fill
                for m in MARKS:
                    k = j + m
                    if k < n and np.isfinite(mid[k]):
                        r["ticks"][m].append((mid[k] - p) / TICK)
            elif b_ok:
                r["break"] += 1
            else:
                r["open"] += 1
    return res, int(ok.sum())


def main():
    files = sorted(glob.glob(os.path.join(DEPTH, "*_book_1s.parquet")))
    if not files:
        print("no data/depth/*_book_1s.parquet yet -- A1 has not run.")
        return
    log("# Can we be a maker on NQ, and what does it earn?")
    log()
    log("A taker round trip on MNQ is **0.87pt**; commission only, as a "
        "maker in and out, is **0.62pt**. At a 5-minute hold that is the "
        "difference between needing IC 0.174 and IC 0.124 -- the second "
        "is inside the range real book signals have been measured at, "
        "the first is not. So this is not a detail at the edges, it is "
        "the HFT lane's binding constraint.")
    log()
    log("`research/DEPTH.md` measured a **6.6% passive fill rate** on one "
        "week of MNQ order-by-order data. If that holds, maker strategies "
        "are unbuildable at any signal quality, because 93% of intended "
        "entries never happen.")
    log()
    log("We join the BACK of the best bid queue and advance only when "
        "volume TRADES against the bid. Cancels ahead of us would also "
        "advance us, but the tape cannot say whether a cancel sat in "
        "front of or behind our position, so none are counted -- that "
        "understates P(fill). A second containing both a fill and the "
        "level breaking is read as a break, for the same reason: the "
        "conservative reading is the one that does not flatter the case "
        "being tested.")
    log()
    for f in files:
        sym = os.path.basename(f).split("_book_1s")[0]
        res, nsec = run(f, sym)
        log(f"## {sym} ({nsec:,} seconds with a live book)")
        log()
        log("| wait allowed | attempts | filled | level left first | "
            "no outcome | median wait | mark +10s | mark +30s | "
            "mark +60s |")
        log("|" + "---|" * 9)
        for h in HORIZ:
            r = res[h]
            tot = r["fill"] + r["break"] + r["open"]
            if not tot:
                continue
            pf = r["fill"] / tot
            wait = (np.median(r["wait"]) if r["wait"] else float("nan"))
            marks = []
            for m in MARKS:
                v = r["ticks"][m]
                marks.append(f"{np.mean(v):+.3f}" if v else "n/a")
            log(f"| {h}s | {tot:,} | **{pf:.1%}** | "
                f"{r['break']/tot:.1%} | {r['open']/tot:.1%} | "
                f"{wait:.0f}s | " + " | ".join(f"{x} tk" for x in marks) +
                " |")
        log()
        # the number that decides it
        h = HORIZ[-1]
        r = res[h]
        tot = r["fill"] + r["break"] + r["open"]
        if tot and r["ticks"][MARKS[1]]:
            pf = r["fill"] / tot
            adv = float(np.mean(r["ticks"][MARKS[1]]))
            per_fill = adv * TICK * TV
            log(f"At a {h}-second patience, **{pf:.1%}** of resting bids "
                f"fill. When one does, the mid {MARKS[1]}s later sits "
                f"**{adv:+.3f} ticks** from our price -- that is the "
                f"adverse selection, and it is the half of the number "
                f"`DEPTH.md` could not measure.")
            log()
            log(f"A filled maker entry is therefore worth "
                f"**${per_fill:+.2f}** gross before the "
                f"${COMM_RT:.2f} commission a maker still pays. "
                + ("The entry side pays for itself, so a maker strategy "
                   "is worth designing around a signal."
                   if per_fill > 0 else
                   "The entry side is negative on its own: resting orders "
                   "get filled precisely when the price is leaving. A "
                   "signal would have to overcome that before it earns "
                   "anything."))
            log()
            log(f"And the fill rate is the harder wall. At {pf:.1%}, "
                f"{1-pf:.0%} of intended entries never happen, so a "
                f"strategy needing N trades a day must generate "
                f"{1/max(pf,1e-9):.0f}x that many signals."
                if pf < 0.5 else "")
            log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
