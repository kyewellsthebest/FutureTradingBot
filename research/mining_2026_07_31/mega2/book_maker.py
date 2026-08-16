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
    # crossed/locked quotes: 0.009% of the tape, nearly all inside the
    # 21:00 UTC maintenance halt. A negative spread would let a "join
    # the bid" attempt rest above the offer.
    A = A[A["ask_px"] > A["bid_px"]].reset_index(drop=True)
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

    res = {h: {"fill": 0, "break": 0, "open": 0, "away": 0,
               "ticks": {m: [] for m in MARKS},
               "drift": {m: [] for m in MARKS},
               "half": [], "wait": []}
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
        seg_bp = bp[i + 1:end + 1]
        # first second at which the best bid has dropped below our price
        brk = np.flatnonzero(seg_bp < p)
        t_break = int(brk[0]) + 1 if len(brk) else 10 ** 9
        # Our order rests AT p. It can only be filled by trades that
        # happen AT p -- i.e. while the best bid is still p. Counting
        # volume that traded at OTHER prices was the bug: when the
        # market rallied away, trades at higher prices were credited to
        # our stale bid below, manufacturing a free fill in every rising
        # market. Same error class as the wrong-side-of-book fills that
        # killed the INVERSE FADE: volume that traded somewhere else
        # cannot fill an order here.
        elig = np.where(seg_bp == p, tvs[i + 1:end + 1], 0.0)
        c = np.cumsum(elig)
        hit = np.flatnonzero(c >= ahead)
        t_fill = int(hit[0]) + 1 if len(hit) else 10 ** 9
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
                # Buying at the bid and marking against the MID books
                # half the spread as instant profit. That is real maker
                # revenue, but it is NOT an edge and it is NOT what
                # adverse selection means -- and on NQ the spread is
                # heavy-tailed (median 3 ticks, max 434), so its MEAN is
                # dominated by moments nobody could actually rest in.
                # The two are separated here and reported separately.
                r["half"].append((mid[i] - p) / TICK)
                for m in MARKS:
                    k = j + m
                    if k < n and np.isfinite(mid[k]):
                        r["ticks"][m].append((mid[k] - p) / TICK)
                        # how the market MOVED after we committed --
                        # this is the adverse selection on its own
                        r["drift"][m].append((mid[k] - mid[i]) / TICK)
            elif b_ok:
                r["break"] += 1
            elif seg_bp[:h].size and np.nanmax(seg_bp[:h]) > p:
                # the market rallied away and never traded back to our
                # price. Not a loss -- but not an entry either, and a
                # strategy that assumes this entry happened is trading a
                # position it does not own.
                r["away"] += 1
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
        log("The half-spread column is a MEDIAN: NQ's spread is "
            "heavy-tailed (median 3 ticks, max 434) and its mean is set "
            "by moments no order could have rested through. Drift is "
            "shown as median/mean, and the MEAN is the one that matters "
            "-- P&L adds, so the average is what the account accrues, "
            "while a median of 0.00 only says price usually sat still.")
        log()
        log("| wait allowed | attempts | filled | level left first | "
            "rallied away | no outcome | median wait | half-spread earned | "
            "drift +10s med/mean | +30s | +60s |")
        log("|" + "---|" * 11)
        for h in HORIZ:
            r = res[h]
            tot = r["fill"] + r["break"] + r["open"] + r["away"]
            if not tot:
                continue
            pf = r["fill"] / tot
            wait = (np.median(r["wait"]) if r["wait"] else float("nan"))
            half = (np.median(r["half"]) if r["half"] else float("nan"))
            dr = []
            for m in MARKS:
                v = r["drift"][m]
                # median AND mean. The median says what usually happens;
                # the MEAN is what the account actually accrues, because
                # P&L adds. A median of exactly 0.000 only means price
                # most often did not move, and would hide the adverse
                # selection entirely.
                dr.append(f"{np.median(v):+.2f}/{np.mean(v):+.2f}"
                          if v else "n/a")
            log(f"| {h}s | {tot:,} | **{pf:.1%}** | "
                f"{r['break']/tot:.1%} | {r['away']/tot:.1%} | "
                f"{r['open']/tot:.1%} | "
                f"{wait:.0f}s | {half:+.3f} tk | "
                + " | ".join(f"{x} tk" for x in dr) + " |")
        log()
        # the number that decides it
        h = HORIZ[-1]
        r = res[h]
        tot = r["fill"] + r["break"] + r["open"] + r["away"]
        if tot and r["drift"][MARKS[1]]:
            pf = r["fill"] / tot
            half = float(np.median(r["half"]))
            drift = float(np.mean(r["drift"][MARKS[1]]))
            net_tk = half + drift
            per_fill = net_tk * TICK * TV
            log(f"At a {h}-second patience, **{pf:.1%}** of resting bids "
                f"fill, in a median of "
                f"{np.median(r['wait']):.0f} seconds.")
            log()
            log(f"A filled entry earns the half-spread it rested "
                f"across -- median **{half:+.3f} ticks** -- and then the "
                f"market moves **{drift:+.3f} ticks on average** in the "
                f"{MARKS[1]}s after we are committed. That second number "
                f"IS the adverse selection, and it is the half "
                f"`DEPTH.md` could not measure. "
                + ("It is negative, which is the expected direction: a "
                   "resting bid is filled preferentially when the price "
                   "is about to fall."
                   if drift < 0 else
                   "It is positive here, which is NOT the textbook "
                   "direction and is a reason to distrust it before "
                   "building on it."))
            log()
            log(f"Net of both, a filled maker entry is worth "
                f"**{net_tk:+.3f} ticks = ${per_fill:+.2f}** before the "
                f"${COMM_RT:.2f} commission a maker still pays, so the "
                f"round trip stands at "
                f"**${per_fill - COMM_RT:+.2f}** before any signal is "
                f"applied.")
            log()
            log("Two cautions that decide how much of this transfers:")
            log()
            log("1. **This is NQ, not MNQ.** We trade the micro. NQ rests "
                "2 lots at the touch and quotes 3 ticks wide; MNQ has a "
                "deeper retail queue and a tighter spread, so neither "
                "the fill rate nor the half-spread carries over. "
                "`DEPTH.md`'s 6.6% came from MNQ order-by-order data and "
                "is the number that applies to our execution.")
            log("2. **Half-spread captured is not edge.** It is the "
                "compensation for providing liquidity, and it is exactly "
                "what is lost again when the exit has to cross. A maker "
                "in and out earns it twice and a maker-in/taker-out "
                "earns it once; neither is a prediction about direction.")
            log()
    open(OUT, "w").write("\n".join(L) + "\n")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
